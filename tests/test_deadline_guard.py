"""The application-level deadline that driver settings cannot provide.

A server-side ``statement_timeout`` only fires while the backend is answering,
``tcp_user_timeout`` bounds unacknowledged outbound data, and keepalives only
detect a dead TCP peer. A stalled backend or proxy satisfies all three while the
client stays blocked in a read, holding a worker thread that cancellation cannot
reclaim. The guard cancels and then closes, so the read raises.
"""

import threading
import time

import pytest

# One import style: the module object is needed anyway, because the tests
# monkeypatch its grace constant.
from api.loaders import deadline


class _Conn:
    """Records what the guard did to it."""

    def __init__(self, cancel_raises=False):
        self.cancelled = threading.Event()
        self.closed = threading.Event()
        self._cancel_raises = cancel_raises

    def cancel(self):
        self.cancelled.set()
        if self._cancel_raises:
            raise OSError("server unreachable")

    def close(self):
        self.closed.set()


@pytest.mark.unit
def test_guard_cancels_then_closes_a_stalled_call(monkeypatch):
    monkeypatch.setattr(deadline, "_CANCEL_GRACE_SECONDS", 0.15)
    conn = _Conn()

    with deadline.deadline_guard(conn, 0.1, "probe"):
        # Stands in for a read that never returns.
        assert conn.cancelled.wait(timeout=2), "deadline did not cancel the query"
        assert conn.closed.wait(timeout=2), "deadline did not close the connection"


@pytest.mark.unit
def test_guard_closes_even_when_cancel_fails(monkeypatch):
    """PQcancel opens its own connection, so it can fail on an unreachable server."""
    monkeypatch.setattr(deadline, "_CANCEL_GRACE_SECONDS", 0.15)
    conn = _Conn(cancel_raises=True)

    with deadline.deadline_guard(conn, 0.1, "probe"):
        assert conn.closed.wait(timeout=2), "close fallback did not run"


@pytest.mark.unit
def test_guard_leaves_a_prompt_call_alone(monkeypatch):
    monkeypatch.setattr(deadline, "_CANCEL_GRACE_SECONDS", 0.1)
    conn = _Conn()

    with deadline.deadline_guard(conn, 5.0, "probe"):
        time.sleep(0.05)

    time.sleep(0.2)
    assert not conn.cancelled.is_set(), "cancelled a call that finished in time"
    assert not conn.closed.is_set(), "closed a call that finished in time"


@pytest.mark.unit
@pytest.mark.parametrize("seconds", [0, None, -1])
def test_guard_is_a_noop_without_a_deadline(seconds):
    conn = _Conn()
    with deadline.deadline_guard(conn, seconds, "probe"):
        pass
    assert not conn.cancelled.is_set()
    assert not conn.closed.is_set()
