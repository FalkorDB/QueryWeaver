import { test as setup } from '@playwright/test';
import apiCalls from '../logic/api/apiCalls';
import { getTestUser, getTestUser2, getTestUser3 } from '../config/urls';

const authFile = 'e2e/.auth/user.json';
const authFile2 = 'e2e/.auth/user2.json';
const authFile3 = 'e2e/.auth/user3.json';

setup('authenticate users', async ({ page }) => {
  const api = new apiCalls();
  
  // Authenticate user 1
  const { email, password } = getTestUser();

  try {
    // Try to login first
    let response = await api.loginWithEmail(
      email,
      password,
      page.request
    );

    // If login fails, try to create the user
    if (!response.success) { 
      const signupResponse = await api.signupWithEmail(
        'Test',
        'User',
        email,
        password,
        page.request
      );

      if (!signupResponse.success) {
        throw new Error(`Failed to create test user 1: ${signupResponse.error || 'Unknown error'}`);
      }
    } 
  } catch (error) {
    const errorMessage = (error as Error).message;
    throw new Error(
      `Authentication failed for user 1. \n Error: ${errorMessage}`
    );
  }

  // Save authentication state for user 1
  await page.context().storageState({ path: authFile });

  // Authenticate user 2
  const user2 = getTestUser2();

  try {
    // Try to login first
    let response = await api.loginWithEmail(
      user2.email,
      user2.password,
      page.request
    );

    // If login fails, try to create the user
    if (!response.success) { 
      const signupResponse = await api.signupWithEmail(
        'Test2',
        'User2',
        user2.email,
        user2.password,
        page.request
      );

      if (!signupResponse.success) {
        throw new Error(`Failed to create test user 2: ${signupResponse.error || 'Unknown error'}`);
      }
    } 
  } catch (error) {
    const errorMessage = (error as Error).message;
    throw new Error(
      `Authentication failed for user 2. \n Error: ${errorMessage}`
    );
  }

  // Save authentication state for user 2
  await page.context().storageState({ path: authFile2 });

  // Authenticate user 3
  const user3 = getTestUser3();

  try {
    // Try to login first
    let response = await api.loginWithEmail(
      user3.email,
      user3.password,
      page.request
    );

    // If login fails, try to create the user
    if (!response.success) {
      const signupResponse = await api.signupWithEmail(
        'Test3',
        'User3',
        user3.email,
        user3.password,
        page.request
      );

      if (!signupResponse.success) {
        throw new Error(`Failed to create test user 3: ${signupResponse.error || 'Unknown error'}`);
      }
    }
  } catch (error) {
    const errorMessage = (error as Error).message;
    throw new Error(
      `Authentication failed for user 3. \n Error: ${errorMessage}`
    );
  }

  // Save authentication state for user 3
  await page.context().storageState({ path: authFile3 });
});
