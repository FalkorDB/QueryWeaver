"""Signup email verification -- the holding pen for accounts that do not exist yet.

Signing up does not create a user. It records the submitted details on a
``PendingSignup`` node and mails a link; clicking that link is what creates the
``User`` and ``Identity`` and logs the browser in. An address that is never
confirmed therefore never becomes an account at all -- nothing to count, nothing
to log in as, nothing to clean up beyond an expiring node.

That ordering is what makes the guarantee cheap. There is no ``email_verified``
flag to check at every call site and no half-real user for the org graph,
analytics or quota logic to trip over, because an unverified address is simply
absent from the account graph.

The link carries a 256-bit random token. Only its SHA-256 is stored, so a
snapshot of the graph does not yield a working link -- the same reasoning that
keeps passwords hashed. Plain SHA-256 rather than a slow KDF is deliberate and
sufficient here: the input is full-entropy random, so there is no dictionary to
grind and nothing for a work factor to buy.

Tokens are single-use (consuming one deletes the node) and expiring, and sends
are rate-limited per address so the endpoint cannot be used to mail-bomb a third
party.
"""

import hashlib
import html
import logging
import os
import secrets
import time
from dataclasses import dataclass
from typing import Optional, Tuple

from api.config import ORGANIZATIONS_GRAPH
from api.extensions import db
from api.mail import send_mail

# Long enough to survive a link sitting in an inbox overnight, short enough that
# an intercepted mail does not stay useful.
DEFAULT_TTL_HOURS = 24

# Minimum gap between two sends to one address.
DEFAULT_RESEND_INTERVAL_SECONDS = 60

# Total sends allowed for one pending signup, resend included. Bounds how much
# mail a single submitted address can generate.
DEFAULT_MAX_SENDS = 5

# Outcomes of redeeming a token, kept as constants so routes and tests agree on
# the spelling.
RESULT_OK = "ok"
RESULT_INVALID = "invalid"
RESULT_EXPIRED = "expired"


@dataclass(frozen=True)
class PendingSignup:
    """The details captured at signup, replayed when the link is clicked."""

    email: str
    first_name: str
    last_name: str
    password_hash: str

    @property
    def full_name(self) -> str:
        """Display name, matching the format the signup route stored."""
        return f"{self.first_name} {self.last_name}".strip()


@dataclass(frozen=True)
class TokenIssue:
    """The result of asking for a verification link.

    ``token`` is the only time the raw value exists outside the mail; the graph
    keeps just its hash. ``throttled`` and ``exhausted`` are separated so the
    caller can tell "come back in a minute" from "stop asking".

    The ``previous_*`` fields are what the link this one displaced looked like,
    so ``revert_verification_send`` can put it back if the mail never goes out.
    """

    token: Optional[str] = None
    first_name: Optional[str] = None
    throttled: bool = False
    exhausted: bool = False
    missing: bool = False
    previous_token_hash: Optional[str] = None
    previous_expires_at: Optional[int] = None

    @property
    def issued(self) -> bool:
        """Whether a link was actually produced."""
        return self.token is not None


def _positive_int_env(name: str, default: int) -> int:
    """Read a positive integer setting, falling back on anything unusable."""
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value > 0:
        return value
    logging.warning("Invalid %s value %r, using %s", name, raw, default)
    return default


def token_ttl_seconds() -> int:
    """How long a verification link stays valid."""
    return _positive_int_env("EMAIL_VERIFICATION_TTL_HOURS", DEFAULT_TTL_HOURS) * 3600


def resend_interval_seconds() -> int:
    """Minimum gap between two sends to the same address."""
    return _positive_int_env(
        "EMAIL_VERIFICATION_RESEND_SECONDS", DEFAULT_RESEND_INTERVAL_SECONDS
    )


def max_sends() -> int:
    """Total sends allowed for a single pending signup."""
    return _positive_int_env("EMAIL_VERIFICATION_MAX_SENDS", DEFAULT_MAX_SENDS)


def _now_ms() -> int:
    """Wall-clock milliseconds, matching the units Cypher's ``timestamp()`` uses."""
    return int(time.time() * 1000)


def hash_token(token: str) -> str:
    """Hash a raw token for storage and lookup."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _graph():
    """The Organizations graph, where identity records live."""
    return db.select_graph(ORGANIZATIONS_GRAPH)


async def _read_send_state(email: str) -> Tuple[Optional[int], int, Optional[str]]:
    """Return ``(last_sent_at, send_count, first_name)`` for a pending signup."""
    result = await _graph().query(
        """
        MATCH (p:PendingSignup {email: $email})
        RETURN p.last_sent_at AS last_sent_at,
               p.send_count AS send_count,
               p.first_name AS first_name
        """,
        {"email": email},
    )
    if not result.result_set:
        return None, 0, None
    last_sent_at, send_count, first_name = result.result_set[0]
    return last_sent_at, int(send_count or 0), first_name


# The guard the two issuing queries share. It rides along in the write itself
# rather than being checked first: a single Cypher query is atomic and writes to
# one graph are serialised, so checking separately would let two concurrent
# requests both pass the check and both send while the counter advanced once.
_SEND_ALLOWED = """
        WHERE p.send_count < $max_sends
          AND (p.last_sent_at IS NULL OR $now - p.last_sent_at >= $interval_ms)
"""

# Creates the pending signup if it is new, then replaces its details and issues
# a link -- but only for a node the guard lets through. A node created by this
# very query starts at zero sends, so it always passes.
_START_SIGNUP = (
    """
        MERGE (p:PendingSignup {email: $email})
        ON CREATE SET p.created_at = $now, p.send_count = 0
        WITH p
"""
    + _SEND_ALLOWED
    + """
        SET p.token_hash = $token_hash,
            p.first_name = $first_name,
            p.last_name = $last_name,
            p.password_hash = $password_hash,
            p.expires_at = $expires_at,
            p.last_sent_at = $now,
            p.send_count = p.send_count + 1
        RETURN p.send_count AS send_count
"""
)

# Refresh only: never MERGE, so the resend endpoint cannot conjure a pending
# signup for an address nobody submitted.
_REFRESH_SIGNUP = (
    """
        MATCH (p:PendingSignup {email: $email})
"""
    + _SEND_ALLOWED
    + """
        WITH p,
             p.token_hash AS previous_token_hash,
             p.expires_at AS previous_expires_at
        SET p.token_hash = $token_hash,
            p.expires_at = $expires_at,
            p.last_sent_at = $now,
            p.send_count = p.send_count + 1
        RETURN p.first_name AS first_name,
               previous_token_hash,
               previous_expires_at
"""
)

# Undoes one send. Matching on the hash this send wrote makes it a no-op if
# another request has since issued a link of its own.
_REVERT_SEND = """
        MATCH (p:PendingSignup {email: $email})
        WHERE p.token_hash = $token_hash
        SET p.token_hash = $previous_token_hash,
            p.expires_at = $previous_expires_at,
            p.send_count = p.send_count - 1
"""


def _throttle_params(now: int) -> dict:
    """The parameters ``_SEND_ALLOWED`` reads."""
    return {
        "now": now,
        "max_sends": max_sends(),
        "interval_ms": resend_interval_seconds() * 1000,
    }


async def _classify_refusal(email: str) -> TokenIssue:
    """Say why the guard rejected a send. Only ever reports, never decides."""
    last_sent_at, send_count, first_name = await _read_send_state(email)
    if last_sent_at is None and send_count == 0 and first_name is None:
        return TokenIssue(missing=True)
    if send_count >= max_sends():
        return TokenIssue(exhausted=True)
    return TokenIssue(throttled=True)


async def start_pending_signup(
    email: str, first_name: str, last_name: str, password_hash: str
) -> TokenIssue:
    """Record a signup awaiting verification and return its link token.

    Re-submitting the form for an address that is already pending replaces the
    stored details and invalidates the previous link, so the most recent attempt
    is the one that works. The send counter deliberately survives that replace:
    otherwise resubmitting would reset the rate limit and defeat it.
    """
    now = _now_ms()
    token = secrets.token_urlsafe(32)
    result = await _graph().query(
        _START_SIGNUP,
        {
            "email": email,
            "token_hash": hash_token(token),
            "first_name": first_name,
            "last_name": last_name,
            "password_hash": password_hash,
            "expires_at": now + token_ttl_seconds() * 1000,
            **_throttle_params(now),
        },
    )
    if not result.result_set:
        return await _classify_refusal(email)

    return TokenIssue(token=token, first_name=first_name)


async def refresh_pending_signup(email: str) -> TokenIssue:
    """Issue a fresh link for an existing pending signup.

    Only ever refreshes; it will not create a pending signup, so the resend
    endpoint cannot be used to send mail to an address nobody submitted.
    """
    now = _now_ms()
    token = secrets.token_urlsafe(32)
    result = await _graph().query(
        _REFRESH_SIGNUP,
        {
            "email": email,
            "token_hash": hash_token(token),
            "expires_at": now + token_ttl_seconds() * 1000,
            **_throttle_params(now),
        },
    )
    if not result.result_set:
        # No pending signup, one that has used up its sends, or one that was
        # sent to a moment ago. Also covers losing a race with a verification
        # that just consumed the record.
        return await _classify_refusal(email)

    first_name, previous_token_hash, previous_expires_at = result.result_set[0]
    return TokenIssue(
        token=token,
        first_name=first_name,
        previous_token_hash=previous_token_hash,
        previous_expires_at=previous_expires_at,
    )


async def revert_verification_send(email: str, issue: TokenIssue) -> None:
    """Give back a send whose mail never left. Best-effort; never fatal.

    Refunds the counter and puts the displaced link back in force, so a
    transport failure costs the user neither their send budget nor the link
    they may already be holding. ``last_sent_at`` is deliberately left where
    the failed attempt put it: retries stay one per interval even when they
    fail, which is what stops a broken transport from being hammered.
    """
    if not issue.issued:
        return
    try:
        await _graph().query(
            _REVERT_SEND,
            {
                "email": email,
                "token_hash": hash_token(issue.token),
                "previous_token_hash": issue.previous_token_hash,
                "previous_expires_at": issue.previous_expires_at,
            },
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        logging.warning("Could not revert a failed verification send: %s", e)


async def consume_pending_signup(token: str) -> Tuple[Optional[PendingSignup], str]:
    """Redeem a verification token exactly once.

    Returns ``(pending, RESULT_OK)`` when the token was live. The node is
    deleted in the same query that reads it, so a replayed link finds nothing --
    that, not a flag, is what makes the token single-use.

    Lookup is by token *hash*, an exact match on a stored value, so there is no
    secret-dependent comparison here for timing to leak.
    """
    if not token:
        return None, RESULT_INVALID

    result = await _graph().query(
        """
        MATCH (p:PendingSignup {token_hash: $token_hash})
        WITH p,
             p.email AS email,
             p.first_name AS first_name,
             p.last_name AS last_name,
             p.password_hash AS password_hash,
             p.expires_at AS expires_at
        DELETE p
        RETURN email, first_name, last_name, password_hash, expires_at
        """,
        {"token_hash": hash_token(token)},
    )
    if not result.result_set:
        return None, RESULT_INVALID

    email, first_name, last_name, password_hash, expires_at = result.result_set[0]

    # Expired tokens are consumed rather than left behind: the link is dead
    # either way, and dropping the record keeps abandoned signups from
    # accumulating. The user simply signs up again.
    if not isinstance(expires_at, (int, float)) or _now_ms() >= expires_at:
        return None, RESULT_EXPIRED

    if not email or not password_hash:
        logging.error("Discarding a malformed pending signup record")
        return None, RESULT_INVALID

    return (
        PendingSignup(
            email=email,
            first_name=first_name or "",
            last_name=last_name or "",
            password_hash=password_hash,
        ),
        RESULT_OK,
    )


async def discard_pending_signup(email: str) -> None:
    """Drop any pending signup for an address. Best-effort; never fatal.

    Called once an account exists for the address by some other route, so a
    stale link cannot later be redeemed against it.
    """
    try:
        await _graph().query(
            "MATCH (p:PendingSignup {email: $email}) DELETE p", {"email": email}
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        logging.warning("Could not discard pending signup: %s", e)


def _greeting(first_name: Optional[str]) -> str:
    """``Hi Ada`` when a name is known, plain ``Hi`` when it is not."""
    name = (first_name or "").strip()
    return f"Hi {name}," if name else "Hi,"


async def send_verification_link(
    email: str, first_name: Optional[str], verify_url: str
) -> bool:
    """Mail the verification link. Returns whether it was handed to a transport."""
    hours = token_ttl_seconds() // 3600
    greeting = _greeting(first_name)

    text_body = (
        f"{greeting}\n\n"
        "Confirm your email address to finish creating your QueryWeaver account:\n\n"
        f"{verify_url}\n\n"
        f"The link works once and expires in {hours} hours. Your account is not "
        "created until you open it.\n\n"
        "If you did not sign up for QueryWeaver, ignore this message -- no "
        "account exists for this address and none will be created.\n"
    )

    html_body = (
        "<html><body>"
        f"<p>{html.escape(greeting)}</p>"
        "<p>Confirm your email address to finish creating your QueryWeaver "
        "account:</p>"
        f'<p><a href="{html.escape(verify_url, quote=True)}">Confirm my email address</a></p>'
        f"<p>The link works once and expires in {hours} hours. Your account is "
        "not created until you open it.</p>"
        "<p>If you did not sign up for QueryWeaver, ignore this message &mdash; "
        "no account exists for this address and none will be created.</p>"
        "</body></html>"
    )

    return await send_mail(
        to=email,
        subject="Confirm your QueryWeaver email address",
        text_body=text_body,
        html_body=html_body,
    )
