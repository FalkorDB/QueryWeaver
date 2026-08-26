"""Request/response tests for the REST routes under ``api/routes/``.

Every route is exercised through ``TestClient`` with the core layer mocked, so
these tests cover the HTTP contract — status codes, response bodies and the
streaming wire format — without reaching a real database or LLM.

A FalkorDB instance must still be reachable to *import* the app: importing
``api.index`` pulls in ``api/extensions.py``, which opens a connection at
import time. CI provides one as a service container.

Requests authenticate with a Bearer token: ``CSRFMiddleware`` exempts
Bearer-authenticated requests, so the tests assert authorization behaviour
rather than re-testing CSRF (see ``test_csrf_middleware.py``).
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.core.errors import GraphNotFoundError, InternalError, InvalidArgumentError
from api.core.pipeline import MESSAGE_DELIMITER
from api.index import app

pytestmark = pytest.mark.unit

USER_EMAIL = "tester@example.com"
BEARER = {"Authorization": "Bearer test-token"}

# (method, path, json body) for every route guarded by ``token_required``.
# Bodies are valid so the request reaches the auth decorator instead of
# failing FastAPI's request validation with a 422.
PROTECTED_ROUTES = [
    ("GET", "/graphs", None),
    ("POST", "/graphs", {"database": "testdb"}),
    ("GET", "/graphs/testdb/data", None),
    ("DELETE", "/graphs/testdb", None),
    ("POST", "/graphs/testdb", {"chat": ["show me users"]}),
    ("POST", "/graphs/testdb/confirm", {"sql_query": "DELETE FROM users"}),
    ("POST", "/graphs/testdb/refresh", None),
    ("GET", "/graphs/testdb/user-rules", None),
    ("PUT", "/graphs/testdb/user-rules", {"user_rules": "be brief"}),
    ("POST", "/database", {"url": "postgresql://u:p@localhost:5432/testdb"}),
    ("GET", "/tokens/list", None),
    ("POST", "/tokens/generate", None),
    ("DELETE", "/tokens/abcd", None),
    ("POST", "/settings/validate-api-key", {"api_key": "sk-test"}),
]


_MISSING = object()


@pytest.fixture(name="callback_handler")
def _callback_handler():
    """Install a stub OAuth callback handler and put back what was there.

    ``app.state.callback_handler`` is registered during normal startup by
    ``setup_oauth_handlers``; overwriting or deleting it without restoring
    leaks into whatever test happens to run next.
    """
    previous = getattr(app.state, "callback_handler", _MISSING)
    handler = AsyncMock()
    app.state.callback_handler = handler
    try:
        yield handler
    finally:
        if previous is _MISSING:
            del app.state.callback_handler
        else:
            app.state.callback_handler = previous


@pytest.fixture(name="no_callback_handler")
def _no_callback_handler():
    """Remove the callback handler for one test, then put it back."""
    previous = getattr(app.state, "callback_handler", _MISSING)
    if previous is not _MISSING:
        del app.state.callback_handler
    try:
        yield
    finally:
        if previous is not _MISSING:
            app.state.callback_handler = previous


async def _agen(*items):
    """Build an async generator yielding ``items``."""
    for item in items:
        yield item


def _final(**kwargs):
    """A stand-in for the pipeline's terminal ``QueryResult``."""
    return SimpleNamespace(
        requires_confirmation=False, is_valid=True, error_message=None, **kwargs
    )


@pytest.fixture(name="client")
def client_fixture():
    """Test client for the assembled FastAPI app."""
    return TestClient(app)


@pytest.fixture(name="authed")
def authed_fixture():
    """Make the Bearer token resolve to an authenticated user."""
    with patch(
        "api.auth.user_management.validate_user",
        new=AsyncMock(return_value=({"email": USER_EMAIL}, True)),
    ):
        yield


@pytest.fixture(name="no_usage_tracking")
def no_usage_tracking_fixture():
    """Stop streaming routes from recording usage against the graph DB."""
    with patch("api.routes.graphs.record_query_usage_background") as mock:
        yield mock


def _request(client, method, path, body=None, headers=None):
    """Issue a request, sending ``body`` as JSON when the method allows it."""
    kwargs = {"headers": headers or {}}
    if body is not None:
        kwargs["json"] = body
    return client.request(method, path, **kwargs)


def _stream_events(response):
    """Decode a delimiter-separated streaming response into event dicts."""
    return [
        json.loads(chunk)
        for chunk in response.text.split(MESSAGE_DELIMITER)
        if chunk.strip()
    ]


class TestAuthorization:
    """Every route under ``api/routes/`` that requires a token."""

    @pytest.mark.parametrize(
        "method,path,body",
        PROTECTED_ROUTES,
        ids=[f"{m} {p}" for m, p, _ in PROTECTED_ROUTES],
    )
    def test_rejects_unknown_token(self, client, method, path, body):
        """An unrecognised Bearer token must yield 401, never 5xx."""
        with patch(
            "api.auth.user_management._get_user_info", new=AsyncMock(return_value=None)
        ):
            response = _request(client, method, path, body, BEARER)

        assert response.status_code == 401
        assert "Unauthorized" in response.json()["detail"]

    def test_version_is_public(self, client):
        """``/version`` is intentionally unauthenticated."""
        response = client.get("/version")

        assert response.status_code == 200
        assert response.json()["name"] == "queryweaver"
        assert response.json()["version"]


@pytest.mark.usefixtures("authed")
class TestGraphsRoutes:
    """``api/routes/graphs.py``."""

    def test_list_graphs(self, client):
        """Returns the user's databases verbatim."""
        with patch(
            "api.routes.graphs.list_databases",
            new=AsyncMock(return_value=["testdb", "sales"]),
        ):
            response = client.get("/graphs", headers=BEARER)

        assert response.status_code == 200
        assert response.json() == ["testdb", "sales"]

    def test_get_graph_data(self, client):
        """Returns the schema as-is."""
        schema = {"nodes": [{"id": 1}], "edges": []}
        with patch("api.routes.graphs.get_schema", new=AsyncMock(return_value=schema)):
            response = client.get("/graphs/testdb/data", headers=BEARER)

        assert response.status_code == 200
        assert response.json() == schema

    @pytest.mark.parametrize(
        "error,status,message",
        [
            (GraphNotFoundError("missing"), 404, "Database not found"),
            (InternalError("boom"), 500, "Failed to retrieve database schema"),
        ],
    )
    def test_get_graph_data_errors(self, client, error, status, message):
        """Core errors map to status codes without leaking details."""
        with patch(
            "api.routes.graphs.get_schema", new=AsyncMock(side_effect=error)
        ):
            response = client.get("/graphs/testdb/data", headers=BEARER)

        assert response.status_code == status
        assert response.json() == {"error": message}

    def test_delete_graph(self, client):
        """Successful deletion passes the core result through."""
        with patch(
            "api.routes.graphs.delete_database",
            new=AsyncMock(return_value={"deleted": "testdb"}),
        ):
            response = client.delete("/graphs/testdb", headers=BEARER)

        assert response.status_code == 200
        assert response.json() == {"deleted": "testdb"}

    @pytest.mark.parametrize(
        "error,status,message",
        [
            (InvalidArgumentError("bad"), 400, "Invalid delete request"),
            (GraphNotFoundError("missing"), 404, "Database not found"),
            (InternalError("boom"), 500, "Failed to delete database"),
        ],
    )
    def test_delete_graph_errors(self, client, error, status, message):
        """Core errors map to status codes without leaking details."""
        with patch(
            "api.routes.graphs.delete_database", new=AsyncMock(side_effect=error)
        ):
            response = client.delete("/graphs/testdb", headers=BEARER)

        assert response.status_code == status
        assert response.json() == {"error": message}

    @pytest.mark.parametrize(
        "filename,status",
        [
            ("schema.json", 501),
            ("schema.xml", 501),
            ("schema.csv", 501),
            ("schema.JSON", 501),
            ("schema.txt", 415),
            ("schema", 415),
            ("json", 415),
        ],
    )
    def test_load_graph_upload(self, client, filename, status):
        """Loaders are not implemented yet; unknown extensions are rejected."""
        response = client.post(
            "/graphs",
            headers=BEARER,
            files={"file": (filename, b"payload", "application/octet-stream")},
        )

        assert response.status_code == status

    def test_load_graph_multipart_without_file(self, client):
        """A multipart body with no ``file`` part is rejected."""
        response = client.post(
            "/graphs",
            headers=BEARER,
            files={"attachment": ("schema.json", b"payload", "application/json")},
        )

        assert response.status_code == 415

    def test_load_graph_json_payload(self, client):
        """A valid JSON body reaches the (unimplemented) JSON loader."""
        response = client.post("/graphs", headers=BEARER, json={"database": "testdb"})

        assert response.status_code == 501

    def test_load_graph_rejects_invalid_json_payload(self, client):
        """A JSON body missing ``database`` fails validation before the loader."""
        response = client.post("/graphs", headers=BEARER, json={"nope": 1})

        assert response.status_code == 422

    @pytest.mark.parametrize("content_type", ["application/xml", "text/xml"])
    def test_load_graph_xml_payload(self, client, content_type):
        """An XML body reaches the (unimplemented) OData loader."""
        response = client.post(
            "/graphs",
            headers={**BEARER, "Content-Type": content_type},
            content=b"<schema/>",
        )

        assert response.status_code == 501

    def test_load_graph_without_payload(self, client):
        """No body and no file is an unsupported content type."""
        response = client.post("/graphs", headers=BEARER)

        assert response.status_code == 415

    def test_load_graph_documents_its_accepted_bodies(self, client):
        """Content-Type is dispatched by hand, so the body is documented by hand."""
        schema = client.app.openapi()
        body = schema["paths"]["/graphs"]["post"]["requestBody"]

        assert body["required"] is True
        assert set(body["content"]) == {
            "application/json",
            "application/xml",
            "text/xml",
            "multipart/form-data",
        }
        assert body["content"]["application/json"]["schema"]["required"] == ["database"]
        multipart = body["content"]["multipart/form-data"]["schema"]
        assert multipart["properties"]["file"]["format"] == "binary"

    @pytest.mark.usefixtures("no_usage_tracking")
    def test_query_graph_streams_events(self, client):
        """Pipeline events are streamed delimiter-separated, minus the sentinel."""
        from api.routes.graphs import _Final  # pylint: disable=import-outside-toplevel

        with patch(
            "api.routes.graphs.run_query",
            return_value=_agen({"type": "progress"}, _Final(_final())),
        ):
            response = client.post(
                "/graphs/testdb", headers=BEARER, json={"chat": ["show me users"]}
            )

        assert response.status_code == 200
        assert _stream_events(response) == [{"type": "progress"}]

    def test_query_graph_rejects_invalid_chat(self, client):
        """Client-side validation errors surface as 400, not a broken stream."""
        with patch(
            "api.routes.graphs.validate_and_truncate_chat",
            side_effect=InvalidArgumentError("empty chat"),
        ):
            response = client.post("/graphs/testdb", headers=BEARER, json={"chat": []})

        assert response.status_code == 400
        assert response.json() == {"error": "Invalid query request"}

    def test_confirm_rejects_empty_sql(self, client):
        """A confirmation with no SQL is rejected before streaming starts."""
        response = client.post(
            "/graphs/testdb/confirm", headers=BEARER, json={"sql_query": "   "}
        )

        assert response.status_code == 400
        assert response.json() == {"error": "Invalid confirmation request"}

    @pytest.mark.usefixtures("no_usage_tracking")
    def test_confirm_streams_events(self, client):
        """Confirmed destructive operations stream like a normal query."""
        from api.routes.graphs import _Final  # pylint: disable=import-outside-toplevel

        with patch(
            "api.routes.graphs.run_confirmed",
            return_value=_agen({"type": "executing"}, _Final(_final())),
        ):
            response = client.post(
                "/graphs/testdb/confirm",
                headers=BEARER,
                json={"sql_query": "DELETE FROM users", "chat": ["drop them"]},
            )

        assert response.status_code == 200
        assert _stream_events(response) == [{"type": "executing"}]

    def test_refresh_schema_streams(self, client):
        """A refresh returns the loader's progress stream."""
        with patch(
            "api.routes.graphs.refresh_database_schema",
            new=AsyncMock(return_value=_agen("chunk")),
        ):
            response = client.post("/graphs/testdb/refresh", headers=BEARER)

        assert response.status_code == 200
        assert response.text == "chunk"

    @pytest.mark.parametrize(
        "error,status,message",
        [
            (InvalidArgumentError("bad"), 400, "Invalid request to refresh schema"),
            (InternalError("boom"), 500, "Failed to refresh database schema"),
        ],
    )
    def test_refresh_schema_errors(self, client, error, status, message):
        """Core errors map to status codes without leaking details."""
        with patch(
            "api.routes.graphs.refresh_database_schema", new=AsyncMock(side_effect=error)
        ):
            response = client.post("/graphs/testdb/refresh", headers=BEARER)

        assert response.status_code == status
        assert response.json() == {"error": message}

    def test_get_user_rules(self, client):
        """Rules are returned under a ``user_rules`` key."""
        with patch(
            "api.routes.graphs.get_user_rules", new=AsyncMock(return_value="be brief")
        ):
            response = client.get("/graphs/testdb/user-rules", headers=BEARER)

        assert response.status_code == 200
        assert response.json() == {"user_rules": "be brief"}

    def test_get_user_rules_missing_graph(self, client):
        """An unknown graph is a 404."""
        with patch(
            "api.routes.graphs.get_user_rules",
            new=AsyncMock(side_effect=GraphNotFoundError("missing")),
        ):
            response = client.get("/graphs/testdb/user-rules", headers=BEARER)

        assert response.status_code == 404
        assert response.json() == {"error": "Database not found"}

    def test_update_user_rules(self, client):
        """Updating rules echoes the stored value."""
        setter = AsyncMock()
        with patch("api.routes.graphs.set_user_rules", new=setter):
            response = client.put(
                "/graphs/testdb/user-rules",
                headers=BEARER,
                json={"user_rules": "be brief"},
            )

        assert response.status_code == 200
        assert response.json() == {"success": True, "user_rules": "be brief"}
        setter.assert_awaited_once()

    def test_update_user_rules_rejected_for_demo_graph(self, client):
        """Demo databases are read-only."""
        with patch("api.routes.graphs.GENERAL_PREFIX", "demo_"):
            response = client.put(
                "/graphs/demo_sales/user-rules",
                headers=BEARER,
                json={"user_rules": "be brief"},
            )

        assert response.status_code == 403
        assert response.json() == {
            "error": "Rules cannot be modified for demo databases"
        }


@pytest.mark.usefixtures("authed")
class TestDatabaseRoute:
    """``api/routes/database.py``."""

    def test_connect_streams_loader_progress(self, client):
        """The connect endpoint streams whatever the loader yields."""
        with patch(
            "api.routes.database.load_database",
            new=AsyncMock(return_value=_agen("step-1", "step-2")),
        ) as loader:
            response = client.post(
                "/database",
                headers=BEARER,
                json={"url": "postgresql://u:p@localhost:5432/testdb"},
            )

        assert response.status_code == 200
        assert response.text == "step-1step-2"
        assert loader.await_args.args[0] == "postgresql://u:p@localhost:5432/testdb"

    def test_connect_requires_url(self, client):
        """A body without ``url`` fails request validation."""
        response = client.post("/database", headers=BEARER, json={})

        assert response.status_code == 422


@pytest.mark.usefixtures("authed")
class TestSettingsRoute:
    """``api/routes/settings.py``."""

    @pytest.mark.parametrize(
        "body,status,error",
        [
            ({"api_key": "  "}, 400, "API key is required"),
            (
                {"api_key": "sk-test", "vendor": "bedrock"},
                400,
                "Unsupported vendor for key validation",
            ),
            ({"api_key": "sk-test", "model": " "}, 400, "Model name is required"),
            ({"api_key": "nope"}, 400, "Invalid OpenAI API key format"),
            (
                {"api_key": "sk-test", "vendor": "anthropic"},
                400,
                "Invalid Anthropic API key format",
            ),
        ],
    )
    def test_rejects_bad_input_before_calling_provider(
        self, client, body, status, error
    ):
        """Malformed requests are rejected without an outbound LLM call."""
        with patch("api.routes.settings.completion") as completion:
            response = client.post(
                "/settings/validate-api-key", headers=BEARER, json=body
            )

        assert response.status_code == status
        assert error in response.json()["error"]
        completion.assert_not_called()

    def test_accepts_valid_key(self, client):
        """A provider response with choices means the key is valid."""
        with patch(
            "api.routes.settings.completion",
            return_value=MagicMock(choices=[MagicMock()]),
        ):
            response = client.post(
                "/settings/validate-api-key",
                headers=BEARER,
                json={"api_key": "sk-test"},
            )

        assert response.status_code == 200
        assert response.json() == {"valid": True}

    @pytest.mark.parametrize(
        "detail,status,error",
        [
            ("Invalid authentication", 401, "Invalid API key"),
            ("quota exceeded", 429, "API quota exceeded or rate limited"),
            ("connection reset", 500, "Failed to validate API key"),
        ],
    )
    def test_maps_provider_errors(self, client, detail, status, error):
        """Provider failures map to status codes without echoing the exception."""
        # The provider error carries the submitted key; it must never come back out.
        provider_error = RuntimeError(f"{detail} for key sk-test")
        with patch("api.routes.settings.completion", side_effect=provider_error):
            response = client.post(
                "/settings/validate-api-key",
                headers=BEARER,
                json={"api_key": "sk-test"},
            )

        assert response.status_code == status
        assert response.json() == {"valid": False, "error": error}
        assert "sk-test" not in response.text


@pytest.mark.usefixtures("authed")
class TestTokensRoutes:
    """``api/routes/tokens.py``."""

    def test_generate_token(self, client, callback_handler):
        """A generated token is returned once, in full."""
        response = client.post("/tokens/generate", headers=BEARER)

        assert response.status_code == 200
        assert len(response.json()["token_id"]) > 20
        assert callback_handler.await_args.args[0] == "api"

    @pytest.mark.usefixtures("no_callback_handler")
    def test_generate_token_without_handler(self, client):
        """Without a registered callback handler generation fails cleanly."""
        response = client.post("/tokens/generate", headers=BEARER)

        assert response.status_code == 400
        assert response.json()["detail"] == "Failed to generate token"

    def test_list_tokens_returns_last_four_chars(self, client):
        """Listing never exposes a full token."""
        graph = MagicMock()
        graph.query = AsyncMock(
            return_value=SimpleNamespace(result_set=[["secret-token-wxyz", 1700000000]])
        )
        with patch("api.routes.tokens.db") as db:
            db.select_graph.return_value = graph
            response = client.get("/tokens/list", headers=BEARER)

        assert response.status_code == 200
        assert response.json() == {
            "tokens": [{"token_id": "wxyz", "created_at": 1700000000}]
        }

    def test_list_tokens_when_none_exist(self, client):
        """An empty result set is an empty list, not an error."""
        graph = MagicMock()
        graph.query = AsyncMock(return_value=SimpleNamespace(result_set=[]))
        with patch("api.routes.tokens.db") as db:
            db.select_graph.return_value = graph
            response = client.get("/tokens/list", headers=BEARER)

        assert response.status_code == 200
        assert response.json() == {"tokens": []}

    def test_list_tokens_database_error(self, client):
        """A graph failure is a 500 with a generic message."""
        graph = MagicMock()
        graph.query = AsyncMock(side_effect=RuntimeError("graph down"))
        with patch("api.routes.tokens.db") as db:
            db.select_graph.return_value = graph
            response = client.get("/tokens/list", headers=BEARER)

        assert response.status_code == 500
        assert response.json()["detail"] == "Internal server error"

    def test_delete_token(self, client):
        """Deleting an existing token reports success."""
        graph = MagicMock()
        graph.query = AsyncMock(return_value=SimpleNamespace(result_set=[[1]]))
        with patch("api.routes.tokens.db") as db:
            db.select_graph.return_value = graph
            response = client.delete("/tokens/wxyz", headers=BEARER)

        assert response.status_code == 200
        assert response.json() == {"message": "Token deleted successfully"}

    def test_delete_unknown_token(self, client):
        """Deleting a token that is not the user's is a 404."""
        graph = MagicMock()
        graph.query = AsyncMock(return_value=SimpleNamespace(result_set=[[0]]))
        with patch("api.routes.tokens.db") as db:
            db.select_graph.return_value = graph
            response = client.delete("/tokens/wxyz", headers=BEARER)

        assert response.status_code == 404
        assert response.json()["detail"] == "Token not found"
