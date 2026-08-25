"""Custom exceptions for the text2sql API."""

import socket

import redis.exceptions

# Internal Error Exception
class InternalError(Exception):
    """Custom exception for internal errors."""

# Graph not found Exception
class GraphNotFoundError(Exception):
    """Custom exception for graph not found errors."""

# Wrong argument Exception
class InvalidArgumentError(Exception):
    """Custom exception for invalid argument errors."""

# Auth store unreachable Exception
class AuthBackendUnavailableError(Exception):
    """Raised when the Organizations graph cannot be reached.

    Distinguishes "we could not check this credential" from "this credential is
    invalid", so callers can answer 503 instead of 401.
    """


# Faults that are plausibly transient, so retrying makes sense. Deliberately
# excludes redis.exceptions.ResponseError: a Cypher or schema fault is
# deterministic, and reporting it as a transient outage tells clients to retry
# something that will never succeed. Equally deliberately these are the
# reachability-related OSError subclasses rather than OSError itself, which
# would sweep up FileNotFoundError and PermissionError and dress a real bug up
# as an outage.
TRANSIENT_BACKEND_ERRORS = (
    ConnectionError,
    TimeoutError,
    socket.gaierror,
    redis.exceptions.ConnectionError,
    redis.exceptions.TimeoutError,
)
