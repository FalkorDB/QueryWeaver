import fs from 'fs';
import path from 'path';
import { APIRequestContext } from '@playwright/test';
import { postRequest } from '../../infra/api/apiRequests';
import { getBaseUrl } from '../../config/urls';

/**
 * Reading the signup confirmation code out of the mail outbox.
 *
 * Signup no longer logs anybody in: it mails a code, and handing that code back
 * is what creates the account and starts the session. The suite therefore has
 * to go through the mail. The backend's file transport (`MAIL_OUTBOX_DIR`)
 * writes each message to disk, so the tests exercise the real flow rather than
 * a test-only shortcut that would prove nothing about it.
 */

const OUTBOX_DIR = process.env.MAIL_OUTBOX_DIR || 'e2e/.mail';

// The mail is written while the signup request is still in flight, so a short
// poll covers the gap without making the setup slow when it is already there.
const WAIT_TIMEOUT_MS = 10_000;
const POLL_INTERVAL_MS = 200;

const CODE_LENGTH = 6;

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
 * Python's email builder wraps long lines with a trailing `=` and escapes bytes
 * as `=XX`, either of which can land in the middle of the digits we are after.
 */
function decodeQuotedPrintable(contents: string): string {
  return contents
    .replace(/=\r?\n/g, '')
    .replace(/=([0-9A-Fa-f]{2})/g, (_, hex) => String.fromCharCode(parseInt(hex, 16)));
}

/**
 * Pull the code out of the message body.
 *
 * The plain-text part indents it on a line of its own, which is specific enough
 * to keep the match away from the digits in headers and timestamps.
 */
function extractCode(contents: string): string | null {
  const match = decodeQuotedPrintable(contents).match(
    new RegExp(`^\\s+(\\d{${CODE_LENGTH}})\\s*$`, 'm')
  );
  return match ? match[1] : null;
}

/**
 * Wait for the confirmation code most recently mailed to `email`.
 */
export async function waitForVerificationCode(email: string): Promise<string> {
  const deadline = Date.now() + WAIT_TIMEOUT_MS;

  while (Date.now() < deadline) {
    const candidates = readOutbox()
      .filter((message) => message.contents.includes(email))
      .sort((a, b) => b.mtimeMs - a.mtimeMs);

    for (const candidate of candidates) {
      const code = extractCode(candidate.contents);
      // Consume it, so a later signup for the same address cannot match this
      // message and submit a code that has already been spent.
      if (code) {
        fs.rmSync(candidate.file, { force: true });
        return code;
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
 * Hand the mailed code back, which creates the account and signs the request
 * context in.
 */
export async function completeVerification(
  email: string,
  requestContext: APIRequestContext
): Promise<void> {
  const code = await waitForVerificationCode(email);
  const response = await postRequest(
    `${getBaseUrl()}/signup/email/verify`,
    { email, code },
    requestContext
  );

  const data = await response.json().catch(() => ({}));
  if (!data.success) {
    throw new Error(
      `Verification for ${email} failed: ${data.error || response.status()}`
    );
  }
}
