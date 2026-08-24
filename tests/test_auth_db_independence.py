"""Browser login must not depend on FalkorDB.

These tests pin the credential precedence in ``validate_user``: an explicitly
supplied API token is always checked against the database, a browser login never
is, and an outage is reported as 503 rather than 401.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.auth import user_management
from api.auth.browser_session import clear_browser_session, establish_browser_session
from api.auth.user_management import (
    get_cookie_api_token,
    get_explicit_api_token,
    token_required,
    validate_user,
)
from api.core.errors import AuthBackendUnavailableError

pytestmark = [pytest.mark.unit, pytest.mark.auth]

DB_USER = {"email": "token-owner@example.com", "name": "Token Owner", "picture": None}


class FakeRequest:  # pylint: disable=too-few-public-methods
    """Minimal stand-in for the parts of Request that auth reads."""

    def __init__(self, cookies=None, headers=None, query_params=None):
        self.cookies = cookies or {}
        self.headers = headers or {}
        self.query_params = query_params or {}
        self.session = {}
        self.state = type("State", (), {})()


def _logged_in(request, email="browser-user@example.com"):
    establish_browser_session(
        request, email=email, name="Browser User", provider="google", provider_user_id="1"
    )
    return request


def _patch_user_info(**kwargs):
    return patch.object(user_management, "_get_user_info", new_callable=AsyncMock, **kwargs)


class TestTokenExtraction:
    """Deliberate credentials must be told apart from the ambient cookie."""

    @pytest.mark.parametrize(
        "header",
        ["Bearer abc123", "bearer abc123", "BEARER   abc123"],
    )
    def test_bearer_header_is_explicit(self, header):
        assert get_explicit_api_token(FakeRequest(headers={"authorization": header})) == "abc123"

    def test_query_parameter_is_explicit(self):
        request = FakeRequest(query_params={"api_token": "from-query"})

        assert get_explicit_api_token(request) == "from-query"

    def test_cookie_is_not_explicit(self):
        request = FakeRequest(cookies={"api_token": "from-cookie"})

        assert get_explicit_api_token(request) is None
        assert get_cookie_api_token(request) == "from-cookie"

    @pytest.mark.parametrize("header", ["", "Basic abc123", "Bearer", "Bearer   "])
    def test_non_bearer_headers_yield_nothing(self, header):
        assert get_explicit_api_token(FakeRequest(headers={"authorization": header})) is None


class TestBrowserLoginIsDatabaseFree:
    """The whole point: a FalkorDB outage must not log people out."""

    @pytest.mark.asyncio
    async def test_session_authenticates_without_touching_the_database(self):
        request = _logged_in(FakeRequest())

        with _patch_user_info() as mock_get_user_info:
            user_info, is_authenticated = await validate_user(request)

        assert is_authenticated is True
        assert user_info["email"] == "browser-user@example.com"
        mock_get_user_info.assert_not_called()

    @pytest.mark.asyncio
    async def test_session_survives_an_unreachable_database(self):
        # A stale api_token cookie is present too, so the fallback ordering matters.
        request = _logged_in(FakeRequest(cookies={"api_token": "stale"}))

        with _patch_user_info(side_effect=AuthBackendUnavailableError("down")):
            user_info, is_authenticated = await validate_user(request)

        assert is_authenticated is True
        assert user_info["email"] == "browser-user@example.com"

    @pytest.mark.asyncio
    async def test_logout_ends_the_session(self):
        request = _logged_in(FakeRequest())
        clear_browser_session(request)

        with _patch_user_info(return_value=None):
            _, is_authenticated = await validate_user(request)

        assert is_authenticated is False


class TestExplicitTokensNeverFallBack:
    """A supplied API token must be judged on its own merits."""

    @pytest.mark.asyncio
    async def test_invalid_bearer_token_does_not_borrow_the_session(self):
        request = _logged_in(FakeRequest(headers={"authorization": "Bearer bogus"}))

        with _patch_user_info(return_value=None) as mock_get_user_info:
            user_info, is_authenticated = await validate_user(request)

        assert (user_info, is_authenticated) == (None, False)
        mock_get_user_info.assert_awaited_once_with("bogus")

    @pytest.mark.asyncio
    async def test_valid_bearer_token_resolves_to_its_own_owner(self):
        request = _logged_in(FakeRequest(headers={"authorization": "Bearer good"}))

        with _patch_user_info(return_value=DB_USER):
            user_info, is_authenticated = await validate_user(request)

        assert is_authenticated is True
        assert user_info["email"] == "token-owner@example.com"

    @pytest.mark.asyncio
    async def test_unreachable_database_is_raised_not_silently_denied(self):
        request = FakeRequest(headers={"authorization": "Bearer good"})

        with _patch_user_info(side_effect=AuthBackendUnavailableError("down")):
            with pytest.raises(AuthBackendUnavailableError):
                await validate_user(request)


class TestLegacyCookieToken:
    """Sessions issued before browser logins became self-contained still work."""

    @pytest.mark.asyncio
    async def test_valid_cookie_token_authenticates(self):
        request = FakeRequest(cookies={"api_token": "legacy"})

        with _patch_user_info(return_value=DB_USER):
            user_info, is_authenticated = await validate_user(request)

        assert is_authenticated is True
        assert user_info["email"] == "token-owner@example.com"

    @pytest.mark.asyncio
    async def test_unreachable_database_denies_quietly(self):
        # Nothing else identifies this caller, so there is no verdict to give
        # but "not authenticated" -- and it must not surface as a 503 storm.
        request = FakeRequest(cookies={"api_token": "legacy"})

        with _patch_user_info(side_effect=AuthBackendUnavailableError("down")):
            user_info, is_authenticated = await validate_user(request)

        assert (user_info, is_authenticated) == (None, False)

    @pytest.mark.asyncio
    async def test_no_credentials_at_all(self):
        user_info, is_authenticated = await validate_user(FakeRequest())

        assert (user_info, is_authenticated) == (None, False)


class TestTokenRequiredStatusCodes:
    """An outage is a 503; a bad credential is a 401."""

    @staticmethod
    def _route():
        @token_required
        async def handler(request):  # pylint: disable=unused-argument
            return "ok"

        return handler

    @pytest.mark.asyncio
    async def test_session_user_is_allowed_through(self):
        request = _logged_in(FakeRequest())

        with _patch_user_info(side_effect=AuthBackendUnavailableError("down")):
            assert await self._route()(request) == "ok"

        assert request.state.user_email == "browser-user@example.com"

    @pytest.mark.asyncio
    async def test_unreachable_auth_store_yields_503(self):
        request = FakeRequest(headers={"authorization": "Bearer good"})

        with _patch_user_info(side_effect=AuthBackendUnavailableError("down")):
            with pytest.raises(HTTPException) as excinfo:
                await self._route()(request)

        assert excinfo.value.status_code == 503

    @pytest.mark.asyncio
    async def test_bad_credential_yields_401(self):
        request = FakeRequest(headers={"authorization": "Bearer bogus"})

        with _patch_user_info(return_value=None):
            with pytest.raises(HTTPException) as excinfo:
                await self._route()(request)

        assert excinfo.value.status_code == 401


class TestTokenLookup:
    """`_get_user_info` must tell "unknown token" apart from "graph is down"."""

    @staticmethod
    def _result(rows):
        return type("Result", (), {"result_set": rows})()

    @pytest.mark.asyncio
    async def test_valid_token_returns_its_owner(self):
        graph = AsyncMock()
        graph.query.return_value = self._result(
            [["token-owner@example.com", "Token Owner", None, True]]
        )

        with patch.object(user_management.db, "select_graph", return_value=graph):
            assert await user_management._get_user_info("good") == DB_USER

    @pytest.mark.asyncio
    async def test_expired_token_is_denied_and_cleaned_up(self):
        graph = AsyncMock()
        graph.query.return_value = self._result(
            [["token-owner@example.com", "Token Owner", None, False]]
        )

        with patch.object(user_management.db, "select_graph", return_value=graph), \
             patch.object(
                 user_management, "delete_user_token", new_callable=AsyncMock
             ) as delete:
            assert await user_management._get_user_info("expired") is None

        delete.assert_awaited_once_with("expired")

    @pytest.mark.asyncio
    async def test_unknown_token_is_denied_without_a_delete(self):
        graph = AsyncMock()
        graph.query.return_value = self._result([])

        with patch.object(user_management.db, "select_graph", return_value=graph), \
             patch.object(
                 user_management, "delete_user_token", new_callable=AsyncMock
             ) as delete:
            assert await user_management._get_user_info("unknown") is None

        delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_graph_failure_is_raised_not_reported_as_a_bad_token(self):
        graph = AsyncMock()
        graph.query.side_effect = ConnectionError("down")

        with patch.object(user_management.db, "select_graph", return_value=graph):
            with pytest.raises(AuthBackendUnavailableError):
                await user_management._get_user_info("good")


class TestIdentityPersistence:
    """`api_token=None` persists the identity without minting a Token node."""

    @staticmethod
    async def _merge_query_for(api_token):
        graph = AsyncMock()
        graph.query.return_value = type("Result", (), {"result_set": []})()

        with patch.object(user_management.db, "select_graph", return_value=graph):
            await user_management.ensure_user_in_organizations(
                "1", "user@example.com", "Example User", "google", api_token
            )

        return graph.query.await_args.args[0]

    @pytest.mark.asyncio
    async def test_a_token_is_merged_when_one_is_supplied(self):
        assert "MERGE (token:Token" in await self._merge_query_for("tok")

    @pytest.mark.asyncio
    async def test_no_token_is_merged_for_a_browser_login(self):
        assert "MERGE (token:Token" not in await self._merge_query_for(None)
