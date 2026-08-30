import { test as setup, Page } from '@playwright/test';
import apiCalls from '../logic/api/apiCalls';
import { completeVerification } from '../logic/api/mailbox';
import { getTestUser, getTestUser2, getTestUser3 } from '../config/urls';

const authFile = 'e2e/.auth/user.json';
const authFile2 = 'e2e/.auth/user2.json';
const authFile3 = 'e2e/.auth/user3.json';

/**
 * Sign the context in as one test user, creating the account if it is missing.
 *
 * Signup does not log anybody in any more: it mails a confirmation link, and
 * opening that link is what creates the account and starts the session. So the
 * create path goes through the mail outbox rather than trusting the signup
 * response, which is also what keeps this setup honest about the real flow.
 */
async function authenticateUser(
  api: apiCalls,
  page: Page,
  user: { email: string; password: string },
  firstName: string,
  lastName: string,
  storagePath: string,
  label: string
): Promise<void> {
  const { email, password } = user;

  try {
    const response = await api.loginWithEmail(email, password, page.request);

    if (!response.success) {
      const signupResponse = await api.signupWithEmail(
        firstName,
        lastName,
        email,
        password,
        page.request
      );

      if (!signupResponse.success) {
        throw new Error(
          `Failed to create ${label}: ${signupResponse.error || 'Unknown error'}`
        );
      }

      await completeVerification(email, page.request);
    }
  } catch (error) {
    const errorMessage = (error as Error).message;
    throw new Error(`Authentication failed for ${label}. \n Error: ${errorMessage}`);
  }

  await page.context().storageState({ path: storagePath });
}

setup('authenticate users', async ({ page }) => {
  const api = new apiCalls();

  await authenticateUser(api, page, getTestUser(), 'Test', 'User', authFile, 'test user 1');
  await authenticateUser(api, page, getTestUser2(), 'Test2', 'User2', authFile2, 'test user 2');
  await authenticateUser(api, page, getTestUser3(), 'Test3', 'User3', authFile3, 'test user 3');
});
