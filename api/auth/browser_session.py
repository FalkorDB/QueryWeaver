"""The browser login session — QueryWeaver's own user session, free of FalkorDB.

QueryWeaver deals with three independent credentials. This module owns exactly
one of them:

1. **Browser login** (this module) — who the person at the keyboard is. Proven
   once by an OAuth provider or a password, then carried in the signed Starlette
   session cookie. Validating it is pure signature and expiry checking, so it
   keeps working while FalkorDB is unreachable.
2. **API tokens** — opaque tokens for programmatic clients, stored as ``Token``
   nodes in the Organizations graph. See :mod:`api.auth.user_management`.
3. **Data-source credentials** — the user's PostgreSQL/MySQL/Snowflake URL,
   supplied per request and only exercised when a schema is loaded or a query
   runs.

Nothing here imports :mod:`api.extensions`; that separation is the whole point.
The session cookie is signed (not encrypted) with ``FASTAPI_SECRET_KEY``, so it
may only ever carry the profile the UI already shows back to its own owner —
never secrets, password hashes or data-source credentials.
"""

import logging
import os
import time
from typing import Any, Dict, Optional

from fastapi import Request

# Key under which the login payload lives inside the Starlette session dict.
SESSION_KEY = "browser_login"

# Bumped whenever the payload shape changes, so old cookies are ignored rather
# than misread.
SESSION_VERSION = 1

# Matches the 24h expiry of the ``Token`` nodes this session replaces, so the
# change does not silently extend how long a login lasts.
DEFAULT_TTL_HOURS = 24


def session_ttl_seconds() -> int:
    """Browser login lifetime, from ``BROWSER_SESSION_TTL_HOURS``."""
    raw = os.getenv("BROWSER_SESSION_TTL_HOURS")
    if raw:
        try:
            hours = float(raw)
            if hours > 0:
                return int(hours * 3600)
            logging.warning("BROWSER_SESSION_TTL_HOURS must be positive, ignoring %r", raw)
        except ValueError:
            logging.warning("Invalid BROWSER_SESSION_TTL_HOURS value %r, ignoring", raw)
    return DEFAULT_TTL_HOURS * 3600


def _session_store(request: Request) -> Optional[Dict[str, Any]]:
    """Return the Starlette session dict, or ``None`` when unavailable.

    ``request.session`` asserts when ``SessionMiddleware`` is not installed,
    which happens for ASGI sub-apps and in unit tests.
    """
    try:
        return request.session
    except (AssertionError, AttributeError):
        return None


def establish_browser_session(  # pylint: disable=too-many-arguments
    request: Request,
    *,
    email: str,
    name: Optional[str] = None,
    picture: Optional[str] = None,
    provider: str,
    provider_user_id: Optional[str] = None,
    provisioned: bool = False,
) -> bool:
    """Log the user in for this browser. Returns ``False`` if it could not be set.

    ``provisioned`` records whether the matching Organizations-graph write
    succeeded, so a login that happened during an outage can be completed later.
    """
    store = _session_store(request)
    if store is None:
        logging.error("Cannot establish browser session: SessionMiddleware is not installed")
        return False
    if not email:
        # ``token_required`` derives the user id from the email; without one
        # there is no usable identity to log in as.
        logging.error("Cannot establish browser session for provider %s: no email", provider)
        return False

    store[SESSION_KEY] = {
        "v": SESSION_VERSION,
        "email": email,
        "name": name,
        "picture": picture,
        "provider": provider,
        "sub": str(provider_user_id) if provider_user_id is not None else None,
        "exp": int(time.time()) + session_ttl_seconds(),
        "provisioned": bool(provisioned),
    }
    return True


def read_browser_session(request: Request) -> Optional[Dict[str, Any]]:
    """Return the logged-in user, or ``None``. Never touches the database."""
    store = _session_store(request)
    if not store:
        return None

    payload = store.get(SESSION_KEY)
    if not isinstance(payload, dict) or payload.get("v") != SESSION_VERSION:
        return None

    email = payload.get("email")
    expires_at = payload.get("exp")
    if not email or not isinstance(expires_at, (int, float)):
        return None

    if time.time() >= expires_at:
        store.pop(SESSION_KEY, None)
        return None

    return {
        "id": payload.get("sub"),
        "email": email,
        "name": payload.get("name"),
        "picture": payload.get("picture"),
        "provider": payload.get("provider"),
    }


def clear_browser_session(request: Request) -> None:
    """Log the user out of this browser."""
    store = _session_store(request)
    if store is not None:
        store.pop(SESSION_KEY, None)


def is_provisioned(request: Request) -> bool:
    """Whether this login's Organizations-graph record is known to exist."""
    store = _session_store(request)
    payload = store.get(SESSION_KEY) if store else None
    return bool(isinstance(payload, dict) and payload.get("provisioned"))


def mark_provisioned(request: Request) -> None:
    """Record that the Organizations-graph write for this login has landed."""
    store = _session_store(request)
    payload = store.get(SESSION_KEY) if store else None
    if isinstance(payload, dict):
        payload["provisioned"] = True
        # Reassign so Starlette re-serialises the mutated payload.
        store[SESSION_KEY] = payload
