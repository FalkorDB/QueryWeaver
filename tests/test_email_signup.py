"""Tests for the email signup endpoint, focused on the authentication-bypass fix.

Regression coverage for CVE-2026-10130: signing up with an email that already
belongs to an account (under any provider) must NOT issue a session token, which
would otherwise allow taking over that account without knowing its password.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.routes.auth import EmailSignupRequest, email_signup


def _mock_request():
    """Build a minimal mock Request for the signup handler."""
    request = MagicMock()
    # _is_request_secure reads these; default to a plain http request.
    request.headers.get.return_value = None
    request.url.scheme = "http"
    return request


def _signup_data(email="victim@example.com"):
    return EmailSignupRequest(
        firstName="Mallory",
        lastName="Attacker",
        email=email,
        password="attacker-password-123",
    )


def _set_cookie_header(response):
    return response.headers.get("set-cookie", "") or ""


class TestEmailSignupExistingAccount:
    """An existing account must never be handed a session token via signup."""

    @pytest.mark.asyncio
    @patch("api.routes.auth.ensure_user_in_organizations", new_callable=AsyncMock)
    @patch("api.routes.auth._set_mail_hash", new_callable=AsyncMock)
    @patch("api.routes.auth._email_account_exists", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_existing_account_is_rejected_without_token(
        self, _enabled, mock_exists, mock_set_hash, mock_ensure
    ):
        mock_exists.return_value = True

        response = await email_signup(_mock_request(), _signup_data())

        assert response.status_code == 409
        body = response.body.decode()
        assert "already exists" in body
        # No session token must be issued for an existing account.
        assert "api_token=" not in _set_cookie_header(response)
        # The account/token graph mutation and password write must not run.
        mock_ensure.assert_not_called()
        mock_set_hash.assert_not_called()

    @pytest.mark.asyncio
    @patch("api.routes.auth._email_account_exists", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_existence_check_failure_fails_closed(self, _enabled, mock_exists):
        """If the existence check raises, the handler must not issue a token."""
        mock_exists.side_effect = RuntimeError("db down")

        response = await email_signup(_mock_request(), _signup_data())

        assert response.status_code == 500
        assert "api_token=" not in _set_cookie_header(response)


class TestEmailSignupNewAccount:
    """A genuinely new account should be created and issued a token."""

    @pytest.mark.asyncio
    @patch("api.routes.auth.ensure_user_in_organizations", new_callable=AsyncMock)
    @patch("api.routes.auth._set_mail_hash", new_callable=AsyncMock)
    @patch("api.routes.auth._email_account_exists", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_new_account_is_created_with_token(
        self, _enabled, mock_exists, mock_set_hash, mock_ensure
    ):
        mock_exists.return_value = False
        mock_ensure.return_value = (True, {"new_identity": True})

        response = await email_signup(_mock_request(), _signup_data("new@example.com"))

        assert response.status_code == 201
        assert "api_token=" in _set_cookie_header(response)
        mock_ensure.assert_awaited_once()
        mock_set_hash.assert_awaited_once()


class TestEmailSignupCreationFailure:
    """If account creation does not yield a new identity, no token is issued."""

    @pytest.mark.asyncio
    @patch("api.routes.auth.delete_user_token", new_callable=AsyncMock)
    @patch("api.routes.auth.ensure_user_in_organizations", new_callable=AsyncMock)
    @patch("api.routes.auth._set_mail_hash", new_callable=AsyncMock)
    @patch("api.routes.auth._email_account_exists", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_non_new_identity_is_rejected_and_token_cleaned_up(
        self, _enabled, mock_exists, mock_set_hash, mock_ensure, mock_delete
    ):
        # Passes the pre-check, but creation reports the identity already existed
        # (e.g. a concurrent signup race). No token must leak.
        mock_exists.return_value = False
        mock_ensure.return_value = (False, {"new_identity": False})

        response = await email_signup(_mock_request(), _signup_data("race@example.com"))

        assert response.status_code == 500
        assert "api_token=" not in _set_cookie_header(response)
        mock_set_hash.assert_not_called()
        mock_delete.assert_awaited_once()
