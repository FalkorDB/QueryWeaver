"""Application-level deadline for a blocking database connection.

Driver and TCP settings do not cover every stall. A server-side
``statement_timeout`` only fires while the backend is processing our query;
``tcp_user_timeout`` bounds *unacknowledged outbound data*; keepalives only
detect a dead TCP peer. A stalled backend or a proxy that keeps the connection
alive without answering satisfies all three while the client stays blocked in a
read — holding a worker thread that cancellation cannot reclaim.

This closes that gap from the outside: a timer cancels the in-flight query and,
failing that, closes the connection, which makes the blocked read raise in the
worker so the thread is released.
"""

import contextlib
import logging
import threading

# How long to wait for a cooperative cancel before closing the socket.
_CANCEL_GRACE_SECONDS = 5.0


def _cancel(conn, label: str) -> None:
    """Ask the server to abort the running statement, if the driver can."""
    cancel = getattr(conn, "cancel", None)
    if cancel is None:
        return
    try:
        cancel()
        logging.warning("%s exceeded its deadline; cancelling the query", label)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # PQcancel opens its own connection to the server, so it can fail or
        # hang when the server is unreachable. The close below is the fallback.
        logging.warning("%s cancel failed (%s); will close the connection",
                        label, type(exc).__name__)


def _close(conn, label: str) -> None:
    """Force the socket shut so a blocked read raises instead of hanging."""
    try:
        conn.close()
        logging.warning("%s deadline exceeded; connection closed", label)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logging.warning("%s close after deadline failed: %s",
                        label, type(exc).__name__)


@contextlib.contextmanager
def deadline_guard(conn, seconds: float, label: str = "database call"):
    """Cancel, then close, *conn* if the body outlives *seconds*.

    The guard is what makes the configured deadline real for a connection whose
    peer has stopped answering but has not dropped the socket.
    """
    if not seconds or seconds <= 0:
        yield
        return

    cancel_timer = threading.Timer(seconds, _cancel, args=(conn, label))
    close_timer = threading.Timer(
        seconds + _CANCEL_GRACE_SECONDS, _close, args=(conn, label)
    )
    cancel_timer.daemon = True
    close_timer.daemon = True
    cancel_timer.start()
    close_timer.start()
    try:
        yield
    finally:
        cancel_timer.cancel()
        close_timer.cancel()
