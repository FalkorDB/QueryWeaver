"""Tests for the DB-free browser login session.

The browser session is what makes logging in independent of FalkorDB, so its
round-trip, expiry and tamper handling are pinned here.
"""

import time

import pytest

from api.auth.browser_session import (
    DEFAULT_TTL_HOURS,
    SESSION_KEY,
    SESSION_VERSION,
    clear_browser_session,
    establish_browser_session,
    is_provisioned,
    mark_provisioned,
    read_browser_session,
    session_ttl_seconds,
)

pytestmark = [pytest.mark.unit, pytest.mark.auth]


class FakeRequest:  # pylint: disable=too-few-public-methods
    """Minimal stand-in for a Starlette Request's session access."""

    def __init__(self, session=None, has_middleware=True):
        self._session = {} if session is None else session
        self._has_middleware = has_middleware

    @property
    def session(self):
        if not self._has_middleware:
            raise AssertionError("SessionMiddleware must be installed")
        return self._session


def _login(request, **overrides):
    kwargs = {
        "email": "user@example.com",
        "name": "Test User",
        "picture": "https://example.com/avatar.png",
        "provider": "google",
        "provider_user_id": "12345",
    }
    kwargs.update(overrides)
    return establish_browser_session(request, **kwargs)


class TestRoundTrip:
    """A login written to the session must read back unchanged."""

    def test_establish_then_read(self):
        request = FakeRequest()

        assert _login(request) is True

        user = read_browser_session(request)
        assert user == {
            "id": "12345",
            "email": "user@example.com",
            "name": "Test User",
            "picture": "https://example.com/avatar.png",
            "provider": "google",
        }

    def test_provider_user_id_is_stringified(self):
        # GitHub returns a numeric id; the payload must stay JSON-friendly.
        request = FakeRequest()
        _login(request, provider="github", provider_user_id=98765)

        assert read_browser_session(request)["id"] == "98765"

    def test_no_session_means_no_user(self):
        assert read_browser_session(FakeRequest()) is None

    def test_only_non_secret_profile_fields_are_stored(self):
        # The cookie is signed, not encrypted -- nothing secret may go in it.
        request = FakeRequest()
        _login(request)

        assert set(request.session[SESSION_KEY]) == {
            "v", "email", "name", "picture", "provider", "sub", "exp", "provisioned",
        }


class TestRejectedLogins:
    """Logins that cannot be represented must fail rather than half-succeed."""

    def test_missing_email_is_refused(self):
        request = FakeRequest()

        assert _login(request, email="") is False
        assert SESSION_KEY not in request.session

    def test_missing_session_middleware_is_refused(self):
        request = FakeRequest(has_middleware=False)

        assert _login(request) is False
        assert read_browser_session(request) is None
        # Must not raise -- logout has to work regardless.
        clear_browser_session(request)


class TestExpiryAndTampering:
    """Only a current, current-version payload counts as a login."""

    def test_expired_session_is_rejected_and_dropped(self):
        request = FakeRequest()
        _login(request)
        request.session[SESSION_KEY]["exp"] = time.time() - 1

        assert read_browser_session(request) is None
        assert SESSION_KEY not in request.session

    def test_old_payload_version_is_ignored(self):
        request = FakeRequest()
        _login(request)
        request.session[SESSION_KEY]["v"] = SESSION_VERSION - 1

        assert read_browser_session(request) is None

    @pytest.mark.parametrize(
        "payload",
        [
            "not-a-dict",
            {"v": SESSION_VERSION, "email": "user@example.com"},  # no expiry
            {"v": SESSION_VERSION, "exp": time.time() + 60},  # no email
            {"v": SESSION_VERSION, "email": "u@e.com", "exp": "soon"},
        ],
    )
    def test_malformed_payloads_are_ignored(self, payload):
        assert read_browser_session(FakeRequest({SESSION_KEY: payload})) is None


class TestLogout:
    """Clearing the session must actually log the user out."""

    def test_clear_removes_the_login(self):
        request = FakeRequest()
        _login(request)

        clear_browser_session(request)

        assert read_browser_session(request) is None

    def test_clear_is_idempotent(self):
        request = FakeRequest()
        clear_browser_session(request)
        clear_browser_session(request)

        assert read_browser_session(request) is None


class TestProvisioningFlag:
    """Tracks whether the Organizations-graph write for this login landed."""

    def test_defaults_to_unprovisioned(self):
        request = FakeRequest()
        _login(request)

        assert is_provisioned(request) is False

    def test_can_be_set_at_login(self):
        request = FakeRequest()
        _login(request, provisioned=True)

        assert is_provisioned(request) is True

    def test_can_be_marked_later(self):
        request = FakeRequest()
        _login(request)

        mark_provisioned(request)

        assert is_provisioned(request) is True
        # Marking must not disturb the identity itself.
        assert read_browser_session(request)["email"] == "user@example.com"

    def test_marking_without_a_login_is_a_no_op(self):
        request = FakeRequest()
        mark_provisioned(request)

        assert is_provisioned(request) is False


class TestTtlConfiguration:
    """``BROWSER_SESSION_TTL_HOURS`` tunes how long a browser login lasts."""

    def test_default_ttl(self, monkeypatch):
        monkeypatch.delenv("BROWSER_SESSION_TTL_HOURS", raising=False)

        assert session_ttl_seconds() == DEFAULT_TTL_HOURS * 3600

    def test_override_is_applied_to_new_sessions(self, monkeypatch):
        monkeypatch.setenv("BROWSER_SESSION_TTL_HOURS", "1")
        request = FakeRequest()

        _login(request)

        remaining = request.session[SESSION_KEY]["exp"] - time.time()
        assert 3500 < remaining <= 3600

    # "inf" and "1e309" both parse to float('inf'), which is > 0 but overflows
    # int(); "nan" compares false against everything. All must degrade to the
    # default, because this runs at startup and on every login.
    @pytest.mark.parametrize(
        "value", ["0", "-3", "abc", "", "inf", "-inf", "1e309", "nan"]
    )
    def test_invalid_overrides_fall_back_to_the_default(self, monkeypatch, value):
        monkeypatch.setenv("BROWSER_SESSION_TTL_HOURS", value)

        assert session_ttl_seconds() == DEFAULT_TTL_HOURS * 3600
