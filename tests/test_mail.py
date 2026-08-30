"""Tests for the mail transport seam.

The transport is deliberately thin, so the only things worth pinning are the
ones that would be silently wrong: that a failed send is reported rather than
raised, that a failure does not leak the confirmation code into the logs, and
that a recipient address cannot smuggle extra headers into the message.
"""

import smtplib
from unittest.mock import MagicMock, patch

import pytest

from api import mail

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def _clean_mail_env(monkeypatch):
    """Start every test from the default (console) transport."""
    monkeypatch.delenv("MAIL_SERVER", raising=False)
    monkeypatch.delenv("MAIL_OUTBOX_DIR", raising=False)


class TestTransportSelection:
    """Which transport is used, and how that is reported."""

    def test_console_is_the_default(self):
        assert mail.is_smtp_configured() is False
        assert mail.transport_name() == "console"

    def test_configuring_a_server_switches_to_smtp(self, monkeypatch):
        monkeypatch.setenv("MAIL_SERVER", "smtp.example.com")
        assert mail.is_smtp_configured() is True
        assert mail.transport_name() == "smtp"

    def test_an_outbox_wins_over_a_relay(self, monkeypatch, tmp_path):
        # An outbox is only ever set deliberately, and a test run that quietly
        # mails real addresses is worse than one that quietly does not.
        monkeypatch.setenv("MAIL_SERVER", "smtp.example.com")
        monkeypatch.setenv("MAIL_OUTBOX_DIR", str(tmp_path))
        assert mail.transport_name() == "file"

    @pytest.mark.asyncio
    async def test_an_outbox_keeps_a_configured_relay_unused(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MAIL_SERVER", "smtp.example.com")
        monkeypatch.setenv("MAIL_OUTBOX_DIR", str(tmp_path))

        with patch("api.mail.smtplib.SMTP") as mock_smtp:
            sent = await mail.send_mail(
                to="new@example.com", subject="Confirm", text_body="body"
            )

        assert sent is True
        mock_smtp.assert_not_called()

    @pytest.mark.asyncio
    async def test_console_transport_logs_the_body(self, caplog):
        # Local development has no mail server, so the log is where the
        # confirmation code has to be readable from.
        with caplog.at_level("INFO"):
            sent = await mail.send_mail(
                to="new@example.com", subject="Confirm", text_body="code 123456"
            )

        assert sent is True
        assert "code 123456" in caplog.text


class TestFileTransport:
    """The outbox the end-to-end suite reads the confirmation code out of."""

    @pytest.mark.asyncio
    async def test_message_is_written_as_a_readable_file(self, monkeypatch, tmp_path):
        outbox = tmp_path / "mail"
        monkeypatch.setenv("MAIL_OUTBOX_DIR", str(outbox))

        sent = await mail.send_mail(
            to="new@example.com", subject="Confirm", text_body="code 123456"
        )

        assert sent is True
        files = list(outbox.glob("*.eml"))
        assert len(files) == 1
        contents = files[0].read_text()
        assert "new@example.com" in contents
        assert "code 123456" in contents

    @pytest.mark.asyncio
    async def test_an_unwritable_outbox_is_reported_not_raised(self, monkeypatch, tmp_path):
        blocker = tmp_path / "not-a-dir"
        blocker.write_text("")
        monkeypatch.setenv("MAIL_OUTBOX_DIR", str(blocker))

        sent = await mail.send_mail(
            to="new@example.com", subject="Confirm", text_body="body"
        )

        assert sent is False


class TestSmtpTransport:
    """The SMTP path."""

    @pytest.mark.asyncio
    async def test_a_broken_server_is_reported_not_raised(self, monkeypatch, caplog):
        # The caller decides what a failed send means; an exception escaping
        # here would turn it into a 500 on a request that can be retried.
        monkeypatch.setenv("MAIL_SERVER", "smtp.example.com")
        with patch("api.mail.smtplib.SMTP", side_effect=OSError("no route")):
            sent = await mail.send_mail(
                to="new@example.com",
                subject="Confirm",
                text_body="code-that-must-not-leak",
            )

        assert sent is False
        # The body carries a live confirmation code; logging it on failure would
        # put a credential in the log file.
        assert "code-that-must-not-leak" not in caplog.text

    @pytest.mark.asyncio
    async def test_an_smtp_error_is_reported_not_raised(self, monkeypatch):
        monkeypatch.setenv("MAIL_SERVER", "smtp.example.com")
        with patch("api.mail.smtplib.SMTP", side_effect=smtplib.SMTPException("nope")):
            sent = await mail.send_mail(
                to="new@example.com", subject="Confirm", text_body="body"
            )

        assert sent is False

    @pytest.mark.asyncio
    async def test_credentials_are_only_sent_when_configured(self, monkeypatch):
        monkeypatch.setenv("MAIL_SERVER", "smtp.example.com")
        monkeypatch.delenv("MAIL_USERNAME", raising=False)
        client = MagicMock()
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)

        with patch("api.mail.smtplib.SMTP", return_value=client):
            sent = await mail.send_mail(
                to="new@example.com", subject="Confirm", text_body="body"
            )

        assert sent is True
        client.login.assert_not_called()
        client.send_message.assert_called_once()


class TestHeaderInjection:
    """A recipient address is attacker-controlled input."""

    @pytest.mark.parametrize("evil", [
        "victim@example.com\nBcc: everyone@example.com",
        "victim@example.com\r\nBcc: everyone@example.com",
    ])
    @pytest.mark.asyncio
    async def test_newlines_in_the_recipient_are_refused(self, evil):
        # Without this the address field becomes a way to add arbitrary headers
        # and mail the link to a third party.
        sent = await mail.send_mail(to=evil, subject="Confirm", text_body="body")

        assert sent is False
