"""Tests for the pending-signup store that backs email verification.

The store is what makes "no account until the code comes back" true, so the
properties pinned here are the ones the guarantee rests on: the raw code is
never stored, a code is redeemable exactly once, wrong guesses are finite, and
the send limits cannot be reset by asking again.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.auth import email_verification as ev

pytestmark = [pytest.mark.unit, pytest.mark.auth]


def _result(rows):
    return MagicMock(result_set=rows)


class _FakeGraph:
    """Records the queries a helper runs and replays canned result sets."""

    def __init__(self, results):
        self._results = list(results)
        self.calls = []
        self.query = AsyncMock(side_effect=self._query)

    async def _query(self, cypher, params=None):
        self.calls.append((cypher, params or {}))
        return self._results.pop(0) if self._results else _result([])


def _patch_graph(graph):
    return patch("api.auth.email_verification._graph", return_value=graph)


class TestStartPendingSignup:
    """Parking a signup, and the limits on how much mail it can generate."""

    @staticmethod
    def _issued(**previous):
        """The row the issuing query returns: the record as it stood before."""
        return _result([[previous]])

    @pytest.mark.asyncio
    async def test_only_the_code_hash_is_stored(self):
        graph = _FakeGraph([self._issued()])
        with _patch_graph(graph):
            issue = await ev.start_pending_signup(
                "new@example.com", "Ada", "Lovelace", "hash"
            )

        assert issue.issued
        _, params = graph.calls[-1]
        assert params["code_hash"] == ev.hash_code(issue.code)
        # A graph snapshot must not yield a usable code.
        assert issue.code not in params.values()

    @pytest.mark.asyncio
    async def test_only_the_ticket_hash_is_stored(self):
        # Same reasoning as the code: the ticket is the other half of the pair,
        # so a reader of the graph must not be able to lift a usable one.
        graph = _FakeGraph([self._issued()])
        with _patch_graph(graph):
            issue = await ev.start_pending_signup(
                "new@example.com", "Ada", "Lovelace", "hash"
            )

        _, params = graph.calls[-1]
        assert params["ticket_hash"] == ev.hash_code(issue.ticket)
        assert issue.ticket not in params.values()

    @pytest.mark.asyncio
    async def test_every_signup_gets_its_own_ticket(self):
        # The ticket is what stops a second submission for the same address
        # from having its password confirmed by the address's owner.
        graph = _FakeGraph([self._issued(), self._issued(code_hash="old-hash")])
        with _patch_graph(graph):
            first = await ev.start_pending_signup(
                "new@example.com", "Ada", "Lovelace", "hash"
            )
            second = await ev.start_pending_signup(
                "new@example.com", "Mal", "Lory", "other-hash"
            )

        assert first.ticket and second.ticket
        assert first.ticket != second.ticket

    @pytest.mark.asyncio
    async def test_the_code_is_six_digits(self):
        graph = _FakeGraph([self._issued()])
        with _patch_graph(graph):
            issue = await ev.start_pending_signup(
                "new@example.com", "Ada", "Lovelace", "hash"
            )

        # Including the leading zeros: a code that sometimes arrives five
        # digits long is a code the user cannot type into a fixed-width field.
        assert len(issue.code) == ev.CODE_DIGITS
        assert issue.code.isdigit()

    @pytest.mark.asyncio
    async def test_the_limit_is_enforced_inside_the_write(self):
        # Checking first and writing after would let two concurrent requests
        # both pass the check and both send while the counter advanced once.
        graph = _FakeGraph([self._issued()])
        with _patch_graph(graph):
            await ev.start_pending_signup("new@example.com", "Ada", "Lovelace", "hash")

        assert len(graph.calls) == 1
        cypher, params = graph.calls[0]
        assert "$max_sends" in cypher and "$interval_ms" in cypher
        assert params["max_sends"] == ev.max_sends()

    @pytest.mark.asyncio
    async def test_resubmitting_cannot_reset_the_send_limit(self):
        # Otherwise the rate limit is decorative: re-post the form and the
        # counter starts over. Only a record this query creates starts at zero.
        graph = _FakeGraph([self._issued(code_hash="old-hash", send_count=1)])
        with _patch_graph(graph):
            issue = await ev.start_pending_signup(
                "new@example.com", "Ada", "Lovelace", "hash"
            )

        assert issue.issued
        cypher, params = graph.calls[-1]
        assert "ELSE p.send_count + 1" in cypher
        assert "ON CREATE SET p.created_at = $now, p.send_count = 0" in cypher
        assert "send_count" not in params

    @pytest.mark.asyncio
    async def test_an_expired_record_starts_a_fresh_budget(self):
        # Nothing deletes a signup that is never confirmed, so a spent send
        # budget would otherwise lock an address out of the product for good --
        # five submissions by a stranger and the real owner can never sign up.
        graph = _FakeGraph([self._issued(code_hash="old-hash", expires_at=1)])
        with _patch_graph(graph):
            await ev.start_pending_signup("new@example.com", "Ada", "Lovelace", "hash")

        cypher, _ = graph.calls[-1]
        assert "(p.expires_at IS NULL OR p.expires_at < $now) AS stale" in cypher
        assert "WHERE (stale OR p.send_count < $max_sends)" in cypher
        assert "p.send_count = CASE WHEN stale THEN 1" in cypher

    @pytest.mark.asyncio
    async def test_expiry_does_not_lift_the_interval(self):
        # An expired record is a way to keep sending, not a way to send faster.
        graph = _FakeGraph([self._issued()])
        with _patch_graph(graph):
            await ev.start_pending_signup("new@example.com", "Ada", "Lovelace", "hash")

        cypher, _ = graph.calls[-1]
        interval = "AND (p.last_sent_at IS NULL OR $now - p.last_sent_at >= $interval_ms)"
        assert interval in cypher
        assert "stale OR p.last_sent_at" not in cypher

    @pytest.mark.asyncio
    async def test_the_whole_displaced_record_comes_back_for_reverting(self):
        # Not just the code: issuing rewrites the name, the password hash and
        # the ticket too, and an undo that restores a subset would leave a
        # record nobody submitted -- one person's code against another's
        # password. The snapshot is also how the caller tells "this address
        # already had a live code" from "this record is one I just created".
        previous = {
            "code_hash": "old-hash",
            "ticket_hash": "old-ticket",
            "password_hash": "someone-elses-password",
            "expires_at": 4242,
            "attempts": 3,
        }
        graph = _FakeGraph([self._issued(**previous)])
        with _patch_graph(graph):
            issue = await ev.start_pending_signup(
                "new@example.com", "Ada", "Lovelace", "hash"
            )

        assert issue.previous == previous
        assert issue.displaced

    @pytest.mark.asyncio
    async def test_a_record_this_call_created_displaced_nothing(self):
        graph = _FakeGraph([self._issued(email="new@example.com", send_count=0)])
        with _patch_graph(graph):
            issue = await ev.start_pending_signup(
                "new@example.com", "Ada", "Lovelace", "hash"
            )

        assert issue.issued
        assert not issue.displaced

    @pytest.mark.asyncio
    async def test_a_refused_send_says_nothing_about_why(self, monkeypatch):
        # The route answers a refusal exactly like a success, so asking the
        # graph why would only be a way to probe for a stranger's signup.
        monkeypatch.setenv("EMAIL_VERIFICATION_RESEND_SECONDS", "60")
        graph = _FakeGraph([_result([])])
        with _patch_graph(graph):
            issue = await ev.start_pending_signup(
                "new@example.com", "Ada", "Lovelace", "hash"
            )

        assert not issue.issued
        assert issue == ev.CodeIssue()
        assert len(graph.calls) == 1

    @pytest.mark.asyncio
    async def test_send_budget_is_finite(self, monkeypatch):
        # Bounds how much mail one submitted address can aim at a third party.
        monkeypatch.setenv("EMAIL_VERIFICATION_MAX_SENDS", "2")
        graph = _FakeGraph([_result([])])
        with _patch_graph(graph):
            issue = await ev.start_pending_signup(
                "new@example.com", "Ada", "Lovelace", "hash"
            )

        assert not issue.issued
        _, params = graph.calls[-1]
        assert params["max_sends"] == 2


class TestRefreshPendingSignup:
    """Resending refreshes an existing signup and never invents one."""

    @pytest.mark.asyncio
    async def test_unknown_address_is_not_created(self):
        # A MERGE here would turn the resend endpoint into a way to mail an
        # address nobody ever submitted.
        graph = _FakeGraph([_result([])])
        with _patch_graph(graph):
            issue = await ev.refresh_pending_signup("nobody@example.com")

        assert not issue.issued
        assert all("MERGE" not in cypher for cypher, _ in graph.calls)

    @pytest.mark.asyncio
    async def test_a_resend_keeps_the_ticket(self):
        # A resend is another copy of the same signup. Minting a new ticket
        # would lock out the browser that is sitting on the code entry screen.
        graph = _FakeGraph([_result([["Ada", {"code_hash": "old-hash"}]])])
        with _patch_graph(graph):
            issue = await ev.refresh_pending_signup("pending@example.com")

        cypher, params = graph.calls[-1]
        assert "ticket_hash" not in cypher
        assert "ticket_hash" not in params
        assert issue.ticket is None

    @pytest.mark.asyncio
    async def test_refresh_replaces_the_previous_code(self):
        previous = {"code_hash": "old-hash", "ticket_hash": "kept", "attempts": 3}
        graph = _FakeGraph([_result([["Ada", previous]])])
        with _patch_graph(graph):
            issue = await ev.refresh_pending_signup("pending@example.com")

        assert issue.issued
        assert issue.first_name == "Ada"
        write_cypher, params = graph.calls[-1]
        assert "MATCH" in write_cypher and "MERGE" not in write_cypher
        assert params["code_hash"] == ev.hash_code(issue.code)
        assert "ELSE p.send_count + 1" in write_cypher
        # A fresh code deserves a fresh budget of guesses.
        assert "p.attempts = 0" in write_cypher
        # Kept so a send that never reaches a transport can be undone.
        assert issue.previous == previous

    @pytest.mark.asyncio
    async def test_losing_a_race_with_verification_is_not_an_error(self):
        # The record was consumed between the write and this call.
        graph = _FakeGraph([_result([])])
        with _patch_graph(graph):
            issue = await ev.refresh_pending_signup("pending@example.com")

        assert not issue.issued


class TestRevertVerificationSend:
    """Undoing a send whose mail never reached a transport."""

    @staticmethod
    def _issued():
        return ev.CodeIssue(
            code="123456",
            first_name="Ada",
            previous={
                "code_hash": "old-hash",
                "ticket_hash": "old-ticket",
                "password_hash": "someone-elses-password",
                "expires_at": 4242,
                "attempts": 3,
                "send_count": 1,
            },
        )

    @pytest.mark.asyncio
    async def test_the_record_is_put_back_exactly_as_it_was(self):
        # A transport failure must cost the user neither their send budget nor
        # the code they may already be holding. Restoring the whole map rather
        # than named fields is also what keeps the undo honest: the send
        # rewrote the password hash and the ticket too.
        graph = _FakeGraph([])
        with _patch_graph(graph):
            await ev.revert_verification_send("pending@example.com", self._issued())

        cypher, params = graph.calls[-1]
        assert "SET p = $previous" in cypher
        assert params["previous"] == self._issued().previous

    @pytest.mark.asyncio
    async def test_a_send_that_displaced_nothing_is_not_reverted(self):
        # There is no record to restore this one to. Reverting anyway would
        # write back the bare node the MERGE created, leaving a husk behind;
        # discarding it is the caller's job.
        graph = _FakeGraph([])
        with _patch_graph(graph):
            await ev.revert_verification_send(
                "new@example.com",
                ev.CodeIssue(code="123456", previous={"email": "new@example.com"}),
            )

        assert graph.calls == []

    @pytest.mark.asyncio
    async def test_a_code_issued_since_is_left_alone(self):
        # The revert only matches the hash it wrote, so it cannot clobber a
        # send that succeeded in the meantime.
        graph = _FakeGraph([])
        with _patch_graph(graph):
            await ev.revert_verification_send("pending@example.com", self._issued())

        cypher, params = graph.calls[-1]
        assert "WHERE p.code_hash = $code_hash" in cypher
        assert params["code_hash"] == ev.hash_code("123456")

    @pytest.mark.asyncio
    async def test_the_clock_is_not_rolled_back(self):
        # The snapshot would restore the old last_sent_at along with everything
        # else, and a broken transport could then be retried without limit.
        graph = _FakeGraph([])
        with _patch_graph(graph):
            await ev.revert_verification_send("pending@example.com", self._issued())

        cypher, params = graph.calls[-1]
        assert "SET p.last_sent_at = $now" in cypher
        assert params["now"] >= params["previous"].get("last_sent_at", 0)

    @pytest.mark.asyncio
    async def test_nothing_to_undo_when_nothing_was_issued(self):
        graph = _FakeGraph([])
        with _patch_graph(graph):
            await ev.revert_verification_send(
                "pending@example.com", ev.CodeIssue()
            )

        assert graph.calls == []

    @pytest.mark.asyncio
    async def test_a_failing_revert_is_swallowed(self):
        # Best-effort: the caller is already on its error path.
        graph = _FakeGraph([])
        graph.query = AsyncMock(side_effect=RuntimeError("down"))
        with _patch_graph(graph):
            await ev.revert_verification_send("pending@example.com", self._issued())


class TestConsumePendingSignup:
    """Redeeming a code, and the budget of wrong guesses."""

    @staticmethod
    def _row(expires_at):
        return [["Ada", "Lovelace", "hash", expires_at]]

    @pytest.mark.asyncio
    async def test_empty_code_never_reaches_the_database(self):
        graph = _FakeGraph([])
        with _patch_graph(graph):
            pending, result = await ev.consume_pending_signup(
                "new@example.com", "", "ticket"
            )

        assert pending is None
        assert result == ev.RESULT_INVALID
        assert not graph.calls

    @pytest.mark.asyncio
    async def test_a_code_without_a_ticket_never_reaches_the_database(self):
        # The pair is the credential. Half of it is not a partial answer, it is
        # a request from a browser that never submitted this signup.
        graph = _FakeGraph([])
        with _patch_graph(graph):
            pending, result = await ev.consume_pending_signup(
                "new@example.com", "123456", ""
            )

        assert pending is None
        assert result == ev.RESULT_INVALID
        assert not graph.calls

    @pytest.mark.asyncio
    async def test_live_code_returns_the_details_and_deletes_the_record(self):
        future = ev._now_ms() + 60_000
        graph = _FakeGraph([_result(self._row(future))])
        with _patch_graph(graph):
            pending, result = await ev.consume_pending_signup(
                "new@example.com", "123456", "ticket"
            )

        assert result == ev.RESULT_OK
        assert pending.email == "new@example.com"
        assert pending.full_name == "Ada Lovelace"
        cypher, params = graph.calls[0]
        # Single-use is structural: the read and the delete are one query, so a
        # replay cannot find the node no matter how the caller behaves.
        assert "DELETE" in cypher
        assert params["code_hash"] == ev.hash_code("123456")

    @pytest.mark.asyncio
    async def test_the_ticket_is_matched_in_the_same_query(self):
        # Otherwise re-submitting a stranger's pending signup with a password
        # of your own gets it confirmed by the address's owner.
        future = ev._now_ms() + 60_000
        graph = _FakeGraph([_result(self._row(future))])
        with _patch_graph(graph):
            await ev.consume_pending_signup("new@example.com", "123456", "ticket")

        cypher, params = graph.calls[0]
        assert "p.ticket_hash = $ticket_hash" in cypher
        assert params["ticket_hash"] == ev.hash_code("ticket")

    @pytest.mark.asyncio
    async def test_the_right_code_with_the_wrong_ticket_is_refused(self):
        # The graph matches nothing, exactly as it would for a wrong code.
        graph = _FakeGraph([_result([]), _result([])])
        with _patch_graph(graph):
            pending, result = await ev.consume_pending_signup(
                "new@example.com", "123456", "someone-elses-ticket"
            )

        assert pending is None
        assert result == ev.RESULT_INVALID

    @pytest.mark.asyncio
    async def test_the_attempt_limit_is_enforced_inside_the_write(self):
        # Reading the counter first would let a burst of concurrent guesses all
        # pass a check that only one increment ever answered for.
        future = ev._now_ms() + 60_000
        graph = _FakeGraph([_result(self._row(future))])
        with _patch_graph(graph):
            await ev.consume_pending_signup("new@example.com", "123456", "ticket")

        cypher, params = graph.calls[0]
        assert "p.attempts < $max_attempts" in cypher
        assert params["max_attempts"] == ev.max_attempts()

    @pytest.mark.asyncio
    async def test_a_wrong_code_is_charged_for(self):
        # Six digits are only enough while the number of guesses is small.
        graph = _FakeGraph([_result([]), _result([])])
        with _patch_graph(graph):
            pending, result = await ev.consume_pending_signup(
                "new@example.com", "000000", "ticket"
            )

        assert pending is None
        assert result == ev.RESULT_INVALID
        charge_cypher, _ = graph.calls[-1]
        assert "p.attempts = p.attempts + 1" in charge_cypher

    @pytest.mark.asyncio
    async def test_running_out_of_guesses_destroys_the_signup(self):
        # Guessing has to end somewhere, and ending it by deleting the record
        # costs the attacker their target while the user just signs up again.
        graph = _FakeGraph([_result([]), _result([[5]])])
        with _patch_graph(graph):
            await ev.consume_pending_signup("new@example.com", "000000", "ticket")

        charge_cypher, params = graph.calls[-1]
        assert "attempts >= $max_attempts" in charge_cypher
        assert "DELETE p" in charge_cypher
        assert params["max_attempts"] == ev.max_attempts()

    @pytest.mark.asyncio
    async def test_a_failing_charge_is_not_a_free_retry_signal(self):
        # The guess still fails; only the bookkeeping is best-effort.
        graph = _FakeGraph([_result([])])
        graph.query = AsyncMock(
            side_effect=[_result([]), RuntimeError("db down")]
        )
        with _patch_graph(graph):
            pending, result = await ev.consume_pending_signup(
                "new@example.com", "000000", "ticket"
            )

        assert pending is None
        assert result == ev.RESULT_INVALID

    @pytest.mark.asyncio
    async def test_replayed_code_finds_nothing(self):
        graph = _FakeGraph([_result([]), _result([])])
        with _patch_graph(graph):
            pending, result = await ev.consume_pending_signup(
                "new@example.com", "123456", "ticket"
            )

        assert pending is None
        assert result == ev.RESULT_INVALID

    @pytest.mark.asyncio
    async def test_expired_code_is_reported_and_consumed(self):
        past = ev._now_ms() - 1
        graph = _FakeGraph([_result(self._row(past))])
        with _patch_graph(graph):
            pending, result = await ev.consume_pending_signup(
                "new@example.com", "123456", "ticket"
            )

        assert pending is None
        assert result == ev.RESULT_EXPIRED

    @pytest.mark.asyncio
    async def test_record_without_an_expiry_is_not_treated_as_eternal(self):
        # A missing expiry must fail closed, not read as "never expires".
        graph = _FakeGraph([_result(self._row(None))])
        with _patch_graph(graph):
            pending, result = await ev.consume_pending_signup(
                "new@example.com", "123456", "ticket"
            )

        assert pending is None
        assert result == ev.RESULT_EXPIRED

    @pytest.mark.asyncio
    async def test_record_missing_a_password_is_rejected(self):
        future = ev._now_ms() + 60_000
        graph = _FakeGraph([_result([["Ada", "Lovelace", None, future]])])
        with _patch_graph(graph):
            pending, result = await ev.consume_pending_signup(
                "new@example.com", "123456", "ticket"
            )

        assert pending is None
        assert result == ev.RESULT_INVALID


class TestDiscardPendingSignup:
    """Discarding is best-effort: it must never be the thing that fails a request."""

    @pytest.mark.asyncio
    async def test_a_failing_delete_is_swallowed(self):
        graph = MagicMock()
        graph.query = AsyncMock(side_effect=RuntimeError("db down"))
        with _patch_graph(graph):
            await ev.discard_pending_signup("new@example.com")


class TestSendVerificationCode:
    """The mail itself."""

    @pytest.mark.asyncio
    async def test_code_is_included_in_both_bodies(self):
        with patch("api.auth.email_verification.send_mail",
                   new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            sent = await ev.send_verification_code("new@example.com", "Ada", "123456")

        assert sent is True
        kwargs = mock_send.await_args.kwargs
        assert kwargs["to"] == "new@example.com"
        assert "123456" in kwargs["text_body"]
        assert "123456" in kwargs["html_body"]

    @pytest.mark.asyncio
    async def test_no_link_is_offered(self):
        # The point of a code is that nothing in the mail can be acted on by
        # someone who did not fill in the form -- including a scanner that
        # fetches every URL it sees.
        with patch("api.auth.email_verification.send_mail",
                   new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            await ev.send_verification_code("new@example.com", "Ada", "123456")

        kwargs = mock_send.await_args.kwargs
        assert "http" not in kwargs["text_body"]
        assert "<a " not in kwargs["html_body"]

    @pytest.mark.asyncio
    async def test_a_name_from_the_form_cannot_inject_markup(self):
        # The first name is attacker-controlled and lands in an HTML body.
        with patch("api.auth.email_verification.send_mail",
                   new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            await ev.send_verification_code(
                "new@example.com", "<script>alert(1)</script>", "123456"
            )

        html_body = mock_send.await_args.kwargs["html_body"]
        assert "<script>" not in html_body
        assert "&lt;script&gt;" in html_body
