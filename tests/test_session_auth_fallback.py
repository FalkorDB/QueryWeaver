"""
Tests for session-based authentication fallback.

These tests verify that login is not blocked when FalkorDB is unavailable,
and that the session is used as a backup for auth validation.
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Mock FalkorDB at module level so api.extensions does not attempt a real
# Redis connection when the test suite is collected.
# ---------------------------------------------------------------------------
_extensions_mock = MagicMock()
sys.modules.setdefault("api.extensions", _extensions_mock)

# pylint: disable=wrong-import-position
from api.auth.user_management import (  # noqa: E402
    DatabaseUnavailableError,
    _validate_from_session,
    validate_user,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request(session_data: dict | None = None, api_token_cookie: str | None = None):
    """Build a minimal mock Request with session and cookies."""
    request = MagicMock()
    request.session = session_data or {}
    request.cookies = {"api_token": api_token_cookie} if api_token_cookie else {}
    # Simulate no Authorization header and no query param so get_token only
    # looks at the cookie.
    request.headers.get = lambda key, default=None: default
    request.query_params.get = lambda key, default=None: default
    return request


# ---------------------------------------------------------------------------
# _validate_from_session
# ---------------------------------------------------------------------------

class TestValidateFromSession:
    """Unit tests for the _validate_from_session helper."""

    def test_returns_user_when_token_matches(self):
        """User info is returned when the session token matches the cookie token."""
        user_info = {"email": "user@example.com", "name": "Test User", "picture": None}
        request = _make_request(
            session_data={"user_info": user_info, "api_token": "tok123"},
        )
        result_user, authenticated = _validate_from_session(request, "tok123")
        assert authenticated is True
        assert result_user == user_info

    def test_returns_none_when_token_mismatches(self):
        """No user is returned when the session token does NOT match the request token."""
        user_info = {"email": "user@example.com", "name": "Test User", "picture": None}
        request = _make_request(
            session_data={"user_info": user_info, "api_token": "different-token"},
        )
        result_user, authenticated = _validate_from_session(request, "tok123")
        assert authenticated is False
        assert result_user is None

    def test_returns_none_when_session_is_empty(self):
        """No user is returned when the session contains no auth data."""
        request = _make_request(session_data={})
        result_user, authenticated = _validate_from_session(request, "tok123")
        assert authenticated is False
        assert result_user is None

    def test_returns_none_when_session_missing_api_token(self):
        """No user is returned when the session has user_info but no api_token."""
        user_info = {"email": "user@example.com", "name": "Test User", "picture": None}
        request = _make_request(session_data={"user_info": user_info})
        result_user, authenticated = _validate_from_session(request, "tok123")
        assert authenticated is False
        assert result_user is None

    def test_returns_none_when_no_session_attribute(self):
        """No user is returned when the request object has no session."""
        request = MagicMock(spec=[])  # No attributes at all
        result_user, authenticated = _validate_from_session(request, "tok123")
        assert authenticated is False
        assert result_user is None


# ---------------------------------------------------------------------------
# validate_user – DB unavailable scenario
# ---------------------------------------------------------------------------

class TestValidateUserSessionFallback:
    """Tests for validate_user falling back to session when FalkorDB is down."""

    @pytest.mark.asyncio
    async def test_falls_back_to_session_when_db_unavailable(self):
        """validate_user returns session user when FalkorDB raises DatabaseUnavailableError."""
        user_info = {"email": "user@example.com", "name": "Test User", "picture": None}
        request = _make_request(
            session_data={"user_info": user_info, "api_token": "good-token"},
            api_token_cookie="good-token",
        )

        with patch(
            "api.auth.user_management._get_user_info",
            new_callable=AsyncMock,
            side_effect=DatabaseUnavailableError("DB is down"),
        ):
            result_user, authenticated = await validate_user(request)

        assert authenticated is True
        assert result_user == user_info

    @pytest.mark.asyncio
    async def test_db_success_returns_db_user(self):
        """validate_user returns DB user when FalkorDB is reachable."""
        db_user = {"email": "db@example.com", "name": "DB User", "picture": None}
        request = _make_request(api_token_cookie="some-token")

        with patch(
            "api.auth.user_management._get_user_info",
            new_callable=AsyncMock,
            return_value=db_user,
        ):
            result_user, authenticated = await validate_user(request)

        assert authenticated is True
        assert result_user == db_user

    @pytest.mark.asyncio
    async def test_not_authenticated_when_db_down_and_no_session(self):
        """validate_user returns not-authenticated when DB is down and no session backup."""
        request = _make_request(
            session_data={},  # No session backup
            api_token_cookie="some-token",
        )

        with patch(
            "api.auth.user_management._get_user_info",
            new_callable=AsyncMock,
            side_effect=DatabaseUnavailableError("DB is down"),
        ):
            result_user, authenticated = await validate_user(request)

        assert authenticated is False
        assert result_user is None

    @pytest.mark.asyncio
    async def test_not_authenticated_when_db_down_and_token_mismatch(self):
        """Session fallback does not authenticate when the session token differs from cookie."""
        user_info = {"email": "user@example.com", "name": "Test User", "picture": None}
        request = _make_request(
            session_data={"user_info": user_info, "api_token": "old-token"},
            api_token_cookie="new-token",  # Mismatch
        )

        with patch(
            "api.auth.user_management._get_user_info",
            new_callable=AsyncMock,
            side_effect=DatabaseUnavailableError("DB is down"),
        ):
            result_user, authenticated = await validate_user(request)

        assert authenticated is False
        assert result_user is None

    @pytest.mark.asyncio
    async def test_not_authenticated_when_no_token(self):
        """validate_user returns not-authenticated when no token is present at all."""
        request = _make_request()  # No cookies, no headers

        result_user, authenticated = await validate_user(request)

        assert authenticated is False
        assert result_user is None


# ---------------------------------------------------------------------------
# DatabaseUnavailableError is exported correctly
# ---------------------------------------------------------------------------

class TestDatabaseUnavailableError:
    """Ensure DatabaseUnavailableError can be imported and is an Exception subclass."""

    def test_is_exception(self):
        """DatabaseUnavailableError must derive from Exception."""
        assert issubclass(DatabaseUnavailableError, Exception)

    def test_can_be_raised_and_caught(self):
        """DatabaseUnavailableError can be raised and caught."""
        with pytest.raises(DatabaseUnavailableError, match="db error"):
            raise DatabaseUnavailableError("db error")
