"""Tests for the email signup, verification and resend endpoints.

Two properties are pinned here.

Regression coverage for CVE-2026-10130: signing up with an email that already
belongs to an account (under any provider) must NOT issue a session token, which
would otherwise allow taking over that account without knowing its password.

And the property that replaces it: signup creates nothing at all. It parks the
details and mails a link, and only opening that link creates the account and
signs the browser in. So an address the registrant does not control never
becomes an account.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import HTTPException

from api.auth.email_verification import RESULT_EXPIRED, RESULT_OK, PendingSignup, TokenIssue
from api.core.errors import AuthBackendUnavailableError
from api.routes.auth import (
    EmailResendRequest,
    EmailSignupRequest,
    _email_account_exists,
    email_signup,
    resend_verification_email,
    verify_email,
)

pytestmark = [pytest.mark.unit, pytest.mark.auth]


def _mock_request():
    """Build a minimal mock Request for the signup handler."""
    request = MagicMock()
    # The transport helpers read these; default to a plain http request.
    request.headers.get.return_value = None
    request.url.scheme = "http"
    request.base_url = "http://testserver/"
    request.session = {}
    return request


def _signup_data(email="victim@example.com"):
    return EmailSignupRequest(
        firstName="Mallory",
        lastName="Attacker",
        email=email,
        password="attacker-password-123",
    )


def _pending(email="new@example.com"):
    return PendingSignup(
        email=email,
        first_name="Ada",
        last_name="Lovelace",
        password_hash="00" * 32,
    )


def _set_cookie_header(response):
    return response.headers.get("set-cookie", "") or ""


def _verified_param(response):
    """Read the ``verified`` outcome off a verification redirect."""
    query = parse_qs(urlparse(response.headers["location"]).query)
    return (query.get("verified") or [None])[0]


class TestEmailSignupExistingAccount:
    """An existing account must never be handed a session token via signup."""

    @pytest.mark.asyncio
    @patch("api.routes.auth.discard_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth.start_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._email_account_exists", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_existing_account_is_rejected_without_token(
        self, _enabled, mock_exists, mock_start, mock_discard
    ):
        mock_exists.return_value = True

        response = await email_signup(_mock_request(), _signup_data())

        assert response.status_code == 409
        assert "already exists" in response.body.decode()
        # No session token must be issued for an existing account.
        assert "api_token=" not in _set_cookie_header(response)
        # Nothing may be parked either: a link mailed now would be redeemable
        # against an account that already exists.
        mock_start.assert_not_called()
        # Any link still outstanding for the address is revoked.
        mock_discard.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("api.routes.auth._email_account_exists", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_existence_check_failure_fails_closed(self, _enabled, mock_exists):
        """If the existence check raises, the handler must not issue a token."""
        mock_exists.side_effect = RuntimeError("db down")

        response = await email_signup(_mock_request(), _signup_data())

        assert response.status_code == 500
        assert "api_token=" not in _set_cookie_header(response)

    @pytest.mark.asyncio
    @patch("api.routes.auth.start_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._email_account_exists", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_an_outage_is_retryable_not_a_bug(self, _enabled, mock_exists, mock_start):
        # 500 would tell the caller the registration is broken, when in fact
        # nothing was decided and retrying is the right move.
        mock_exists.return_value = False
        mock_start.side_effect = AuthBackendUnavailableError("down")

        response = await email_signup(_mock_request(), _signup_data("new@example.com"))

        assert response.status_code == 503
        assert "api_token=" not in _set_cookie_header(response)


class TestEmailSignupPending:
    """Signup mails a link and creates nothing."""

    @pytest.mark.asyncio
    @patch("api.routes.auth.ensure_user_in_organizations", new_callable=AsyncMock)
    @patch("api.routes.auth._set_mail_hash", new_callable=AsyncMock)
    @patch("api.routes.auth.send_verification_link", new_callable=AsyncMock)
    @patch("api.routes.auth.start_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._email_account_exists", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_signup_mails_a_link_and_creates_nothing(
        self, _enabled, mock_exists, mock_start, mock_send, mock_set_hash, mock_ensure
    ):
        mock_exists.return_value = False
        mock_start.return_value = TokenIssue(token="raw-token", first_name="Mallory")
        mock_send.return_value = True

        request = _mock_request()
        response = await email_signup(request, _signup_data("new@example.com"))

        # 202, not 201: nothing has been created.
        assert response.status_code == 202
        body = response.body.decode()
        assert '"pending":true' in body.replace(" ", "")
        assert "api_token=" not in _set_cookie_header(response)
        # The whole point: no account and no session until the link is opened.
        assert not request.session
        mock_ensure.assert_not_called()
        mock_set_hash.assert_not_called()

        # The mailed link must carry the raw token, which exists nowhere else.
        _, kwargs = mock_send.await_args
        args = mock_send.await_args.args
        verify_url = kwargs.get("verify_url") or args[2]
        assert parse_qs(urlparse(verify_url).query)["token"] == ["raw-token"]

    @pytest.mark.asyncio
    @patch("api.routes.auth.discard_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth.send_verification_link", new_callable=AsyncMock)
    @patch("api.routes.auth.start_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._email_account_exists", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_undeliverable_mail_is_reported_and_rolled_back(
        self, _enabled, mock_exists, mock_start, mock_send, mock_discard
    ):
        # Answering 202 here would leave the user waiting for a mail that was
        # never sent, and the dead record would burn the rate limit on retry.
        mock_exists.return_value = False
        mock_start.return_value = TokenIssue(token="raw-token", first_name="Mallory")
        mock_send.return_value = False

        response = await email_signup(_mock_request(), _signup_data("new@example.com"))

        assert response.status_code == 503
        mock_discard.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("api.routes.auth.send_verification_link", new_callable=AsyncMock)
    @patch("api.routes.auth.start_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._email_account_exists", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_throttled_signup_is_refused_with_retry_after(
        self, _enabled, mock_exists, mock_start, mock_send
    ):
        mock_exists.return_value = False
        mock_start.return_value = TokenIssue(throttled=True)

        response = await email_signup(_mock_request(), _signup_data("new@example.com"))

        assert response.status_code == 429
        assert int(response.headers["retry-after"]) > 0
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    @patch("api.routes.auth.send_verification_link", new_callable=AsyncMock)
    @patch("api.routes.auth.start_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._email_account_exists", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_exhausted_signup_is_refused_without_inviting_a_retry(
        self, _enabled, mock_exists, mock_start, mock_send
    ):
        mock_exists.return_value = False
        mock_start.return_value = TokenIssue(exhausted=True)

        response = await email_signup(_mock_request(), _signup_data("new@example.com"))

        assert response.status_code == 429
        assert "Too many" in response.body.decode()
        mock_send.assert_not_called()


class TestVerifyEmail:
    """Opening the link is what creates the account and the session."""

    @pytest.mark.asyncio
    @patch("api.routes.auth.establish_browser_session", return_value=True)
    @patch("api.routes.auth._set_mail_hash", new_callable=AsyncMock)
    @patch("api.routes.auth.ensure_user_in_organizations", new_callable=AsyncMock)
    @patch("api.routes.auth._email_account_exists", new_callable=AsyncMock)
    @patch("api.routes.auth.consume_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_valid_link_creates_the_account_and_logs_in(
        self, _enabled, mock_consume, mock_exists, mock_ensure, mock_set_hash, mock_session
    ):
        pending = _pending()
        mock_consume.return_value = (pending, RESULT_OK)
        mock_exists.return_value = False
        mock_ensure.return_value = (True, {"new_identity": True})

        response = await verify_email(_mock_request(), token="raw-token")

        assert response.status_code == 303
        assert _verified_param(response) == "success"
        mock_ensure.assert_awaited_once()
        # No API token is minted: the session cookie is the browser credential.
        assert mock_ensure.await_args.args[-1] is None
        mock_set_hash.assert_awaited_once_with(pending.email, pending.password_hash)
        assert mock_session.call_args.kwargs["provisioned"] is True

    @pytest.mark.asyncio
    @patch("api.routes.auth.ensure_user_in_organizations", new_callable=AsyncMock)
    @patch("api.routes.auth.consume_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_unknown_or_replayed_token_creates_nothing(
        self, _enabled, mock_consume, mock_ensure
    ):
        # A second click finds nothing, because the first one deleted the node.
        mock_consume.return_value = (None, "invalid")

        response = await verify_email(_mock_request(), token="already-used")

        assert _verified_param(response) == "invalid"
        mock_ensure.assert_not_called()

    @pytest.mark.asyncio
    @patch("api.routes.auth.ensure_user_in_organizations", new_callable=AsyncMock)
    @patch("api.routes.auth.consume_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_expired_token_is_distinguished_from_an_invalid_one(
        self, _enabled, mock_consume, mock_ensure
    ):
        # The user can act on "expired" (sign up again); "invalid" reads like a
        # broken link, so conflating them would send them to support instead.
        mock_consume.return_value = (None, RESULT_EXPIRED)

        response = await verify_email(_mock_request(), token="stale")

        assert _verified_param(response) == "expired"
        mock_ensure.assert_not_called()

    @pytest.mark.asyncio
    @patch("api.routes.auth.ensure_user_in_organizations", new_callable=AsyncMock)
    @patch("api.routes.auth._email_account_exists", new_callable=AsyncMock)
    @patch("api.routes.auth.consume_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_link_for_an_address_that_gained_an_account_is_refused(
        self, _enabled, mock_consume, mock_exists, mock_ensure
    ):
        # Signed up by email, then logged in with Google before clicking. The
        # link must not log anyone into that account.
        mock_consume.return_value = (_pending(), RESULT_OK)
        mock_exists.return_value = True

        response = await verify_email(_mock_request(), token="raw-token")

        assert _verified_param(response) == "exists"
        mock_ensure.assert_not_called()

    @pytest.mark.asyncio
    @patch("api.routes.auth.establish_browser_session", return_value=False)
    @patch("api.routes.auth._set_mail_hash", new_callable=AsyncMock)
    @patch("api.routes.auth.ensure_user_in_organizations", new_callable=AsyncMock)
    @patch("api.routes.auth._email_account_exists", new_callable=AsyncMock)
    @patch("api.routes.auth.consume_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_unset_session_is_reported_as_a_failure(
        self, _enabled, mock_consume, mock_exists, mock_ensure, _set_hash, _session
    ):
        # Landing on a logged-out page with no explanation is worse than being
        # told it did not work; the account is real, so logging in still works.
        mock_consume.return_value = (_pending(), RESULT_OK)
        mock_exists.return_value = False
        mock_ensure.return_value = (True, {"new_identity": True})

        response = await verify_email(_mock_request(), token="raw-token")

        assert _verified_param(response) == "failed"

    @pytest.mark.asyncio
    @patch("api.routes.auth.establish_browser_session", return_value=True)
    @patch("api.routes.auth._set_mail_hash", new_callable=AsyncMock)
    @patch("api.routes.auth.ensure_user_in_organizations", new_callable=AsyncMock)
    @patch("api.routes.auth._email_account_exists", new_callable=AsyncMock)
    @patch("api.routes.auth.consume_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_password_write_failure_does_not_log_anyone_in(
        self, _enabled, mock_consume, mock_exists, mock_ensure, mock_set_hash, mock_session
    ):
        mock_consume.return_value = (_pending(), RESULT_OK)
        mock_exists.return_value = False
        mock_ensure.return_value = (True, {"new_identity": True})
        mock_set_hash.side_effect = HTTPException(status_code=500)

        response = await verify_email(_mock_request(), token="raw-token")

        assert _verified_param(response) == "failed"
        mock_session.assert_not_called()

    @pytest.mark.asyncio
    @patch("api.routes.auth.consume_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_backend_outage_asks_the_user_to_try_the_link_again(
        self, _enabled, mock_consume
    ):
        mock_consume.side_effect = AuthBackendUnavailableError("down")

        response = await verify_email(_mock_request(), token="raw-token")

        assert _verified_param(response) == "unavailable"

    @pytest.mark.asyncio
    @patch("api.routes.auth.consume_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=False)
    async def test_disabled_email_auth_redeems_nothing(self, _enabled, mock_consume):
        response = await verify_email(_mock_request(), token="raw-token")

        assert _verified_param(response) == "failed"
        mock_consume.assert_not_called()


class TestResendVerification:
    """The resend endpoint must not become an account-existence oracle."""

    @pytest.mark.asyncio
    @patch("api.routes.auth.send_verification_link", new_callable=AsyncMock)
    @patch("api.routes.auth.refresh_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_pending_address_gets_a_fresh_link(self, _enabled, mock_refresh, mock_send):
        mock_refresh.return_value = TokenIssue(token="fresh-token", first_name="Ada")
        mock_send.return_value = True

        response = await resend_verification_email(
            _mock_request(), EmailResendRequest(email="pending@example.com")
        )

        assert response.status_code == 202
        mock_send.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("api.routes.auth.send_verification_link", new_callable=AsyncMock)
    @patch("api.routes.auth.refresh_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_unknown_and_throttled_answer_exactly_like_a_success(
        self, _enabled, mock_refresh, mock_send
    ):
        # Same status and same body for all three, or the endpoint would tell an
        # anonymous caller which addresses are mid-signup.
        mock_refresh.return_value = TokenIssue(token="fresh-token", first_name="Ada")
        mock_send.return_value = True
        issued = await resend_verification_email(
            _mock_request(), EmailResendRequest(email="pending@example.com")
        )

        mock_refresh.return_value = TokenIssue(missing=True)
        unknown = await resend_verification_email(
            _mock_request(), EmailResendRequest(email="nobody@example.com")
        )

        mock_refresh.return_value = TokenIssue(throttled=True)
        throttled = await resend_verification_email(
            _mock_request(), EmailResendRequest(email="pending@example.com")
        )

        assert issued.status_code == unknown.status_code == throttled.status_code == 202
        assert issued.body == unknown.body == throttled.body

    @pytest.mark.asyncio
    @patch("api.routes.auth.send_verification_link", new_callable=AsyncMock)
    @patch("api.routes.auth.refresh_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_unknown_address_is_never_mailed(self, _enabled, mock_refresh, mock_send):
        mock_refresh.return_value = TokenIssue(missing=True)

        await resend_verification_email(
            _mock_request(), EmailResendRequest(email="nobody@example.com")
        )

        mock_send.assert_not_called()

    @pytest.mark.asyncio
    @patch("api.routes.auth.refresh_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_malformed_address_is_rejected(self, _enabled, mock_refresh):
        response = await resend_verification_email(
            _mock_request(), EmailResendRequest(email="not-an-email")
        )

        assert response.status_code == 400
        mock_refresh.assert_not_called()

    @pytest.mark.asyncio
    @patch("api.routes.auth.refresh_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_backend_outage_is_retryable(self, _enabled, mock_refresh):
        mock_refresh.side_effect = AuthBackendUnavailableError("down")

        response = await resend_verification_email(
            _mock_request(), EmailResendRequest(email="pending@example.com")
        )

        assert response.status_code == 503


class TestEmailAccountExistsResultHandling:
    """Coverage for how `_email_account_exists` interprets query results.

    The endpoint tests above mock this helper, so they cannot catch a regression
    where the helper misreads the query result and returns a falsy value for an
    existing account -- which would make signup *fail open* and reintroduce
    CVE-2026-10130. The query itself is a UNION that returns one row per matched
    User/Identity, so a non-empty result set means an account exists.

    The query string is not exercised against a live database here (the shared
    async FalkorDB client is not safe across pytest-asyncio's per-test event
    loops); it is validated separately. These tests pin the result handling.
    """

    @staticmethod
    def _patch_graph(result_set):
        graph = MagicMock()
        graph.query = AsyncMock(return_value=MagicMock(result_set=result_set))
        return patch("api.routes.auth.db.select_graph", return_value=graph)

    @pytest.mark.asyncio
    async def test_non_empty_result_means_account_exists(self):
        # UNION yields one row per matching User/Identity node.
        with self._patch_graph([["node-a"], ["node-b"]]):
            assert await _email_account_exists("taken@example.com") is True

    @pytest.mark.asyncio
    async def test_empty_result_means_no_account(self):
        with self._patch_graph([]):
            assert await _email_account_exists("free@example.com") is False

    @pytest.mark.asyncio
    async def test_query_error_propagates_to_fail_closed(self):
        """The helper must not swallow errors, so the endpoint can fail closed."""
        graph = MagicMock()
        graph.query = AsyncMock(side_effect=RuntimeError("db down"))
        with patch("api.routes.auth.db.select_graph", return_value=graph):
            with pytest.raises(RuntimeError):
                await _email_account_exists("err@example.com")
