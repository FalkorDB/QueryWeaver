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
import math
import os
import time
from typing import Any, Dict, Optional

from fastapi import Request

# Key under which the login payload lives inside the Starlette session dict.
SESSION_KEY = "browser_login"

# Key under which a signup awaiting its mailed code parks its ticket. Separate
# from the login: it is held before any account exists, and clearing one must
# not clear the other.
SIGNUP_TICKET_KEY = "signup_ticket"

# Bumped whenever the payload shape changes, so old cookies are ignored rather
# than misread.
SESSION_VERSION = 1

# Matches the 24h expiry of the ``Token`` nodes this session replaces, so the
# change does not silently extend how long a login lasts.
DEFAULT_TTL_HOURS = 24


def session_ttl_seconds() -> int:
    """Browser login lifetime, from ``BROWSER_SESSION_TTL_HOURS``.

    Every rejected value falls back to the default rather than raising: this is
    read while building ``SessionMiddleware`` at startup and again on every
    login, so a typo in the environment must not take the app down.
    """
    raw = os.getenv("BROWSER_SESSION_TTL_HOURS")
    if raw:
        try:
            hours = float(raw)
            # ``float`` happily parses "inf" and "1e309"; both are > 0, and
            # ``int(inf * 3600)`` raises OverflowError.
            if math.isfinite(hours) and hours > 0:
                # Guard the *computed* seconds, not the hours: 0.0002 hours
                # truncates to 0, which itsdangerous reads as "always expired"
                # and would lock every user out.
                seconds = int(hours * 3600)
                if seconds >= 1:
                    return seconds
                logging.warning(
                    "BROWSER_SESSION_TTL_HOURS=%r is under one second, ignoring", raw
                )
            else:
                logging.warning(
                    "BROWSER_SESSION_TTL_HOURS must be a positive finite number, ignoring %r", raw
                )
        except ValueError:
            logging.warning("Invalid BROWSER_SESSION_TTL_HOURS value %r, ignoring", raw)
    return DEFAULT_TTL_HOURS * 3600


def _session_store(request: Request) -> Optional[Dict[str, Any]]:
    """Return the Starlette session dict, or ``None`` when unavailable.

    ``request.session`` asserts when ``SessionMiddleware`` is not installed,
    which happens for ASGI sub-apps and in unit tests. Under ``python -O`` that
    assert is stripped and the scope lookup raises ``KeyError`` instead.
    """
    try:
        return request.session
    except (AssertionError, AttributeError, KeyError):
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
    """Return the logged-in user, or ``None``.

    Never touches the database. It does drop an expired payload from the session
    so the stale cookie is not re-signed on every subsequent response.
    """
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


def remember_signup_ticket(request: Request, *, email: str, ticket: str) -> None:
    """Hold the ticket for a signup this browser just started.

    Not a login -- there is no account yet. It is the browser's half of the
    pending signup, and it lives here rather than in the graph because that is
    exactly what it has to prove: that the caller redeeming the mailed code is
    the same browser that submitted the password being redeemed. One at a time
    is enough; a second signup in the same browser replaces the first.

    Storing it in a signed-but-readable cookie is fine. It is a capability of
    the browser it was handed to, so its owner reading it learns nothing they
    did not already have, and it is worthless without the code that was mailed.
    """
    store = _session_store(request)
    if store is None:
        logging.error("Cannot hold a signup ticket: SessionMiddleware is not installed")
        return
    store[SIGNUP_TICKET_KEY] = {"email": email, "ticket": ticket}


def read_signup_ticket(request: Request, *, email: str) -> Optional[str]:
    """Return this browser's ticket for ``email``, or ``None``."""
    store = _session_store(request)
    payload = store.get(SIGNUP_TICKET_KEY) if store else None
    if not isinstance(payload, dict) or payload.get("email") != email:
        return None
    ticket = payload.get("ticket")
    return ticket if isinstance(ticket, str) and ticket else None


def forget_signup_ticket(request: Request) -> None:
    """Drop any held signup ticket. The code it belonged to is spent."""
    store = _session_store(request)
    if store is not None:
        store.pop(SIGNUP_TICKET_KEY, None)
