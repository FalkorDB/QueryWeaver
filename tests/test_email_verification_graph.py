"""The verification queries, run against a real FalkorDB.

The unit tests hand ``email_verification`` a fake graph, so they pin what the
module *does* with a result set but never execute a line of Cypher: a query with
a typo in it passes them all. That matters most for
``revert_verification_send``, which swallows every exception by design and would
fail silently in production while the suite stayed green.

So this file runs the real queries against a real graph and asserts on the
records they leave behind. It is one round trip per behaviour, not a second copy
of the unit tests -- what is being checked is that the Cypher is valid and means
what the module thinks it means.
"""

import os
import uuid
from unittest.mock import patch

import pytest
from falkordb.asyncio import FalkorDB

from api.auth import email_verification as ev

pytestmark = [pytest.mark.integration]


@pytest.fixture(name="graph")
async def _graph(monkeypatch):
    """A throwaway graph, so a failing test cannot poison the next one.

    Its own client, too: the one in ``api.extensions`` is built at import and
    pools connections against whichever event loop first used it, which the
    per-test loop then closes underneath it.

    The resend interval is switched off, because most of what is being checked
    here needs two sends in a row and none of it is about the clock. The test
    that *is* about the clock puts an interval back.
    """
    monkeypatch.setattr(ev, "resend_interval_seconds", lambda: 0)
    url = os.getenv("FALKORDB_URL")
    client = FalkorDB.from_url(url) if url else FalkorDB(host="localhost", port=6379)
    name = f"test_pending_signup_{uuid.uuid4().hex}"
    handle = client.select_graph(name)
    with patch("api.auth.email_verification._graph", return_value=handle):
        yield handle
    try:
        await handle.delete()
    finally:
        await client.connection.aclose()


async def _record(graph, email="new@example.com"):
    """Every property of the pending signup, or ``None`` if there is none."""
    result = await graph.query(
        "MATCH (p:PendingSignup {email: $email}) RETURN properties(p)",
        {"email": email},
    )
    return dict(result.result_set[0][0]) if result.result_set else None


class TestIssuingAndReverting:
    """The queries that write a code, and the one that takes it back."""

    @pytest.mark.asyncio
    async def test_a_signup_is_parked_with_only_hashes(self, graph):
        issue = await ev.start_pending_signup(
            "new@example.com", "Ada", "Lovelace", "password-hash"
        )

        stored = await _record(graph)
        assert stored["code_hash"] == ev.hash_code(issue.code)
        assert stored["ticket_hash"] == ev.hash_code(issue.ticket)
        assert issue.code not in stored.values()
        assert issue.ticket not in stored.values()
        assert stored["send_count"] == 1

    @pytest.mark.asyncio
    async def test_a_failed_send_puts_the_record_back_exactly(self, graph):
        first = await ev.start_pending_signup(
            "new@example.com", "Ada", "Lovelace", "her-password"
        )
        before = await _record(graph)

        # Somebody re-submits the address with a password of their own, and
        # this time the mail does not go out.
        second = await ev.start_pending_signup(
            "new@example.com", "Mal", "Lory", "his-password"
        )
        assert second.displaced
        await ev.revert_verification_send("new@example.com", second)

        after = await _record(graph)
        assert after == {**before, "last_sent_at": after["last_sent_at"]}
        assert after["last_sent_at"] >= before["last_sent_at"]

        # The point of restoring the whole record rather than the code alone:
        # the ticket and the password are hers again, so her code still works
        # and still creates *her* account.
        pending, result = await ev.consume_pending_signup(
            "new@example.com", first.code, first.ticket
        )
        assert result == ev.RESULT_OK
        assert pending.password_hash == "her-password"

    @pytest.mark.asyncio
    async def test_reverting_a_code_that_was_replaced_does_nothing(self, graph):
        stale = await ev.start_pending_signup(
            "new@example.com", "Ada", "Lovelace", "hash"
        )
        current = await ev.start_pending_signup(
            "new@example.com", "Ada", "Lovelace", "hash"
        )

        await ev.revert_verification_send("new@example.com", stale)

        # The revert matches the hash it wrote, which is no longer the one
        # stored, so the code that did go out is untouched.
        assert (await _record(graph))["code_hash"] == ev.hash_code(current.code)

    @pytest.mark.asyncio
    async def test_a_resend_keeps_the_ticket_and_replaces_the_code(self, graph):
        issue = await ev.start_pending_signup(
            "new@example.com", "Ada", "Lovelace", "hash"
        )
        before = await _record(graph)

        resent = await ev.refresh_pending_signup("new@example.com")

        after = await _record(graph)
        assert resent.first_name == "Ada"
        assert after["code_hash"] == ev.hash_code(resent.code)
        assert after["ticket_hash"] == before["ticket_hash"]
        assert after["send_count"] == 2

        # The browser waiting on the code screen holds the original ticket, and
        # the code that just arrived. Both must still work together.
        _, result = await ev.consume_pending_signup(
            "new@example.com", resent.code, issue.ticket
        )
        assert result == ev.RESULT_OK

    @pytest.mark.asyncio
    async def test_a_resend_will_not_invent_a_pending_signup(self, graph):
        issue = await ev.refresh_pending_signup("nobody@example.com")

        assert not issue.issued
        assert await _record(graph, "nobody@example.com") is None


class TestTheSendBudget:
    """The guard that rides inside the write."""

    @pytest.mark.asyncio
    async def test_sends_are_spaced_out(self, graph, monkeypatch):
        monkeypatch.setattr(ev, "resend_interval_seconds", lambda: 600)
        issued = await ev.start_pending_signup(
            "new@example.com", "Ada", "Lovelace", "hash"
        )

        refused = await ev.start_pending_signup(
            "new@example.com", "Ada", "Lovelace", "hash"
        )

        assert not refused.issued
        # Refused inside the write, so nothing moved: the live code is intact.
        assert (await _record(graph))["code_hash"] == ev.hash_code(issued.code)

    @pytest.mark.asyncio
    async def test_the_budget_runs_out(self, graph, monkeypatch):
        monkeypatch.setenv("EMAIL_VERIFICATION_MAX_SENDS", "2")

        assert (await ev.start_pending_signup("new@example.com", "A", "B", "h")).issued
        assert (await ev.start_pending_signup("new@example.com", "A", "B", "h")).issued
        assert not (
            await ev.start_pending_signup("new@example.com", "A", "B", "h")
        ).issued
        assert (await _record(graph))["send_count"] == 2

    @pytest.mark.asyncio
    async def test_an_expired_record_starts_a_fresh_budget(self, graph, monkeypatch):
        # Nothing deletes an abandoned pending signup, so without this a
        # stranger could spend an address's budget and lock it out for good.
        monkeypatch.setenv("EMAIL_VERIFICATION_MAX_SENDS", "1")
        await ev.start_pending_signup("new@example.com", "A", "B", "h")
        assert not (
            await ev.start_pending_signup("new@example.com", "A", "B", "h")
        ).issued

        await graph.query(
            "MATCH (p:PendingSignup {email: $email}) SET p.expires_at = 1",
            {"email": "new@example.com"},
        )

        assert (await ev.start_pending_signup("new@example.com", "A", "B", "h")).issued
        assert (await _record(graph))["send_count"] == 1


class TestRedeeming:
    """Spending a code, and what a wrong or late one costs."""

    @pytest.mark.asyncio
    async def test_a_code_is_single_use(self, graph):
        issue = await ev.start_pending_signup(
            "new@example.com", "Ada", "Lovelace", "hash"
        )

        _, first = await ev.consume_pending_signup(
            "new@example.com", issue.code, issue.ticket
        )
        _, replay = await ev.consume_pending_signup(
            "new@example.com", issue.code, issue.ticket
        )

        assert first == ev.RESULT_OK
        assert replay == ev.RESULT_INVALID
        assert await _record(graph) is None

    @pytest.mark.asyncio
    async def test_the_right_code_in_the_wrong_browser_is_refused(self, graph):
        issue = await ev.start_pending_signup(
            "new@example.com", "Ada", "Lovelace", "hash"
        )

        pending, result = await ev.consume_pending_signup(
            "new@example.com", issue.code, ev.generate_ticket()
        )

        assert pending is None
        assert result == ev.RESULT_INVALID
        assert await _record(graph) is not None

    @pytest.mark.asyncio
    async def test_wrong_guesses_run_out(self, graph, monkeypatch):
        monkeypatch.setenv("EMAIL_VERIFICATION_MAX_ATTEMPTS", "3")
        issue = await ev.start_pending_signup(
            "new@example.com", "Ada", "Lovelace", "hash"
        )
        wrong = "000000" if issue.code != "000000" else "111111"

        for _ in range(3):
            await ev.consume_pending_signup("new@example.com", wrong, issue.ticket)

        assert await _record(graph) is None

    @pytest.mark.asyncio
    async def test_a_late_code_leaves_the_record_for_a_resend(self, graph):
        issue = await ev.start_pending_signup(
            "new@example.com", "Ada", "Lovelace", "hash"
        )
        await graph.query(
            "MATCH (p:PendingSignup {email: $email}) SET p.expires_at = 1",
            {"email": "new@example.com"},
        )

        pending, result = await ev.consume_pending_signup(
            "new@example.com", issue.code, issue.ticket
        )

        assert pending is None
        assert result == ev.RESULT_EXPIRED
        # Still there, and still costing no guesses, so the resend button on
        # the screen the user is looking at can get them out of this.
        stored = await _record(graph)
        assert stored is not None
        assert stored["attempts"] == 0

        resent = await ev.refresh_pending_signup("new@example.com")
        _, result = await ev.consume_pending_signup(
            "new@example.com", resent.code, issue.ticket
        )
        assert result == ev.RESULT_OK

    @pytest.mark.asyncio
    async def test_discarding_removes_the_record(self, graph):
        await ev.start_pending_signup("new@example.com", "Ada", "Lovelace", "hash")

        await ev.discard_pending_signup("new@example.com")

        assert await _record(graph) is None
