"""Tests for the email signup, verification and resend endpoints.

Two properties are pinned here.

Regression coverage for CVE-2026-10130: signing up with an email that already
belongs to an account (under any provider) must NOT issue a session token, which
would otherwise allow taking over that account without knowing its password.

And the property that replaces it: signup creates nothing at all. It parks the
details and mails a code, and only handing that code back creates the account
and signs the browser in. So an address the registrant does not control never
becomes an account -- and because the code has to come back to the session that
submitted the form, a stranger cannot get someone else to finish a signup they
never started.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.auth.email_verification import (
    RESULT_EXPIRED,
    RESULT_INVALID,
    RESULT_OK,
    CodeIssue,
    PendingSignup,
)
from api.auth.user_management import _build_user_merge_query
from api.core.errors import AuthBackendUnavailableError
from api.routes.auth import (
    EmailResendRequest,
    EmailSignupRequest,
    EmailVerifyRequest,
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


def _verify_data(email="new@example.com", code="123456"):
    return EmailVerifyRequest(email=email, code=code)


def _set_cookie_header(response):
    return response.headers.get("set-cookie", "") or ""


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
        # Nothing may be parked either: a code mailed now would be redeemable
        # against an account that already exists.
        mock_start.assert_not_called()
        # Any code still outstanding for the address is revoked.
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
    """Signup mails a code and creates nothing."""

    @pytest.mark.asyncio
    @patch("api.routes.auth.ensure_user_in_organizations", new_callable=AsyncMock)
    @patch("api.routes.auth.send_verification_code", new_callable=AsyncMock)
    @patch("api.routes.auth.start_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._email_account_exists", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_signup_mails_a_code_and_creates_nothing(
        self, _enabled, mock_exists, mock_start, mock_send, mock_ensure
    ):
        mock_exists.return_value = False
        mock_start.return_value = CodeIssue(code="123456", first_name="Mallory")
        mock_send.return_value = True

        request = _mock_request()
        response = await email_signup(request, _signup_data("new@example.com"))

        # 202, not 201: nothing has been created.
        assert response.status_code == 202
        body = response.body.decode()
        assert '"pending":true' in body.replace(" ", "")
        assert "api_token=" not in _set_cookie_header(response)
        # The whole point: no account and no session until the code comes back.
        assert not request.session
        mock_ensure.assert_not_called()

        # The mail carries the raw code, which exists nowhere else.
        assert mock_send.await_args.args[2] == "123456"
        # And the code must not be echoed to the caller: the point of mailing it
        # is that only whoever reads the inbox learns it.
        assert "123456" not in body

    @pytest.mark.asyncio
    @patch("api.routes.auth.discard_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth.send_verification_code", new_callable=AsyncMock)
    @patch("api.routes.auth.start_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._email_account_exists", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_undeliverable_mail_is_reported_and_rolled_back(
        self, _enabled, mock_exists, mock_start, mock_send, mock_discard
    ):
        # Answering 202 here would leave the user waiting for a mail that was
        # never sent, and the dead record would burn the rate limit on retry.
        mock_exists.return_value = False
        mock_start.return_value = CodeIssue(code="123456", first_name="Mallory")
        mock_send.return_value = False

        response = await email_signup(_mock_request(), _signup_data("new@example.com"))

        assert response.status_code == 503
        mock_discard.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("api.routes.auth.send_verification_code", new_callable=AsyncMock)
    @patch("api.routes.auth.start_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._email_account_exists", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_throttled_signup_is_refused_with_retry_after(
        self, _enabled, mock_exists, mock_start, mock_send
    ):
        mock_exists.return_value = False
        mock_start.return_value = CodeIssue(throttled=True)

        response = await email_signup(_mock_request(), _signup_data("new@example.com"))

        assert response.status_code == 429
        assert int(response.headers["retry-after"]) > 0
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    @patch("api.routes.auth.send_verification_code", new_callable=AsyncMock)
    @patch("api.routes.auth.start_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._email_account_exists", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_exhausted_signup_is_refused_without_inviting_a_retry(
        self, _enabled, mock_exists, mock_start, mock_send
    ):
        mock_exists.return_value = False
        mock_start.return_value = CodeIssue(exhausted=True)

        response = await email_signup(_mock_request(), _signup_data("new@example.com"))

        assert response.status_code == 429
        assert "Too many" in response.body.decode()
        mock_send.assert_not_called()


class TestVerifyEmail:
    """Handing the code back is what creates the account and the session."""

    @pytest.mark.asyncio
    @patch("api.routes.auth.establish_browser_session", return_value=True)
    @patch("api.routes.auth.ensure_user_in_organizations", new_callable=AsyncMock)
    @patch("api.routes.auth._email_account_exists", new_callable=AsyncMock)
    @patch("api.routes.auth.consume_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_valid_code_creates_the_account_and_logs_in(
        self, _enabled, mock_consume, mock_exists, mock_ensure, mock_session
    ):
        pending = _pending()
        mock_consume.return_value = (pending, RESULT_OK)
        mock_exists.return_value = False
        mock_ensure.return_value = (True, {"new_identity": True})

        response = await verify_email(_mock_request(), _verify_data())

        assert response.status_code == 200
        mock_ensure.assert_awaited_once()
        # No API token is minted: the session cookie is the browser credential.
        assert mock_ensure.await_args.args[-1] is None
        # The password is written with the identity, not after it: a separate
        # write could fail and leave an account nobody can log into.
        assert mock_ensure.await_args.kwargs["password_hash"] == pending.password_hash
        assert mock_session.call_args.kwargs["provisioned"] is True

    @pytest.mark.asyncio
    @patch("api.routes.auth.consume_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_the_code_is_matched_against_the_address_that_was_submitted(
        self, _enabled, mock_consume
    ):
        # A code that redeemed against any pending signup would be a code worth
        # guessing against every one of them at once.
        mock_consume.return_value = (None, RESULT_INVALID)

        await verify_email(_mock_request(), _verify_data(email="Ada@Example.com "))

        assert mock_consume.await_args.args == ("ada@example.com", "123456")

    @pytest.mark.asyncio
    @patch("api.routes.auth.ensure_user_in_organizations", new_callable=AsyncMock)
    @patch("api.routes.auth.consume_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_wrong_expired_and_replayed_codes_read_identically(
        self, _enabled, mock_consume, mock_ensure
    ):
        # Telling them apart would let a guesser learn when they had found a
        # live signup, and let anyone probe which addresses are mid-signup.
        mock_consume.return_value = (None, RESULT_INVALID)
        wrong = await verify_email(_mock_request(), _verify_data())

        mock_consume.return_value = (None, RESULT_EXPIRED)
        expired = await verify_email(_mock_request(), _verify_data())

        assert wrong.status_code == expired.status_code == 400
        assert wrong.body == expired.body
        mock_ensure.assert_not_called()

    @pytest.mark.asyncio
    @patch("api.routes.auth.ensure_user_in_organizations", new_callable=AsyncMock)
    @patch("api.routes.auth.consume_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_an_empty_code_never_reaches_the_store(
        self, _enabled, mock_consume, mock_ensure
    ):
        response = await verify_email(_mock_request(), _verify_data(code="  "))

        assert response.status_code == 400
        mock_consume.assert_not_called()
        mock_ensure.assert_not_called()

    @pytest.mark.asyncio
    @patch("api.routes.auth.ensure_user_in_organizations", new_callable=AsyncMock)
    @patch("api.routes.auth._email_account_exists", new_callable=AsyncMock)
    @patch("api.routes.auth.consume_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_code_for_an_address_that_gained_an_account_is_refused(
        self, _enabled, mock_consume, mock_exists, mock_ensure
    ):
        # Signed up by email, then logged in with Google before confirming. The
        # code must not log anyone into that account.
        mock_consume.return_value = (_pending(), RESULT_OK)
        mock_exists.return_value = True

        response = await verify_email(_mock_request(), _verify_data())

        assert response.status_code == 409
        mock_ensure.assert_not_called()

    @pytest.mark.asyncio
    @patch("api.routes.auth.establish_browser_session", return_value=False)
    @patch("api.routes.auth.ensure_user_in_organizations", new_callable=AsyncMock)
    @patch("api.routes.auth._email_account_exists", new_callable=AsyncMock)
    @patch("api.routes.auth.consume_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_unset_session_is_reported_as_a_failure(
        self, _enabled, mock_consume, mock_exists, mock_ensure, _session
    ):
        # Silently reporting success would leave the user logged out with no
        # explanation; the account is real, so logging in still works.
        mock_consume.return_value = (_pending(), RESULT_OK)
        mock_exists.return_value = False
        mock_ensure.return_value = (True, {"new_identity": True})

        response = await verify_email(_mock_request(), _verify_data())

        assert response.status_code == 500

    @pytest.mark.asyncio
    @patch("api.routes.auth.establish_browser_session", return_value=True)
    @patch("api.routes.auth.ensure_user_in_organizations", new_callable=AsyncMock)
    @patch("api.routes.auth._email_account_exists", new_callable=AsyncMock)
    @patch("api.routes.auth.consume_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_a_failed_account_write_does_not_log_anyone_in(
        self, _enabled, mock_consume, mock_exists, mock_ensure, mock_session
    ):
        # The account and its password are one write, so a failure leaves
        # nothing behind and the address is still free to sign up again.
        mock_consume.return_value = (_pending(), RESULT_OK)
        mock_exists.return_value = False
        mock_ensure.return_value = (False, None)

        response = await verify_email(_mock_request(), _verify_data())

        assert response.status_code == 500
        mock_session.assert_not_called()

    @pytest.mark.asyncio
    @patch("api.routes.auth.consume_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_backend_outage_is_retryable(self, _enabled, mock_consume):
        mock_consume.side_effect = AuthBackendUnavailableError("down")

        response = await verify_email(_mock_request(), _verify_data())

        assert response.status_code == 503

    @pytest.mark.asyncio
    @patch("api.routes.auth.consume_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=False)
    async def test_disabled_email_auth_redeems_nothing(self, _enabled, mock_consume):
        response = await verify_email(_mock_request(), _verify_data())

        assert response.status_code == 403
        mock_consume.assert_not_called()


class TestResendVerification:
    """The resend endpoint must not become an account-existence oracle."""

    @pytest.mark.asyncio
    @patch("api.routes.auth.send_verification_code", new_callable=AsyncMock)
    @patch("api.routes.auth.refresh_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_pending_address_gets_a_fresh_code(self, _enabled, mock_refresh, mock_send):
        mock_refresh.return_value = CodeIssue(code="654321", first_name="Ada")
        mock_send.return_value = True

        response = await resend_verification_email(
            _mock_request(), EmailResendRequest(email="pending@example.com")
        )

        assert response.status_code == 202
        mock_send.assert_awaited_once()
        assert "654321" not in response.body.decode()

    @pytest.mark.asyncio
    @patch("api.routes.auth.send_verification_code", new_callable=AsyncMock)
    @patch("api.routes.auth.refresh_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_unknown_and_throttled_answer_exactly_like_a_success(
        self, _enabled, mock_refresh, mock_send
    ):
        # Same status and same body for all three, or the endpoint would tell an
        # anonymous caller which addresses are mid-signup.
        mock_refresh.return_value = CodeIssue(code="654321", first_name="Ada")
        mock_send.return_value = True
        issued = await resend_verification_email(
            _mock_request(), EmailResendRequest(email="pending@example.com")
        )

        mock_refresh.return_value = CodeIssue(missing=True)
        unknown = await resend_verification_email(
            _mock_request(), EmailResendRequest(email="nobody@example.com")
        )

        mock_refresh.return_value = CodeIssue(throttled=True)
        throttled = await resend_verification_email(
            _mock_request(), EmailResendRequest(email="pending@example.com")
        )

        assert issued.status_code == unknown.status_code == throttled.status_code == 202
        assert issued.body == unknown.body == throttled.body

    @pytest.mark.asyncio
    @patch("api.routes.auth.send_verification_code", new_callable=AsyncMock)
    @patch("api.routes.auth.refresh_pending_signup", new_callable=AsyncMock)
    @patch("api.routes.auth._is_email_auth_enabled", return_value=True)
    async def test_unknown_address_is_never_mailed(self, _enabled, mock_refresh, mock_send):
        mock_refresh.return_value = CodeIssue(missing=True)

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


class TestPasswordIsWrittenWithTheIdentity:
    """The password clause on the identity merge.

    Verification consumes the code before it creates the account, so there is
    no second chance: an account written without its password could neither be
    logged into nor signed up for again.
    """

    def test_no_password_is_written_unless_one_is_given(self):
        assert "password_hash" not in _build_user_merge_query()

    def test_the_password_is_set_as_the_identity_is_created(self):
        query = _build_user_merge_query(include_token=False, include_password=True)
        on_create, on_match = query.split("ON MATCH SET", 1)

        assert "identity.password_hash = $password_hash" in on_create
        # Never on the ON MATCH branch: an identity that already exists keeps
        # the password it already has.
        assert "password_hash" not in on_match


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
