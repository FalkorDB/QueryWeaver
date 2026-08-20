"""Custom exceptions for the text2sql API."""

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
