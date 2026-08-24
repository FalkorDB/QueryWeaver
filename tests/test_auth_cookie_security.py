"""Regression tests for the cookie-security and provisioning fixes.

Four separate defects are pinned here:

* ``X-Forwarded-Proto`` was compared verbatim, so a proxy sending ``HTTPS`` or
  ``https, http`` silently dropped the ``Secure`` flag on a real HTTPS request.
* The session cookie lost ``Secure`` whenever ``APP_ENV`` was simply unset,
  which is the easiest deployment mistake to make.
* The ``api_token`` cookie took its ``Secure`` flag from the request, so a
  single request steered over plain HTTP handed out the credential unprotected.
* A login during a FalkorDB outage was marked provisioned even though nothing
  was written, so the deferred repair never ran.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.routes import auth as auth_routes

from api.app_factory import _session_cookie_https_only
from api.auth.browser_session import establish_browser_session, is_provisioned
from api.auth.oauth_handlers import setup_oauth_handlers
from api.auth.user_management import _build_user_merge_query
from api.helpers.request_security import is_secure_request, should_mark_cookie_secure
from api.routes.auth import _retry_pending_provisioning

pytestmark = [pytest.mark.unit, pytest.mark.auth]


class FakeRequest:  # pylint: disable=too-few-public-methods
    """Minimal stand-in for the parts of Request these helpers read."""

    def __init__(self, headers=None, scheme="http"):
        self.headers = headers or {}
        self.url = SimpleNamespace(scheme=scheme)
        self.session = {}
        self.app = SimpleNamespace(state=SimpleNamespace())


class TestForwardedProtoNormalization:
    """A proxy's header spelling must not decide whether cookies are Secure."""

    @pytest.mark.parametrize(
        "forwarded",
        ["https", "HTTPS", "Https", " https ", "https, http", "https,http"],
    )
    def test_https_is_recognised(self, forwarded):
        assert is_secure_request(FakeRequest(headers={"x-forwarded-proto": forwarded})) is True

    @pytest.mark.parametrize("forwarded", ["http", "HTTP", "http, https", "ws"])
    def test_plain_http_is_recognised(self, forwarded):
        assert is_secure_request(FakeRequest(headers={"x-forwarded-proto": forwarded})) is False

    def test_falls_back_to_the_url_scheme(self):
        assert is_secure_request(FakeRequest(scheme="https")) is True
        assert is_secure_request(FakeRequest(scheme="http")) is False

    def test_both_call_sites_share_one_implementation(self):
        """The duplicate copies are what let the two drift apart."""
        # pylint: disable=import-outside-toplevel
        from api.app_factory import _is_secure_request
        from api.routes.auth import _is_request_secure

        proxied = FakeRequest(headers={"x-forwarded-proto": "HTTPS"})
        assert _is_secure_request(proxied) is True
        assert _is_request_secure(proxied) is True


class TestSessionCookieFailsSecure:
    """Forgetting ``APP_ENV`` must not downgrade the login cookie."""

    def test_unset_app_env_is_https_only(self, monkeypatch):
        monkeypatch.delenv("APP_ENV", raising=False)
        assert _session_cookie_https_only() is True

    @pytest.mark.parametrize("value", ["development", "DEVELOPMENT", "  development  "])
    def test_explicit_development_opts_out(self, monkeypatch, value):
        monkeypatch.setenv("APP_ENV", value)
        assert _session_cookie_https_only() is False

    @pytest.mark.parametrize("value", ["production", "staging", "", "dev"])
    def test_anything_else_is_https_only(self, monkeypatch, value):
        monkeypatch.setenv("APP_ENV", value)
        assert _session_cookie_https_only() is True


class TestApiTokenCookieFailsSecure:
    """The ``api_token`` cookie is a credential, so the transport cannot demote it."""

    def test_plain_http_still_gets_secure_outside_development(self, monkeypatch):
        monkeypatch.delenv("APP_ENV", raising=False)
        assert should_mark_cookie_secure(FakeRequest(scheme="http")) is True

    @pytest.mark.parametrize("value", ["production", "staging", "", "dev"])
    def test_non_development_environments_are_secure(self, monkeypatch, value):
        monkeypatch.setenv("APP_ENV", value)
        assert should_mark_cookie_secure(FakeRequest(scheme="http")) is True

    @pytest.mark.parametrize("value", ["development", "DEVELOPMENT", "  development  "])
    def test_development_follows_the_transport(self, monkeypatch, value):
        monkeypatch.setenv("APP_ENV", value)
        assert should_mark_cookie_secure(FakeRequest(scheme="http")) is False
        assert should_mark_cookie_secure(FakeRequest(scheme="https")) is True

    def test_every_api_token_cookie_uses_the_policy(self):
        """A single missed call site is enough to leak the credential."""
        source = Path(auth_routes.__file__).read_text(encoding="utf-8")
        cookie_writes = source.count('key="api_token"')
        assert cookie_writes > 0
        assert source.count("secure=should_mark_cookie_secure(request)") == cookie_writes


class TestCallbackReportsRealOutcome:
    """``handle_callback`` must not claim success when nothing was persisted."""

    @staticmethod
    def _handler():
        app = SimpleNamespace(state=SimpleNamespace())
        setup_oauth_handlers(app, oauth=object())
        return app.state.callback_handler

    @staticmethod
    def _user_info():
        return {"id": "42", "email": "user@example.com", "name": "A User"}

    @pytest.mark.asyncio
    async def test_persisted_identity_reports_success(self):
        with patch(
            "api.auth.oauth_handlers.ensure_user_in_organizations",
            new_callable=AsyncMock,
            return_value=(True, {"identity": {}, "user": {}, "new_identity": True}),
        ):
            assert await self._handler()("google", self._user_info(), "tok") is True

    @pytest.mark.asyncio
    async def test_returning_user_reports_success(self):
        """The first element is "is new identity", not a success flag."""
        with patch(
            "api.auth.oauth_handlers.ensure_user_in_organizations",
            new_callable=AsyncMock,
            return_value=(False, {"identity": {}, "user": {}, "new_identity": False}),
        ):
            assert await self._handler()("google", self._user_info(), "tok") is True

    @pytest.mark.asyncio
    async def test_outage_reports_failure(self):
        """A DB outage returns ``(False, None)`` without raising."""
        with patch(
            "api.auth.oauth_handlers.ensure_user_in_organizations",
            new_callable=AsyncMock,
            return_value=(False, None),
        ):
            assert await self._handler()("google", self._user_info(), "tok") is False

    @pytest.mark.asyncio
    async def test_missing_email_reports_failure(self):
        assert await self._handler()("google", {"id": "42"}, "tok") is False


class TestDeferredProvisioning:
    """The status poll repairs records without handing out a new credential."""

    @staticmethod
    def _logged_in():
        request = FakeRequest()
        establish_browser_session(
            request,
            email="user@example.com",
            name="A User",
            provider="google",
            provider_user_id="42",
            provisioned=False,
        )
        return request

    @pytest.mark.asyncio
    async def test_repairs_identity_without_minting_a_token(self):
        request = self._logged_in()
        with patch(
            "api.routes.auth.ensure_user_in_organizations",
            new_callable=AsyncMock,
            return_value=(True, {"identity": {}, "user": {}, "new_identity": True}),
        ) as ensure:
            await _retry_pending_provisioning(request)

        ensure.assert_awaited_once()
        assert ensure.await_args.args[4] is None, "no API token should be issued here"
        assert is_provisioned(request) is True

    @pytest.mark.asyncio
    async def test_still_unprovisioned_when_the_write_fails(self):
        request = self._logged_in()
        with patch(
            "api.routes.auth.ensure_user_in_organizations",
            new_callable=AsyncMock,
            return_value=(False, None),
        ):
            await _retry_pending_provisioning(request)

        assert is_provisioned(request) is False

    @pytest.mark.asyncio
    async def test_survives_an_outage_and_retries_later(self):
        request = self._logged_in()
        with patch(
            "api.routes.auth.ensure_user_in_organizations",
            new_callable=AsyncMock,
            side_effect=ConnectionError("graph down"),
        ):
            await _retry_pending_provisioning(request)
        assert is_provisioned(request) is False

        with patch(
            "api.routes.auth.ensure_user_in_organizations",
            new_callable=AsyncMock,
            return_value=(False, {"identity": {}, "user": {}, "new_identity": False}),
        ):
            await _retry_pending_provisioning(request)
        assert is_provisioned(request) is True

    @pytest.mark.asyncio
    async def test_already_provisioned_session_is_left_alone(self):
        request = FakeRequest()
        establish_browser_session(
            request,
            email="user@example.com",
            provider="google",
            provider_user_id="42",
            provisioned=True,
        )
        with patch(
            "api.routes.auth.ensure_user_in_organizations", new_callable=AsyncMock
        ) as ensure:
            await _retry_pending_provisioning(request)
        ensure.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_anonymous_request_is_ignored(self):
        with patch(
            "api.routes.auth.ensure_user_in_organizations", new_callable=AsyncMock
        ) as ensure:
            await _retry_pending_provisioning(FakeRequest())
        ensure.assert_not_awaited()


class TestTokenlessMergeQuery:
    """Repairing an identity must not create a Token node as a side effect."""

    def test_token_clause_is_included_by_default(self):
        assert "MERGE (token:Token {id: $api_token})" in _build_user_merge_query()

    def test_token_clause_is_omitted_on_request(self):
        query = _build_user_merge_query(include_token=False)
        assert "Token" not in query
        assert "$api_token" not in query

    def test_identity_and_user_are_still_merged(self):
        query = _build_user_merge_query(include_token=False)
        assert "MERGE (user:User {email: $email})" in query
        assert "MERGE (identity)-[:AUTHENTICATES]->(user)" in query
        assert "RETURN" in query
