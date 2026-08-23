"""Application-level deadline for a blocking database connection.

Driver and TCP settings do not cover every stall. A server-side
``statement_timeout`` only fires while the backend is processing our query;
``tcp_user_timeout`` bounds *unacknowledged outbound data*; keepalives only
detect a dead TCP peer. A stalled backend or a proxy that keeps the connection
alive without answering satisfies all three while the client stays blocked in a
read — holding a worker thread that cancellation cannot reclaim.

This closes that gap from the outside: a timer asks the server to cancel the
in-flight query and, failing that, shuts the connection's socket down at the OS
level, which makes the blocked read raise in the worker so the thread is
released.

The escalation must not itself be blockable by the stall it exists to break:

* ``conn.cancel()`` (PQcancel) opens its *own* connection to the server, so
  against a black-holed host the cancel itself can hang. It therefore runs on
  a dedicated daemon timer thread that nothing waits for — a hanging cancel
  costs one parked thread until the kernel gives up, never the escalation.
* ``conn.close()`` is not usable from another thread while a query is running:
  psycopg2 serialises connection access with an internal lock that the worker
  blocked in ``recv`` is holding, so a close from the timer thread would join
  the deadlock instead of breaking it. The escalation instead calls
  ``shutdown(2)`` on the underlying socket via a duplicated file descriptor —
  a plain syscall that needs no driver lock and no network round trip. The
  kernel fails the pending read immediately, the driver raises in the worker,
  and the connection is then closed by the worker's own cleanup path, which
  holds the lock legitimately.
"""

import contextlib
import logging
import os
import socket
import threading

# How long to wait for a cooperative cancel before shutting the socket down.
_CANCEL_GRACE_SECONDS = 5.0


def _cancel(conn, label: str) -> None:
    """Ask the server to abort the running statement, if the driver can.

    Best-effort only: this may hang (see the module docstring), and the
    escalation to ``_shutdown`` does not depend on it returning.
    """
    cancel = getattr(conn, "cancel", None)
    if cancel is None:
        return
    logging.warning("%s exceeded its deadline; cancelling the query", label)
    try:
        cancel()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # PQcancel opens its own connection to the server, so it can fail when
        # the server is unreachable. The socket shutdown is the fallback.
        logging.warning("%s cancel failed (%s); the socket shutdown will follow",
                        label, type(exc).__name__)


def _connection_fd(conn):
    """The connection's socket descriptor, or ``None`` if it has none."""
    fileno = getattr(conn, "fileno", None)
    if fileno is None:
        return None
    try:
        fd = fileno()
    except Exception:  # pylint: disable=broad-exception-caught
        # e.g. psycopg2.InterfaceError once the connection is already closed.
        return None
    return fd if isinstance(fd, int) and fd >= 0 else None


def _duplicate_socket(conn):
    """A second handle on the connection's socket, or ``None``.

    Taken while the caller still demonstrably owns the connection, so the
    deadline callback never resolves a file descriptor at fire time — a
    descriptor number can be closed and reused by an unrelated file between
    those two moments, and a shutdown aimed by number could then hit it. The
    duplicate is an object handle on the *socket itself*: after ``close`` it
    refuses further use instead of chasing a recycled number.
    """
    fd = _connection_fd(conn)
    if fd is None:
        return None
    try:
        return socket.socket(fileno=os.dup(fd))
    except OSError:
        return None


def _shutdown(dup: socket.socket, label: str) -> None:
    """Make the blocked read raise, without asking the driver for anything.

    ``shutdown`` acts on the socket, which the driver's descriptor and this
    duplicate share, so the worker's pending ``recv`` fails at once — no
    driver lock, no network round trip, nothing on this path can block.
    """
    try:
        dup.shutdown(socket.SHUT_RDWR)
        logging.warning("%s deadline exceeded; socket shut down so the blocked "
                        "call raises", label)
    except OSError as exc:
        # ENOTCONN and the like: the peer (or the guard's own exit, which
        # closes the duplicate) beat us to it — the outcome we wanted anyway.
        logging.warning("%s socket shutdown after deadline was a no-op: %s",
                        label, type(exc).__name__)


def _close(conn, label: str) -> None:
    """Driver-level close, for connections that expose no socket."""
    try:
        conn.close()
        logging.warning("%s deadline exceeded; connection closed", label)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logging.warning("%s close after deadline failed: %s",
                        label, type(exc).__name__)


@contextlib.contextmanager
def deadline_guard(conn, seconds: float, label: str = "database call"):
    """Cancel, then shut down, *conn* if the body outlives *seconds*.

    The guard is what makes the configured deadline real for a connection whose
    peer has stopped answering but has not dropped the socket. Both escalation
    steps run on their own daemon timer threads and neither waits for the
    other, so a step that itself hangs cannot postpone the next one.
    """
    if not seconds or seconds <= 0:
        yield
        return

    dup = _duplicate_socket(conn)
    if dup is not None:
        # The normal case: escalate by shutting the shared socket down.
        escalate, escalate_args = _shutdown, (dup, label)
    else:
        # No reachable socket (a driver that exposes none, or a test fake):
        # the driver-level close is all that is left. It can block on the
        # driver's connection lock, which is exactly why the socket path is
        # preferred whenever it exists.
        escalate, escalate_args = _close, (conn, label)

    cancel_timer = threading.Timer(seconds, _cancel, args=(conn, label))
    shutdown_timer = threading.Timer(
        seconds + _CANCEL_GRACE_SECONDS, escalate, args=escalate_args
    )
    cancel_timer.daemon = True
    shutdown_timer.daemon = True
    cancel_timer.start()
    shutdown_timer.start()
    try:
        yield
    finally:
        cancel_timer.cancel()
        shutdown_timer.cancel()
        if dup is not None:
            # Closing the duplicate also disarms a shutdown callback that
            # already started: the socket object refuses use after close, so
            # a late timer cannot touch whatever the kernel reuses the
            # descriptor number for.
            dup.close()
