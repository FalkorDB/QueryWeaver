"""Custom exceptions for the text2sql API."""

import redis.exceptions

# Interal Error Exception
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
# something that will never succeed. ``OSError`` covers the builtin
# ``ConnectionError``/``TimeoutError`` and socket resolution failures.
TRANSIENT_BACKEND_ERRORS = (
    OSError,
    redis.exceptions.ConnectionError,
    redis.exceptions.TimeoutError,
)
