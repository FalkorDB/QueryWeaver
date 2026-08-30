"""Outbound mail.

QueryWeaver sends one kind of message today -- the signup confirmation code --
so this module stays small: pick a transport from the environment, hand it a
built message, and report whether it left the process.

Three transports:

* ``console`` (the default) writes the message to the log instead of sending
  it, so local development completes the signup flow without a mail server.
* ``file`` writes each message to ``MAIL_OUTBOX_DIR`` as an ``.eml``. The
  Playwright suite reads the confirmation code back out of it, which is what
  keeps the end-to-end signup test exercising the real flow instead of a
  test-only shortcut through the backend. It takes precedence over a configured
  relay: nobody sets this variable by accident, and a test run that quietly
  mails real addresses is a worse failure than one that quietly does not.
* ``smtp`` talks to any relay. Every hosted provider -- Mailgun, SendGrid,
  Resend, SES, Postmark -- exposes an SMTP endpoint, so this covers them all
  without binding the project to a vendor SDK.

The relay is selected by whether ``MAIL_SERVER`` is set rather than by a
separate switch, so a half-configured relay cannot be selected by accident.

``smtplib`` is synchronous, so sends run on a worker thread: a relay that takes
its time must not stall the event loop for every other request.
"""

import asyncio
import logging
import os
import secrets
import smtplib
import ssl
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

# Implicit-TLS port. Everything else is assumed to be plain SMTP that may be
# upgraded with STARTTLS.
SMTPS_PORT = 465

DEFAULT_SMTP_PORT = 587
DEFAULT_TIMEOUT_SECONDS = 10.0
FALLBACK_SENDER = "no-reply@queryweaver.local"


def _env_flag(name: str, default: bool) -> bool:
    """Read a boolean environment variable, falling back on anything unrecognised."""
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in ("true", "1", "yes", "on"):
        return True
    if value in ("false", "0", "no", "off"):
        return False
    logging.warning("Invalid %s value %r, using %s", name, raw, default)
    return default


def _smtp_timeout() -> float:
    """Socket timeout for the relay, from ``MAIL_TIMEOUT_SECONDS``."""
    raw = os.getenv("MAIL_TIMEOUT_SECONDS")
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        timeout = float(raw)
    except ValueError:
        timeout = 0.0
    if timeout > 0:
        return timeout
    logging.warning("Invalid MAIL_TIMEOUT_SECONDS value %r, ignoring", raw)
    return DEFAULT_TIMEOUT_SECONDS


def _smtp_port() -> int:
    """Relay port, from ``MAIL_PORT``."""
    raw = os.getenv("MAIL_PORT")
    if raw:
        try:
            return int(raw)
        except ValueError:
            logging.warning("Invalid MAIL_PORT value %r, ignoring", raw)
    return DEFAULT_SMTP_PORT


def is_smtp_configured() -> bool:
    """Whether a relay is configured. When ``False``, mail is logged, not sent."""
    return bool(os.getenv("MAIL_SERVER", "").strip())


def outbox_dir() -> str:
    """Directory for the file transport, from ``MAIL_OUTBOX_DIR``. Empty when unset."""
    return os.getenv("MAIL_OUTBOX_DIR", "").strip()


def transport_name() -> str:
    """Name of the active transport, for logs and diagnostics."""
    if outbox_dir():
        return "file"
    return "smtp" if is_smtp_configured() else "console"


def default_sender() -> str:
    """The ``From`` address."""
    return (
        os.getenv("MAIL_DEFAULT_SENDER", "").strip()
        or os.getenv("MAIL_USERNAME", "").strip()
        or FALLBACK_SENDER
    )


def _build_message(*, to: str, subject: str, text_body: str, html_body: Optional[str]) -> EmailMessage:
    """Assemble the message. Raises ``ValueError`` for an unusable recipient."""
    # Header injection guard. Callers validate the address first, but a header
    # split turns one verification mail into mail to anybody, so it is checked
    # again at the point the header is actually written.
    if not to or any(char in to for char in "\r\n"):
        raise ValueError("Recipient address contains a line break")

    message = EmailMessage()
    message["From"] = default_sender()
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")
    return message


def _send_via_smtp(message: EmailMessage) -> None:
    """Hand the message to the relay. Blocking; call it on a worker thread."""
    host = os.getenv("MAIL_SERVER", "").strip()
    port = _smtp_port()
    username = os.getenv("MAIL_USERNAME", "").strip()
    password = os.getenv("MAIL_PASSWORD", "")
    timeout = _smtp_timeout()

    if port == SMTPS_PORT:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, timeout=timeout, context=context) as client:
            if username:
                client.login(username, password)
            client.send_message(message)
        return

    with smtplib.SMTP(host, port, timeout=timeout) as client:
        if _env_flag("MAIL_USE_TLS", True):
            client.starttls(context=ssl.create_default_context())
            # The pre-STARTTLS greeting is unauthenticated, so the capability
            # list has to be re-read over the encrypted channel.
            client.ehlo()
        if username:
            client.login(username, password)
        client.send_message(message)


def _sanitize_for_log(value: str) -> str:
    """Flatten a value so it cannot forge log entries of its own."""
    # ``.replace('\n', ...)`` must be the outermost call for CodeQL's
    # log-injection sanitizer to recognise it. The body is deliberately
    # rendered on one line rather than dropped: the console transport exists so
    # a developer can copy the confirmation code out of the log.
    return str(value).replace("\r", " ").replace("\n", " ")


def _log_to_console(message: EmailMessage, text_body: str) -> None:
    """Write the message to the log in place of sending it."""
    logging.info(
        "[mail:console] No MAIL_SERVER configured, so this message was not sent. "
        "To: %s | Subject: %s | %s",
        _sanitize_for_log(message["To"]),
        _sanitize_for_log(message["Subject"]),
        _sanitize_for_log(text_body),
    )


def _write_to_outbox(message: EmailMessage, directory: str) -> bool:
    """Drop the message into the outbox directory as an ``.eml`` file."""
    try:
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        # Timestamp first so readers can pick the newest by name; the random
        # suffix keeps two sends in the same millisecond from colliding.
        name = f"{int(time.time() * 1000)}-{secrets.token_hex(4)}.eml"
        (path / name).write_bytes(message.as_bytes())
        return True
    except OSError as e:
        logging.error("Could not write mail to the outbox: %s", e)
        return False


async def send_mail(
    *,
    to: str,
    subject: str,
    text_body: str,
    html_body: Optional[str] = None,
) -> bool:
    """Send one message. Returns ``False`` instead of raising when it could not go.

    Callers are signup paths, where a failed send must not lose the work already
    done or leak relay detail to the client, so every failure is logged here and
    reported as a plain boolean.
    """
    try:
        message = _build_message(
            to=to, subject=subject, text_body=text_body, html_body=html_body
        )
    except ValueError as e:
        logging.error("Refusing to send mail: %s", e)
        return False

    directory = outbox_dir()
    if directory:
        return _write_to_outbox(message, directory)

    if not is_smtp_configured():
        _log_to_console(message, text_body)
        return True

    try:
        await asyncio.to_thread(_send_via_smtp, message)
        return True
    except (smtplib.SMTPException, OSError, ssl.SSLError) as e:
        # Deliberately does not log the message body: it carries the
        # confirmation code, which is a credential.
        logging.error("Could not send mail via SMTP: %s", e)
        return False
