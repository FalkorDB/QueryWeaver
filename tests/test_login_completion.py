"""Tests for `_complete_login`, the final step of every successful login.

It is shared by the OAuth callbacks and by email login, and it is the only place
that decides whether a browser walks away with a credential. Two properties
matter enough to pin here:

* No API token is minted. The browser never receives one, so a token created at
  login would be an orphan `Token` node that nothing can present and logout
  cannot revoke.
* It fails closed. The signed session cookie is the browser's only credential,
  so a failure to set it must not be reported as a successful login.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status

from api.auth.browser_session import SESSION_KEY
from api.routes import auth as auth_module
from api.routes.auth import EmailLoginRequest, _complete_login, email_login

pytestmark = [pytest.mark.unit, pytest.mark.auth]

USER_DATA = {
    "id": "provider-user-1",
    "email": "user@example.com",
    "name": "Example User",
    "picture": "https://example.invalid/avatar.png",
}


def _request(handler_result=True, with_handler=True):
    request = MagicMock()
    request.session = {}
    if with_handler:
        request.app.state.callback_handler = AsyncMock(return_value=handler_result)
    else:
        request.app.state.callback_handler = None
    return request


class TestNoTokenIsMinted:
    """A browser login must not leave a Token node behind."""

    @pytest.mark.asyncio
    async def test_handler_is_asked_for_an_identity_without_a_token(self):
        request = _request()

        await _complete_login(request, "google", USER_DATA)

        request.app.state.callback_handler.assert_awaited_once_with(
            "google", USER_DATA, None
        )

    @pytest.mark.asyncio
    async def test_session_carries_the_profile(self):
        request = _request()

        await _complete_login(request, "google", USER_DATA)

        payload = request.session[SESSION_KEY]
        assert payload["email"] == USER_DATA["email"]
        assert payload["provider"] == "google"
        assert payload["provisioned"] is True


class TestOutageDoesNotBlockLogin:
    """A FalkorDB outage costs the stored profile, not the ability to log in."""

    @pytest.mark.asyncio
    async def test_failed_user_store_write_still_logs_in(self):
        request = _request(handler_result=False)

        await _complete_login(request, "github", USER_DATA)

        # Logged in, but flagged so `/auth-status` can retry provisioning later.
        assert request.session[SESSION_KEY]["provisioned"] is False


class TestFailsClosed:
    """Anything that leaves the browser without a credential must raise."""

    @pytest.mark.asyncio
    async def test_missing_email_is_rejected(self):
        request = _request()

        with pytest.raises(HTTPException) as exc:
            await _complete_login(request, "google", {"id": "1", "name": "No Email"})

        assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
        assert not request.session

    @pytest.mark.asyncio
    async def test_missing_handler_is_rejected(self):
        request = _request(with_handler=False)

        with pytest.raises(HTTPException) as exc:
            await _complete_login(request, "google", USER_DATA)

        assert exc.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert not request.session

    @pytest.mark.asyncio
    @patch("api.routes.auth.establish_browser_session", return_value=False)
    async def test_unset_session_is_not_reported_as_success(self, _establish):
        # Without this the user is redirected to a page they are not logged into,
        # with nothing to explain why.
        request = _request()

        with pytest.raises(HTTPException) as exc:
            await _complete_login(request, "google", USER_DATA)

        assert exc.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestLoginRoutesFinishThroughCompleteLogin:
    """Every login route must funnel through the same finisher."""

    @pytest.mark.asyncio
    @patch("api.routes.auth._complete_login", new_callable=AsyncMock)
    @patch("api.routes.auth._authenticate_email_user", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_email_login(self, _enabled, mock_auth, mock_complete):
        identity = MagicMock()
        identity.properties = {
            "provider_user_id": "1",
            "email": USER_DATA["email"],
            "name": USER_DATA["name"],
            "picture": USER_DATA["picture"],
        }
        mock_auth.return_value = (True, {"identity": identity})

        response = await email_login(
            _request(), EmailLoginRequest(email=USER_DATA["email"], password="pw")
        )

        assert response.status_code == 200
        assert mock_complete.await_args.args[1] == "email"

    @pytest.mark.parametrize(
        ("provider", "route_name"),
        [("google", "google_authorized"), ("github", "github_authorized")],
    )
    @pytest.mark.asyncio
    async def test_oauth_callbacks(self, provider, route_name):
        client = MagicMock()
        client.authorize_access_token = AsyncMock(return_value={"access_token": "t"})
        response_stub = MagicMock(status_code=200)
        response_stub.json.return_value = {
            "id": "1",
            "email": USER_DATA["email"],
            "name": USER_DATA["name"],
        }
        client.get = AsyncMock(return_value=response_stub)

        with patch.object(
                 auth_module, f"_is_{provider}_auth_enabled", return_value=True
             ), \
             patch.object(auth_module, "_get_provider_client", return_value=client), \
             patch.object(
                 auth_module, "_complete_login", new_callable=AsyncMock
             ) as mock_complete:
            redirect = await getattr(auth_module, route_name)(_request())

        assert redirect.status_code == 302
        assert mock_complete.await_args.args[1] == provider
