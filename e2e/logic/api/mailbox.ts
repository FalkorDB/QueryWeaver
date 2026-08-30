import fs from 'fs';
import path from 'path';
import { APIRequestContext } from '@playwright/test';

/**
 * Reading the signup verification link out of the mail outbox.
 *
 * Signup no longer logs anybody in: it mails a link, and opening that link is
 * what creates the account and starts the session. The suite therefore has to
 * go through the mail. The backend's file transport (`MAIL_OUTBOX_DIR`) writes
 * each message to disk, so the tests exercise the real flow rather than a
 * test-only shortcut that would prove nothing about it.
 */

const OUTBOX_DIR = process.env.MAIL_OUTBOX_DIR || 'e2e/.mail';

// The mail is written while the signup request is still in flight, so a short
// poll covers the gap without making the setup slow when it is already there.
const WAIT_TIMEOUT_MS = 10_000;
const POLL_INTERVAL_MS = 200;

interface Message {
  file: string;
  contents: string;
  mtimeMs: number;
}

function readOutbox(): Message[] {
  if (!fs.existsSync(OUTBOX_DIR)) return [];
  return fs
    .readdirSync(OUTBOX_DIR)
    .filter((name) => name.endsWith('.eml'))
    .map((name) => {
      const file = path.join(OUTBOX_DIR, name);
      return {
        file,
        contents: fs.readFileSync(file, 'utf8'),
        mtimeMs: fs.statSync(file).mtimeMs,
      };
    });
}

/**
 * Undo quoted-printable encoding.
 *
 * The verification URL is longer than the 78-character line limit, so Python's
 * email builder encodes the body: the line is split with a trailing `=` and,
 * crucially, the `=` in `?token=` becomes `=3D`. A regex run over the raw file
 * therefore matches a token with a spurious `3D` prefix, which the backend
 * quite correctly rejects.
 */
function decodeQuotedPrintable(contents: string): string {
  return contents
    .replace(/=\r?\n/g, '')
    .replace(/=([0-9A-Fa-f]{2})/g, (_, hex) => String.fromCharCode(parseInt(hex, 16)));
}

function extractVerifyUrl(contents: string): string | null {
  const match = decodeQuotedPrintable(contents).match(
    /https?:\/\/[^\s"<>]*\/verify\/email\?token=[A-Za-z0-9_-]+/
  );
  return match ? match[0] : null;
}

/**
 * Wait for the verification link most recently mailed to `email`.
 */
export async function waitForVerificationUrl(email: string): Promise<string> {
  const deadline = Date.now() + WAIT_TIMEOUT_MS;

  while (Date.now() < deadline) {
    const candidates = readOutbox()
      .filter((message) => message.contents.includes(email))
      .sort((a, b) => b.mtimeMs - a.mtimeMs);

    for (const candidate of candidates) {
      const url = extractVerifyUrl(candidate.contents);
      // Consume it, so a later signup for the same address cannot match this
      // one and follow a link that has already been spent.
      if (url) {
        fs.rmSync(candidate.file, { force: true });
        return url;
      }
    }

    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
  }

  throw new Error(
    `No verification email for ${email} appeared in ${OUTBOX_DIR}. ` +
      'Is the server running with MAIL_OUTBOX_DIR set?'
  );
}

/**
 * Follow the verification link, which creates the account and signs the
 * request context in.
 */
export async function completeVerification(
  email: string,
  requestContext: APIRequestContext
): Promise<void> {
  const url = await waitForVerificationUrl(email);
  const response = await requestContext.get(url);

  // The link redirects into the SPA carrying the outcome.
  const outcome = new URL(response.url()).searchParams.get('verified');
  if (outcome !== 'success') {
    throw new Error(`Verification for ${email} returned "${outcome}"`);
  }
}
