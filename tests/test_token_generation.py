"""Minting a durable API token is the one place a session cookie is not enough.

A browser login is a signed cookie: it cannot be revoked before it expires, and
it keeps working through a ``FASTAPI_SECRET_KEY`` rotation only because nothing
checks it against the database. A ``Token`` node has neither excuse -- it
outlives the session TTL and the signing key -- so it must not be issuable from
a cookie alone, nor handed back to the caller when the write did not land.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.auth import user_management
from api.core.errors import AuthBackendUnavailableError
from api.routes import tokens as tokens_route

pytestmark = [pytest.mark.unit, pytest.mark.auth]

USER_EMAIL = "browser-user@example.com"


class FakeRequest:  # pylint: disable=too-few-public-methods
    """Minimal stand-in for the parts of Request the route reads."""

    def __init__(self, handler=None):
        self.cookies = {}
        self.headers = {}
        self.query_params = {}
        self.session = {}
        self.state = type("State", (), {})()
        self.state.user_email = USER_EMAIL
        self.app = type("App", (), {})()
        self.app.state = type("AppState", (), {})()
        self.app.state.callback_handler = handler


def _patch_identity(**kwargs):
    return patch.object(
        tokens_route, "identity_exists", new_callable=AsyncMock, **kwargs
    )


async def _generate(request):
    """Call the route body, skipping the ``@token_required`` wrapper."""
    return await tokens_route.generate_token.__wrapped__(request)


class TestIdentityIsConfirmed:
    """A session whose identity is gone must not mint a longer-lived credential."""

    @pytest.mark.asyncio
    async def test_missing_identity_is_refused(self):
        handler = AsyncMock(return_value=True)
        request = FakeRequest(handler)

        with _patch_identity(return_value=False):
            with pytest.raises(HTTPException) as excinfo:
                await _generate(request)

        assert excinfo.value.status_code == 403
        handler.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unreachable_store_is_503_not_403(self):
        # "We could not check" is not "this user is gone": a 403 would tell the
        # caller to stop trying over an outage a retry fixes.
        request = FakeRequest(AsyncMock(return_value=True))

        with _patch_identity(side_effect=AuthBackendUnavailableError("down")):
            with pytest.raises(HTTPException) as excinfo:
                await _generate(request)

        assert excinfo.value.status_code == 503


class TestOnlyPersistedTokensAreReturned:
    """A token the caller cannot use is worse than an error."""

    @pytest.mark.asyncio
    async def test_a_confirmed_write_returns_the_token(self):
        handler = AsyncMock(return_value=True)
        request = FakeRequest(handler)

        with _patch_identity(return_value=True):
            result = await _generate(request)

        assert result.token_id
        provider, user_data, api_token = handler.await_args.args
        assert provider == "api"
        assert user_data["email"] == USER_EMAIL
        assert api_token == result.token_id

    @pytest.mark.asyncio
    async def test_a_failed_write_is_reported_not_papered_over(self):
        # handle_callback returns False when the graph write failed. Returning
        # the token anyway hands the user a credential that 401s forever and
        # never appears in /tokens/list.
        request = FakeRequest(AsyncMock(return_value=False))

        with _patch_identity(return_value=True):
            with pytest.raises(HTTPException) as excinfo:
                await _generate(request)

        assert excinfo.value.status_code == 503


class TestProviderIdNormalisation:
    """GitHub sends a JSON number; the session stores a string."""

    @pytest.mark.asyncio
    async def test_an_integer_id_is_stored_as_a_string(self):
        # MERGE keys on the raw value, so 12345 and "12345" would create two
        # Identity nodes for one GitHub user.
        graph = AsyncMock()
        graph.query.return_value = type("Result", (), {"result_set": []})()

        with patch.object(user_management.db, "select_graph", return_value=graph):
            await user_management.ensure_user_in_organizations(
                12345, "gh@example.com", "GH User", "github", None
            )

        params = graph.query.await_args.args[1]
        assert params["provider_user_id"] == "12345"
