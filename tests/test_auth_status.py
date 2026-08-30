"""Tests for `/auth-status` and the deferred provisioning it drives.

Logging in no longer needs FalkorDB, so a user can hold a valid browser session
with no `User`/`Identity` record behind it. `/auth-status` is where that gets
repaired, and the repair is strictly best-effort: it must never change the
authentication verdict, and it must never mint an API token.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from api.auth.browser_session import establish_browser_session, mark_provisioned
from api.core.errors import AuthBackendUnavailableError
from api.routes.auth import auth_status

pytestmark = [pytest.mark.unit, pytest.mark.auth]

SESSION_USER = {
    "id": "1",
    "email": "user@example.com",
    "name": "Example User",
    "picture": None,
    "provider": "google",
}


def _login(request):
    establish_browser_session(
        request,
        email=SESSION_USER["email"],
        name=SESSION_USER["name"],
        picture=SESSION_USER["picture"],
        provider=SESSION_USER["provider"],
        provider_user_id=SESSION_USER["id"],
    )
    return request


class FakeRequest:  # pylint: disable=too-few-public-methods
    """Minimal stand-in for the parts of Request that `/auth-status` reads."""

    def __init__(self):
        self.cookies = {}
        self.headers = {}
        self.query_params = {}
        self.session = {}


def _body(response):
    return json.loads(response.body)


def _patch_validate(**kwargs):
    return patch("api.routes.auth.validate_user", new_callable=AsyncMock, **kwargs)


def _patch_ensure(**kwargs):
    return patch(
        "api.routes.auth.ensure_user_in_organizations", new_callable=AsyncMock, **kwargs
    )


class TestStatusReporting:
    """The verdict itself."""

    @pytest.mark.asyncio
    async def test_authenticated_user_is_reported(self):
        request = _login(FakeRequest())
        mark_provisioned(request)

        with _patch_validate(return_value=(SESSION_USER, True)):
            response = await auth_status(request)

        assert response.status_code == 200
        assert _body(response)["user"]["email"] == SESSION_USER["email"]

    @pytest.mark.asyncio
    async def test_anonymous_visitor_is_not_an_error(self):
        with _patch_validate(return_value=(None, False)):
            response = await auth_status(FakeRequest())

        assert response.status_code == 200
        body = _body(response)
        assert body["authenticated"] is False
        # The sign-in screen is rendered from this, so an anonymous visitor is
        # exactly who needs to know which methods are on offer.
        assert set(body["providers"]) == {
            "email_auth_enabled",
            "google_auth_enabled",
            "github_auth_enabled",
        }

    @pytest.mark.asyncio
    async def test_unreachable_auth_store_yields_503(self):
        with _patch_validate(side_effect=AuthBackendUnavailableError("down")):
            response = await auth_status(FakeRequest())

        assert response.status_code == 503
        assert _body(response)["authenticated"] is False

    @pytest.mark.asyncio
    async def test_id_falls_back_to_the_email(self):
        # Database-backed API tokens resolve to a user with no id field.
        with _patch_validate(return_value=({"email": "t@example.com"}, True)):
            response = await auth_status(FakeRequest())

        assert _body(response)["user"]["id"] == "t@example.com"


class TestDeferredProvisioning:
    """Repairing a login whose Organizations-graph write did not land."""

    @staticmethod
    def _unprovisioned():
        return _login(FakeRequest())

    @pytest.mark.asyncio
    async def test_pending_write_is_retried_without_minting_a_token(self):
        request = self._unprovisioned()

        with _patch_validate(return_value=(SESSION_USER, True)), \
             _patch_ensure(return_value=(True, {"new_identity": True})) as ensure:
            await auth_status(request)

        # Positional `api_token` argument, fifth in the signature.
        assert ensure.await_args.args[4] is None

    @pytest.mark.asyncio
    async def test_a_provisioned_session_is_left_alone(self):
        request = self._unprovisioned()
        mark_provisioned(request)

        with _patch_validate(return_value=(SESSION_USER, True)), _patch_ensure() as ensure:
            await auth_status(request)

        ensure.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_token_authenticated_caller_has_nothing_to_repair(self):
        # No browser session at all, so there is no profile to write.
        with _patch_validate(return_value=(SESSION_USER, True)), _patch_ensure() as ensure:
            await auth_status(FakeRequest())

        ensure.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_failed_retry_does_not_change_the_verdict(self):
        request = self._unprovisioned()

        with _patch_validate(return_value=(SESSION_USER, True)), \
             _patch_ensure(side_effect=ConnectionError("still down")):
            response = await auth_status(request)

        assert response.status_code == 200
        assert _body(response)["authenticated"] is True
