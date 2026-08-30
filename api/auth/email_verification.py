"""Signup email verification -- the holding pen for accounts that do not exist yet.

Signing up does not create a user. It records the submitted details on a
``PendingSignup`` node and mails a six-digit code; typing that code back into
the browser that signed up is what creates the ``User`` and ``Identity`` and
logs it in. An address that is never confirmed therefore never becomes an
account at all -- nothing to count, nothing to log in as, nothing to clean up
beyond an expiring node.

That ordering is what makes the guarantee cheap. There is no ``email_verified``
flag to check at every call site and no half-real user for the org graph,
analytics or quota logic to trip over, because an unverified address is simply
absent from the account graph.

A code rather than a link, deliberately. A link can be opened by whoever
receives it, which is the wrong person in the case that matters: submit someone
else's address with a password of your choosing, and their click would create an
account they do not control the password to. A code has to be carried back to
the session that submitted the form, and the person who submitted it never sees
the mail. It also means no URL for a mail scanner to fetch and silently burn.

The code alone is not quite enough, because two people can submit the same
address. Whoever writes last owns the stored password, and the code that goes
out is mailed to the address, not to the submitter -- so a stranger could
re-submit someone else's pending signup with a password of their own and let the
owner redeem it for them. Each submission therefore also mints a ticket that
stays in the submitting browser's session, and a code is only redeemable by the
browser holding the ticket that was issued with it. Re-submission then costs the
first submitter their pending signup, which is a nuisance they can undo by
signing up again, rather than an account under someone else's password.

The code is short, so its secrecy cannot rest on entropy -- a million
possibilities is nothing to a script. What bounds it is the attempt limit: a
handful of wrong guesses destroys the pending signup outright, and the code
expires in minutes. Only the SHA-256 is stored, which keeps a casual reader of
the graph from lifting a live code, but the attempt limit is the actual defence.

Codes are single-use (consuming one deletes the node) and expiring, and sends
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

# Digits in a verification code. Six is what people expect to retype; the
# attempt limit below is what makes it safe, not the length.
CODE_DIGITS = 6

# Long enough to walk to the other device and back, short enough that a code
# left in an inbox is not still live tomorrow.
DEFAULT_TTL_MINUTES = 15

# Wrong guesses allowed before the pending signup is destroyed. With six digits
# this is the whole defence against grinding the code, so it is deliberately
# small: five wrong guesses out of a million is not a meaningful head start.
DEFAULT_MAX_ATTEMPTS = 5

# Minimum gap between two sends to one address.
DEFAULT_RESEND_INTERVAL_SECONDS = 60

# Total sends allowed for one pending signup, resend included. Bounds how much
# mail a single submitted address can generate.
DEFAULT_MAX_SENDS = 5

# Outcomes of redeeming a code, kept as constants so routes and tests agree on
# the spelling.
RESULT_OK = "ok"
RESULT_INVALID = "invalid"
RESULT_EXPIRED = "expired"


@dataclass(frozen=True)
class PendingSignup:
    """The details captured at signup, replayed when the code is redeemed."""

    email: str
    first_name: str
    last_name: str
    password_hash: str

    @property
    def full_name(self) -> str:
        """Display name, matching the format the signup route stored."""
        return f"{self.first_name} {self.last_name}".strip()


@dataclass(frozen=True)
class CodeIssue:
    """The result of asking for a verification code.

    ``code`` is the only time the raw value exists outside the mail, and
    ``ticket`` the only time that value exists outside the caller's session; the
    graph keeps just their hashes. Nothing here says *why* a code was refused:
    the routes answer refusals and successes identically, so the reason would
    only be a way to ask the graph questions about other people's addresses.

    The ``previous_*`` fields are the code this one displaced, so
    ``revert_verification_send`` can put it back if the mail never goes out.
    They also say whether there was a pending signup here at all: a code hash
    means the record pre-dated this call.
    """

    code: Optional[str] = None
    first_name: Optional[str] = None
    ticket: Optional[str] = None
    previous_code_hash: Optional[str] = None
    previous_expires_at: Optional[int] = None
    previous_attempts: Optional[int] = None

    @property
    def issued(self) -> bool:
        """Whether a code was actually produced."""
        return self.code is not None


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


def code_ttl_seconds() -> int:
    """How long a verification code stays valid."""
    return _positive_int_env("EMAIL_VERIFICATION_TTL_MINUTES", DEFAULT_TTL_MINUTES) * 60


def max_attempts() -> int:
    """Wrong guesses a pending signup survives."""
    return _positive_int_env("EMAIL_VERIFICATION_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS)


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


def generate_code() -> str:
    """A fresh zero-padded verification code."""
    return f"{secrets.randbelow(10 ** CODE_DIGITS):0{CODE_DIGITS}d}"


def generate_ticket() -> str:
    """A fresh signup ticket.

    Unlike the code this one is never typed by anybody, so it is as long as it
    wants to be -- and it has to be, because it is the half of the pair that
    never leaves the browser and therefore has no attempt limit behind it.
    """
    return secrets.token_urlsafe(32)


def hash_code(code: str) -> str:
    """Hash a raw code for storage and lookup."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _graph():
    """The Organizations graph, where identity records live."""
    return db.select_graph(ORGANIZATIONS_GRAPH)


# The guard the two issuing queries share. It rides along in the write itself
# rather than being checked first: a single Cypher query is atomic and writes to
# one graph are serialised, so checking separately would let two concurrent
# requests both pass the check and both send while the counter advanced once.
#
# ``stale`` is what keeps the send budget from turning into a permanent lock on
# an address. Nothing deletes a pending signup that is simply never confirmed,
# so without it a stranger could spend an address's five sends, leave the
# counter pinned at its limit for good, and the real owner would never be able
# to sign up. Once the code the counter was rationing has expired the record is
# spent anyway, and the next submission starts a fresh budget on it.
_SEND_GUARD = """
        WITH p, (p.expires_at IS NULL OR p.expires_at < $now) AS stale
        WHERE (stale OR p.send_count < $max_sends)
          AND (p.last_sent_at IS NULL OR $now - p.last_sent_at >= $interval_ms)
"""

# Counts this send, starting over when the record it lands on had expired. The
# interval still applies on that path, so an expired record is not a way to send
# faster -- only a way to keep sending at all.
_COUNT_SEND = "p.send_count = CASE WHEN stale THEN 1 ELSE p.send_count + 1 END"

# Creates the pending signup if it is new, then replaces its details and issues
# a code -- but only for a node the guard lets through. A node created by this
# very query has no code and no expiry, so it counts as stale and always passes.
_START_SIGNUP = (
    """
        MERGE (p:PendingSignup {email: $email})
        ON CREATE SET p.created_at = $now, p.send_count = 0
"""
    + _SEND_GUARD
    + """
        WITH p, stale,
             p.code_hash AS previous_code_hash,
             p.expires_at AS previous_expires_at,
             p.attempts AS previous_attempts
        SET p.code_hash = $code_hash,
            p.ticket_hash = $ticket_hash,
            p.first_name = $first_name,
            p.last_name = $last_name,
            p.password_hash = $password_hash,
            p.expires_at = $expires_at,
            p.attempts = 0,
            p.last_sent_at = $now,
            """
    + _COUNT_SEND
    + """
        RETURN previous_code_hash,
               previous_expires_at,
               previous_attempts
"""
)

# Refresh only: never MERGE, so the resend endpoint cannot conjure a pending
# signup for an address nobody submitted. The ticket is deliberately left alone
# -- a resend is another copy of the same signup, not a new one, and rotating it
# would lock out the browser that is waiting for the code.
_REFRESH_SIGNUP = (
    """
        MATCH (p:PendingSignup {email: $email})
"""
    + _SEND_GUARD
    + """
        WITH p, stale,
             p.code_hash AS previous_code_hash,
             p.expires_at AS previous_expires_at,
             p.attempts AS previous_attempts
        SET p.code_hash = $code_hash,
            p.expires_at = $expires_at,
            p.attempts = 0,
            p.last_sent_at = $now,
            """
    + _COUNT_SEND
    + """
        RETURN p.first_name AS first_name,
               previous_code_hash,
               previous_expires_at,
               previous_attempts
"""
)

# Undoes one send. Matching on the hash this send wrote makes it a no-op if
# another request has since issued a code of its own.
_REVERT_SEND = """
        MATCH (p:PendingSignup {email: $email})
        WHERE p.code_hash = $code_hash
        SET p.code_hash = $previous_code_hash,
            p.expires_at = $previous_expires_at,
            p.attempts = $previous_attempts,
            p.send_count = p.send_count - 1
"""


def _throttle_params(now: int) -> dict:
    """The parameters ``_SEND_GUARD`` reads."""
    return {
        "now": now,
        "max_sends": max_sends(),
        "interval_ms": resend_interval_seconds() * 1000,
    }


async def start_pending_signup(
    email: str, first_name: str, last_name: str, password_hash: str
) -> CodeIssue:
    """Record a signup awaiting verification and return its code and ticket.

    Re-submitting the form for an address that is already pending replaces the
    stored details and invalidates the previous code *and* ticket, so only the
    browser behind the most recent attempt can complete it. The send counter
    deliberately survives that replace: otherwise resubmitting would reset the
    rate limit and defeat it.
    """
    now = _now_ms()
    code = generate_code()
    ticket = generate_ticket()
    result = await _graph().query(
        _START_SIGNUP,
        {
            "email": email,
            "code_hash": hash_code(code),
            "ticket_hash": hash_code(ticket),
            "first_name": first_name,
            "last_name": last_name,
            "password_hash": password_hash,
            "expires_at": now + code_ttl_seconds() * 1000,
            **_throttle_params(now),
        },
    )
    if not result.result_set:
        # Sent to a moment ago, or out of sends while the current code is still
        # live. Which one is not reported: the route answers a refusal exactly
        # like a success, so telling them apart here would only be a way to ask
        # whether a stranger's address has a signup in flight.
        return CodeIssue()

    previous_code_hash, previous_expires_at, previous_attempts = result.result_set[0]
    return CodeIssue(
        code=code,
        first_name=first_name,
        ticket=ticket,
        previous_code_hash=previous_code_hash,
        previous_expires_at=previous_expires_at,
        previous_attempts=previous_attempts,
    )


async def refresh_pending_signup(email: str) -> CodeIssue:
    """Issue a fresh code for an existing pending signup.

    Only ever refreshes; it will not create a pending signup, so the resend
    endpoint cannot be used to send mail to an address nobody submitted. A new
    code comes with a fresh attempt budget -- the old one belonged to a code
    that no longer works.
    """
    now = _now_ms()
    code = generate_code()
    result = await _graph().query(
        _REFRESH_SIGNUP,
        {
            "email": email,
            "code_hash": hash_code(code),
            "expires_at": now + code_ttl_seconds() * 1000,
            **_throttle_params(now),
        },
    )
    if not result.result_set:
        # No pending signup, one that has used up its sends, or one that was
        # sent to a moment ago. Also covers losing a race with a verification
        # that just consumed the record. Indistinguishable on purpose.
        return CodeIssue()

    first_name, previous_code_hash, previous_expires_at, previous_attempts = (
        result.result_set[0]
    )
    return CodeIssue(
        code=code,
        first_name=first_name,
        previous_code_hash=previous_code_hash,
        previous_expires_at=previous_expires_at,
        previous_attempts=previous_attempts,
    )


async def revert_verification_send(email: str, issue: CodeIssue) -> None:
    """Give back a send whose mail never left. Best-effort; never fatal.

    Refunds the counter and puts the displaced code back in force, so a
    transport failure costs the user neither their send budget nor the code
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
                "code_hash": hash_code(issue.code),
                "previous_code_hash": issue.previous_code_hash,
                "previous_expires_at": issue.previous_expires_at,
                "previous_attempts": issue.previous_attempts,
            },
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        logging.warning("Could not revert a failed verification send: %s", e)


# Redeems a code. The attempt guard rides inside the write for the same reason
# the send guard does: checking first would let concurrent guesses all pass a
# check that only one increment ever answered for.
_CONSUME_CODE = """
        MATCH (p:PendingSignup {email: $email})
        WHERE p.code_hash = $code_hash
          AND p.ticket_hash = $ticket_hash
          AND p.attempts < $max_attempts
        WITH p,
             p.first_name AS first_name,
             p.last_name AS last_name,
             p.password_hash AS password_hash,
             p.expires_at AS expires_at
        DELETE p
        RETURN first_name, last_name, password_hash, expires_at
"""

# Charges a wrong guess, and destroys the signup once the budget is gone. A
# six-digit code only stays secret while the number of guesses stays small.
_CHARGE_ATTEMPT = """
        MATCH (p:PendingSignup {email: $email})
        SET p.attempts = p.attempts + 1
        WITH p, p.attempts AS attempts
        WHERE attempts >= $max_attempts
        DELETE p
        RETURN attempts
"""


async def consume_pending_signup(
    email: str, code: str, ticket: str
) -> Tuple[Optional[PendingSignup], str]:
    """Redeem a verification code exactly once.

    Returns ``(pending, RESULT_OK)`` when the code was live. The node is deleted
    in the same query that reads it, so a replayed code finds nothing -- that,
    not a flag, is what makes it single-use.

    Both halves are required. The code proves the caller reads the address's
    mail; the ticket proves they are the browser that submitted the password
    being redeemed. Without the ticket, anyone could re-submit a stranger's
    pending signup under a password of their own and let the address's owner
    confirm it into an account the submitter can log into.

    A wrong guess is charged against the record's attempt budget, and running
    that budget out deletes the pending signup. That, rather than the length of
    the code, is what makes six digits enough.

    Lookup is by code *hash*, an exact match on a stored value, so there is no
    secret-dependent comparison here for timing to leak.
    """
    if not email or not code or not ticket:
        return None, RESULT_INVALID

    result = await _graph().query(
        _CONSUME_CODE,
        {
            "email": email,
            "code_hash": hash_code(code),
            "ticket_hash": hash_code(ticket),
            "max_attempts": max_attempts(),
        },
    )
    if not result.result_set:
        await _charge_failed_attempt(email)
        return None, RESULT_INVALID

    first_name, last_name, password_hash, expires_at = result.result_set[0]

    # Expired codes are consumed rather than left behind: the code is dead
    # either way, and dropping the record keeps abandoned signups from
    # accumulating. The user simply signs up again.
    if not isinstance(expires_at, (int, float)) or _now_ms() >= expires_at:
        return None, RESULT_EXPIRED

    if not password_hash:
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


async def _charge_failed_attempt(email: str) -> None:
    """Bill a wrong guess. Best-effort; a failure must not become a free retry."""
    try:
        result = await _graph().query(
            _CHARGE_ATTEMPT, {"email": email, "max_attempts": max_attempts()}
        )
        if result.result_set:
            logging.warning("Pending signup discarded after too many wrong codes")
    except Exception as e:  # pylint: disable=broad-exception-caught
        logging.warning("Could not record a failed verification attempt: %s", e)


async def discard_pending_signup(email: str) -> None:
    """Drop any pending signup for an address. Best-effort; never fatal.

    Called once an account exists for the address by some other route, so a
    stale code cannot later be redeemed against it.
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


async def send_verification_code(
    email: str, first_name: Optional[str], code: str
) -> bool:
    """Mail the verification code. Returns whether it was handed to a transport."""
    minutes = code_ttl_seconds() // 60
    greeting = _greeting(first_name)

    text_body = (
        f"{greeting}\n\n"
        "Your QueryWeaver confirmation code is:\n\n"
        f"    {code}\n\n"
        f"Type it into the tab where you signed up. It works once and expires in "
        f"{minutes} minutes. Your account is not created until you enter it.\n\n"
        "If you did not sign up for QueryWeaver, ignore this message -- no "
        "account exists for this address and none will be created. Never share "
        "this code with anyone.\n"
    )

    html_body = (
        "<html><body>"
        f"<p>{html.escape(greeting)}</p>"
        "<p>Your QueryWeaver confirmation code is:</p>"
        f'<p style="font-size:28px;font-weight:bold;letter-spacing:6px">'
        f"{html.escape(code)}</p>"
        f"<p>Type it into the tab where you signed up. It works once and expires "
        f"in {minutes} minutes. Your account is not created until you enter it.</p>"
        "<p>If you did not sign up for QueryWeaver, ignore this message &mdash; "
        "no account exists for this address and none will be created. Never "
        "share this code with anyone.</p>"
        "</body></html>"
    )

    return await send_mail(
        to=email,
        subject="Your QueryWeaver confirmation code",
        text_body=text_body,
        html_body=html_body,
    )
