"""Tests for the pending-signup store that backs email verification.

The store is what makes "no account until the link is opened" true, so the
properties pinned here are the ones the guarantee rests on: the raw token is
never stored, a token is redeemable exactly once, and the send limits cannot be
reset by asking again.
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

    @pytest.mark.asyncio
    async def test_only_the_token_hash_is_stored(self):
        graph = _FakeGraph([_result([])])  # no existing pending record
        with _patch_graph(graph):
            issue = await ev.start_pending_signup(
                "new@example.com", "Ada", "Lovelace", "hash"
            )

        assert issue.issued
        _, params = graph.calls[-1]
        assert params["token_hash"] == ev.hash_token(issue.token)
        # A graph snapshot must not yield a working link.
        assert issue.token not in params.values()

    @pytest.mark.asyncio
    async def test_resubmitting_cannot_reset_the_send_limit(self):
        # Otherwise the rate limit is decorative: re-post the form and the
        # counter starts over.
        graph = _FakeGraph([_result([[None, 3, "Ada"]])])
        with _patch_graph(graph):
            issue = await ev.start_pending_signup(
                "new@example.com", "Ada", "Lovelace", "hash"
            )

        assert issue.issued
        _, params = graph.calls[-1]
        assert params["send_count"] == 4

    @pytest.mark.asyncio
    async def test_a_recent_send_is_throttled_rather_than_repeated(self, monkeypatch):
        monkeypatch.setenv("EMAIL_VERIFICATION_RESEND_SECONDS", "60")
        graph = _FakeGraph([_result([[ev._now_ms(), 1, "Ada"]])])
        with _patch_graph(graph):
            issue = await ev.start_pending_signup(
                "new@example.com", "Ada", "Lovelace", "hash"
            )

        assert not issue.issued
        assert issue.throttled
        # Only the read ran; nothing was written.
        assert len(graph.calls) == 1

    @pytest.mark.asyncio
    async def test_send_budget_is_finite(self, monkeypatch):
        # Bounds how much mail one submitted address can aim at a third party.
        monkeypatch.setenv("EMAIL_VERIFICATION_MAX_SENDS", "2")
        graph = _FakeGraph([_result([[None, 2, "Ada"]])])
        with _patch_graph(graph):
            issue = await ev.start_pending_signup(
                "new@example.com", "Ada", "Lovelace", "hash"
            )

        assert issue.exhausted
        assert not issue.issued


class TestRefreshPendingSignup:
    """Resending refreshes an existing signup and never invents one."""

    @pytest.mark.asyncio
    async def test_unknown_address_is_not_created(self):
        # A MERGE here would turn the resend endpoint into a way to mail an
        # address nobody ever submitted.
        graph = _FakeGraph([_result([])])
        with _patch_graph(graph):
            issue = await ev.refresh_pending_signup("nobody@example.com")

        assert issue.missing
        assert not issue.issued
        assert len(graph.calls) == 1
        assert "MERGE" not in graph.calls[0][0]

    @pytest.mark.asyncio
    async def test_refresh_replaces_the_previous_link(self):
        graph = _FakeGraph([_result([[None, 1, "Ada"]]), _result([["Ada"]])])
        with _patch_graph(graph):
            issue = await ev.refresh_pending_signup("pending@example.com")

        assert issue.issued
        assert issue.first_name == "Ada"
        write_cypher, params = graph.calls[-1]
        assert "MATCH" in write_cypher and "MERGE" not in write_cypher
        assert params["token_hash"] == ev.hash_token(issue.token)
        assert params["send_count"] == 2

    @pytest.mark.asyncio
    async def test_losing_a_race_with_verification_is_not_an_error(self):
        # The record was consumed between the read and the write.
        graph = _FakeGraph([_result([[None, 1, "Ada"]]), _result([])])
        with _patch_graph(graph):
            issue = await ev.refresh_pending_signup("pending@example.com")

        assert issue.missing
        assert not issue.issued


class TestConsumePendingSignup:
    """Redeeming a link."""

    @staticmethod
    def _row(expires_at):
        return [["new@example.com", "Ada", "Lovelace", "hash", expires_at]]

    @pytest.mark.asyncio
    async def test_empty_token_never_reaches_the_database(self):
        graph = _FakeGraph([])
        with _patch_graph(graph):
            pending, result = await ev.consume_pending_signup("")

        assert pending is None
        assert result == ev.RESULT_INVALID
        assert not graph.calls

    @pytest.mark.asyncio
    async def test_live_token_returns_the_details_and_deletes_the_record(self):
        future = ev._now_ms() + 60_000
        graph = _FakeGraph([_result(self._row(future))])
        with _patch_graph(graph):
            pending, result = await ev.consume_pending_signup("raw-token")

        assert result == ev.RESULT_OK
        assert pending.email == "new@example.com"
        assert pending.full_name == "Ada Lovelace"
        cypher, params = graph.calls[0]
        # Single-use is structural: the read and the delete are one query, so a
        # replay cannot find the node no matter how the caller behaves.
        assert "DELETE" in cypher
        assert params["token_hash"] == ev.hash_token("raw-token")

    @pytest.mark.asyncio
    async def test_replayed_token_finds_nothing(self):
        graph = _FakeGraph([_result([])])
        with _patch_graph(graph):
            pending, result = await ev.consume_pending_signup("already-used")

        assert pending is None
        assert result == ev.RESULT_INVALID

    @pytest.mark.asyncio
    async def test_expired_token_is_reported_and_consumed(self):
        past = ev._now_ms() - 1
        graph = _FakeGraph([_result(self._row(past))])
        with _patch_graph(graph):
            pending, result = await ev.consume_pending_signup("stale")

        assert pending is None
        assert result == ev.RESULT_EXPIRED

    @pytest.mark.asyncio
    async def test_record_without_an_expiry_is_not_treated_as_eternal(self):
        # A missing expiry must fail closed, not read as "never expires".
        graph = _FakeGraph([_result(self._row(None))])
        with _patch_graph(graph):
            pending, result = await ev.consume_pending_signup("malformed")

        assert pending is None
        assert result == ev.RESULT_EXPIRED

    @pytest.mark.asyncio
    async def test_record_missing_a_password_is_rejected(self):
        future = ev._now_ms() + 60_000
        graph = _FakeGraph([_result([["new@example.com", "Ada", "Lovelace", None, future]])])
        with _patch_graph(graph):
            pending, result = await ev.consume_pending_signup("malformed")

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


class TestSendVerificationLink:
    """The mail itself."""

    @pytest.mark.asyncio
    async def test_link_is_included_in_both_bodies(self):
        with patch("api.auth.email_verification.send_mail",
                   new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            sent = await ev.send_verification_link(
                "new@example.com", "Ada", "http://testserver/verify/email?token=raw"
            )

        assert sent is True
        kwargs = mock_send.await_args.kwargs
        assert kwargs["to"] == "new@example.com"
        assert "token=raw" in kwargs["text_body"]
        assert "token=raw" in kwargs["html_body"]

    @pytest.mark.asyncio
    async def test_a_name_from_the_form_cannot_inject_markup(self):
        # The first name is attacker-controlled and lands in an HTML body.
        with patch("api.auth.email_verification.send_mail",
                   new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            await ev.send_verification_link(
                "new@example.com", "<script>alert(1)</script>", "http://testserver/v"
            )

        html_body = mock_send.await_args.kwargs["html_body"]
        assert "<script>" not in html_body
        assert "&lt;script&gt;" in html_body
