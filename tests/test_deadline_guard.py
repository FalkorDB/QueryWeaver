"""The application-level deadline that driver settings cannot provide.

A server-side ``statement_timeout`` only fires while the backend is answering,
``tcp_user_timeout`` bounds unacknowledged outbound data, and keepalives only
detect a dead TCP peer. A stalled backend or proxy satisfies all three while the
client stays blocked in a read, holding a worker thread that cancellation cannot
reclaim. The guard cancels and then shuts the socket down, so the read raises.

The enforcement itself must not be blockable by the stall it breaks: psycopg2
holds a connection lock during a blocking read, so ``close()`` from another
thread deadlocks, and ``cancel()`` (PQcancel) can hang against a black-holed
server. The tests below reproduce both against a real blocked socket read.
"""

import os
import socket
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
def test_guard_escalates_a_stalled_call():
    conn = _Conn()

    with deadline.deadline_guard(conn, 0.1, "probe"):
        # Stands in for a read that never returns.
        assert conn.closed.wait(timeout=2), "deadline did not release the call"


@pytest.mark.unit
def test_guard_never_calls_the_drivers_cancel():
    """PQcancel is deliberately unused.

    It opens its own connection to the server, so against a black-holed host it
    hangs — and psycopg2 does not release the GIL around it, which stalls every
    Python thread in the process, the event loop included. A separate timer
    thread is no protection: a thread that cannot take the GIL cannot run.
    """
    conn = _Conn()

    with deadline.deadline_guard(conn, 0.1, "probe"):
        assert conn.closed.wait(timeout=2), "deadline did not release the call"

    assert not conn.cancelled.is_set(), (
        "cancel was invoked in-process; a hanging PQcancel would freeze every "
        "thread, including the streams this deadline exists to protect"
    )


@pytest.mark.unit
def test_guard_leaves_a_prompt_call_alone():
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


class _SocketConn:
    """Fake driver connection over a real socket, with psycopg2's locking.

    ``close()`` takes the same lock the worker holds while blocked in ``recv``,
    which is exactly why the guard must not go through ``close()`` to break a
    stall — this fake deadlocks if it tries.
    """

    def __init__(self, sock, lock, cancel_hangs=False):
        self._sock = sock
        self._lock = lock
        self._cancel_hangs = cancel_hangs
        self._cancel_release = threading.Event()
        self.cancelled = threading.Event()

    def fileno(self):
        return self._sock.fileno()

    def cancel(self):
        self.cancelled.set()
        if self._cancel_hangs:
            # PQcancel against a black-holed server: a blocking connect with
            # no timeout of ours to bound it.
            self._cancel_release.wait(timeout=5)

    def close(self):
        with self._lock:  # would deadlock while the worker is blocked
            self._sock.close()

    def release_cancel(self):
        self._cancel_release.set()


def _blocked_reader(sock, lock, released):
    """A worker blocked in a socket read, holding the driver lock."""

    def worker():
        with lock:
            try:
                sock.recv(1)  # the peer never answers
            except OSError:
                pass
            released.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    # Don't start the deadline until the worker actually holds the lock.
    while not lock.locked():
        time.sleep(0.001)
    return thread


@pytest.mark.unit
def test_guard_releases_a_read_that_close_would_deadlock_on():
    """The reported freeze: the worker blocked in recv holds the driver lock,
    so a close() from the timer thread would join the deadlock. The socket
    shutdown must free the worker anyway."""
    left, right = socket.socketpair()
    lock = threading.Lock()
    conn = _SocketConn(left, lock)
    released = threading.Event()

    try:
        _blocked_reader(left, lock, released)
        with deadline.deadline_guard(conn, 0.1, "probe"):
            assert released.wait(timeout=5), "the blocked read was never released"
        assert not conn.cancelled.is_set(), "cancel must not be attempted"
    finally:
        right.close()
        with lock:
            left.close()


@pytest.mark.unit
def test_guard_escalates_on_the_deadline_alone():
    """The deadline is the whole clock: nothing cooperative precedes it.

    An earlier version cancelled first and shut the socket down only after a
    grace period, which made the real release time depend on how long PQcancel
    took — and a GIL-holding cancel could postpone it indefinitely.
    """
    left, right = socket.socketpair()
    lock = threading.Lock()
    conn = _SocketConn(left, lock, cancel_hangs=True)
    released = threading.Event()

    try:
        _blocked_reader(left, lock, released)
        started = time.monotonic()
        with deadline.deadline_guard(conn, 0.1, "probe"):
            assert released.wait(timeout=5), "the blocked read was never released"
        elapsed = time.monotonic() - started
        assert elapsed < 1.0, f"release took {elapsed:.2f}s for a 0.1s deadline"
        assert not conn.cancelled.is_set(), "cancel must not be attempted"
    finally:
        conn.release_cancel()
        right.close()
        with lock:
            left.close()


@pytest.mark.unit
def test_guard_shutdown_leaves_the_drivers_descriptor_valid():
    """shutdown(2) runs on a duplicated descriptor: the socket dies, but the
    driver's own fd must stay valid for its cleanup path to close."""
    left, right = socket.socketpair()
    lock = threading.Lock()
    conn = _SocketConn(left, lock)
    released = threading.Event()

    try:
        _blocked_reader(left, lock, released)
        with deadline.deadline_guard(conn, 0.1, "probe"):
            assert released.wait(timeout=5)
        os.fstat(left.fileno())  # raises if the guard closed the driver's fd
    finally:
        right.close()
        with lock:
            left.close()


@pytest.mark.unit
def test_guard_falls_back_to_close_without_a_socket():
    """A connection that exposes no usable descriptor still gets closed."""

    class _NoFdConn(_Conn):
        def fileno(self):
            raise RuntimeError("connection already closed")

    conn = _NoFdConn()
    with deadline.deadline_guard(conn, 0.1, "probe"):
        assert conn.closed.wait(timeout=2), "close fallback did not run"
