import { test, expect } from '@playwright/test';
import { getBaseUrl } from '../config/urls';
import BrowserWrapper from '../infra/ui/browserWrapper';
import ApiCalls from '../logic/api/apiCalls';
import { HomePage } from '../logic/pom/homePage';
import { EmailAuthPage } from '../logic/pom/emailAuthPage';

/**
 * Email Authentication Tests
 * Tests email signup and signin functionality
 * Each test is atomic and independent
 * 
 * IMPORTANT: These tests run WITHOUT pre-authentication
 * They use the 'chromium-unauthenticated' and 'firefox-unauthenticated' projects
 */
test.describe('Email Authentication Tests', () => {
  let browser: BrowserWrapper;
  let homePage: HomePage;
  let emailAuthPage: EmailAuthPage;

  // Generate unique email for each test to ensure atomicity
  const generateTestEmail = (testName: string) => {
    const timestamp = Date.now();
    const random = Math.floor(Math.random() * 10000);
    return `test.${testName}.${timestamp}.${random}@example.com`;
  };

  test.beforeEach(async () => {
    browser = new BrowserWrapper();
    homePage = await browser.createNewPage(HomePage, getBaseUrl());
    const page = await browser.getPage();
    emailAuthPage = new EmailAuthPage(page);
    await browser.setPageToFullScreen();
  });

  test.afterEach(async () => {
    await browser.closeBrowser();
  });

  test('should successfully sign up with valid email credentials', async () => {
    // Generate unique credentials
    const email = generateTestEmail('valid-signup');
    const firstName = 'John';
    const lastName = 'Doe';
    const password = 'SecurePass123!';

    // When unauthenticated, the login modal appears automatically
    // Wait for modal to be visible
    await homePage.waitForLoginModalVisible();

    // Modal opens in signin mode by default, switch to signup mode
    // Note: switchMode() also shows the email form automatically
    await emailAuthPage.clickSwitchModeLink();

    // Wait for email signup form to appear
    await emailAuthPage.waitForEmailSignupFormVisible();

    // Fill in signup form
    await emailAuthPage.fillFirstName(firstName);
    await emailAuthPage.fillLastName(lastName);
    await emailAuthPage.fillEmailField(email);
    await emailAuthPage.fillPasswordField(password);
    await emailAuthPage.fillConfirmPasswordField(password);

    // Submit signup form
    await emailAuthPage.clickCreateAccountBtn();

    // Wait for successful signup (modal should close and user should be authenticated)
    await homePage.waitForLoginModalHidden(10000);

    // Verify user is logged in
    const isLoggedIn = await homePage.isLoggedIn();
    expect(isLoggedIn).toBeTruthy();

    // Verify user menu shows correct email
    await homePage.clickOnUserMenu();
    const userEmail = await emailAuthPage.getUserEmail();
    expect(userEmail).toBe(email);
  });

  test('should fail signup without email', async () => {
    const firstName = 'John';
    const lastName = 'Doe';
    const password = 'SecurePass123!';

    // Login modal appears automatically for unauthenticated users
    await homePage.waitForLoginModalVisible();

    // Switch to signup mode (this also shows the email form)
    await emailAuthPage.clickSwitchModeLink();

    // Wait for email signup form to appear
    await emailAuthPage.waitForEmailSignupFormVisible();

    // Fill form WITHOUT email
    await emailAuthPage.fillFirstName(firstName);
    await emailAuthPage.fillLastName(lastName);
    await emailAuthPage.fillPasswordField(password);
    await emailAuthPage.fillConfirmPasswordField(password);

    // Attempt to submit (should be blocked by HTML5 validation)
    await emailAuthPage.clickCreateAccountBtn();

    // Verify modal is still open and error is shown or button is disabled
    const isModalVisible = await homePage.isLoginModalVisible();
    expect(isModalVisible).toBeTruthy();

    // User should still not be logged in
    const isLoggedIn = await homePage.isLoggedIn();
    expect(isLoggedIn).toBeFalsy();
  });

  test('should fail signup without password', async () => {
    const email = generateTestEmail('no-password');
    const firstName = 'John';
    const lastName = 'Doe';

    // Login modal appears automatically for unauthenticated users
    await homePage.waitForLoginModalVisible();

    // Switch to signup mode (this also shows the email form)
    await emailAuthPage.clickSwitchModeLink();

    // Wait for email signup form to appear
    await emailAuthPage.waitForEmailSignupFormVisible();

    // Fill form WITHOUT password
    await emailAuthPage.fillFirstName(firstName);
    await emailAuthPage.fillLastName(lastName);
    await emailAuthPage.fillEmailField(email);

    // Attempt to submit (should be blocked by HTML5 validation)
    await emailAuthPage.clickCreateAccountBtn();

    // Verify modal is still open
    const isModalVisible = await homePage.isLoginModalVisible();
    expect(isModalVisible).toBeTruthy();

    // User should still not be logged in
    const isLoggedIn = await homePage.isLoggedIn();
    expect(isLoggedIn).toBeFalsy();
  });

  test('should fail signup without first name', async () => {
    const email = generateTestEmail('no-firstname');
    const lastName = 'Doe';
    const password = 'SecurePass123!';

    // Login modal appears automatically for unauthenticated users
    await homePage.waitForLoginModalVisible();

    // Switch to signup mode (this also shows the email form)
    await emailAuthPage.clickSwitchModeLink();

    // Wait for email signup form to appear
    await emailAuthPage.waitForEmailSignupFormVisible();

    // Fill form WITHOUT first name
    await emailAuthPage.fillLastName(lastName);
    await emailAuthPage.fillEmailField(email);
    await emailAuthPage.fillPasswordField(password);
    await emailAuthPage.fillConfirmPasswordField(password);

    // Attempt to submit (should be blocked by HTML5 validation)
    await emailAuthPage.clickCreateAccountBtn();

    // Verify modal is still open
    const isModalVisible = await homePage.isLoginModalVisible();
    expect(isModalVisible).toBeTruthy();

    // User should still not be logged in
    const isLoggedIn = await homePage.isLoggedIn();
    expect(isLoggedIn).toBeFalsy();
  });

  test('should fail signup without last name', async () => {
    const email = generateTestEmail('no-lastname');
    const firstName = 'John';
    const password = 'SecurePass123!';

    // Login modal appears automatically for unauthenticated users
    await homePage.waitForLoginModalVisible();

    // Switch to signup mode (this also shows the email form)
    await emailAuthPage.clickSwitchModeLink();

    // Wait for email signup form to appear
    await emailAuthPage.waitForEmailSignupFormVisible();

    // Fill form WITHOUT last name
    await emailAuthPage.fillFirstName(firstName);
    await emailAuthPage.fillEmailField(email);
    await emailAuthPage.fillPasswordField(password);
    await emailAuthPage.fillConfirmPasswordField(password);

    // Attempt to submit (should be blocked by HTML5 validation)
    await emailAuthPage.clickCreateAccountBtn();

    // Verify modal is still open
    const isModalVisible = await homePage.isLoginModalVisible();
    expect(isModalVisible).toBeTruthy();

    // User should still not be logged in
    const isLoggedIn = await homePage.isLoggedIn();
    expect(isLoggedIn).toBeFalsy();
  });

  test('should fail signup with password mismatch', async () => {
    const email = generateTestEmail('password-mismatch');
    const firstName = 'John';
    const lastName = 'Doe';
    const password = 'SecurePass123!';
    const wrongPassword = 'DifferentPass456!';

    // Login modal appears automatically for unauthenticated users
    await homePage.waitForLoginModalVisible();

    // Switch to signup mode (this also shows the email form)
    await emailAuthPage.clickSwitchModeLink();

    // Wait for email signup form to appear
    await emailAuthPage.waitForEmailSignupFormVisible();

    // Fill form with mismatched passwords
    await emailAuthPage.fillFirstName(firstName);
    await emailAuthPage.fillLastName(lastName);
    await emailAuthPage.fillEmailField(email);
    await emailAuthPage.fillPasswordField(password);
    await emailAuthPage.fillConfirmPasswordField(wrongPassword);

    // Attempt to submit
    await emailAuthPage.clickCreateAccountBtn();

    // Verify error message is shown
    await emailAuthPage.waitForSignupErrorVisible();
    const errorText = await emailAuthPage.getSignupErrorText();
    expect(errorText).toContain('Passwords do not match');

    // User should still not be logged in
    const isLoggedIn = await homePage.isLoggedIn();
    expect(isLoggedIn).toBeFalsy();
  });

  test('should fail signup with short password (less than 8 characters)', async () => {
    const email = generateTestEmail('short-password');
    const firstName = 'John';
    const lastName = 'Doe';
    const shortPassword = 'Pass12!';

    // Login modal appears automatically for unauthenticated users
    await homePage.waitForLoginModalVisible();

    // Switch to signup mode (this also shows the email form)
    await emailAuthPage.clickSwitchModeLink();

    // Wait for email signup form to appear
    await emailAuthPage.waitForEmailSignupFormVisible();

    // Fill form with short password
    await emailAuthPage.fillFirstName(firstName);
    await emailAuthPage.fillLastName(lastName);
    await emailAuthPage.fillEmailField(email);
    await emailAuthPage.fillPasswordField(shortPassword);
    await emailAuthPage.fillConfirmPasswordField(shortPassword);

    // Attempt to submit (should be blocked by HTML5 minLength validation)
    await emailAuthPage.clickCreateAccountBtn();

    // Verify modal is still open (form blocked by HTML5 validation)
    const isModalVisible = await homePage.isLoginModalVisible();
    expect(isModalVisible).toBeTruthy();

    // User should still not be logged in
    const isLoggedIn = await homePage.isLoggedIn();
    expect(isLoggedIn).toBeFalsy();
  });

  test('should successfully sign in with email after signup via API', async ({ request }) => {
    // Step 1: Create user via API (setup)
    const email = generateTestEmail('signin-test');
    const firstName = 'Jane';
    const lastName = 'Smith';
    const password = 'SecurePass456!';

    const signupApi = new ApiCalls();
    const signupResponse = await signupApi.signupWithEmail(firstName, lastName, email, password, request);
    expect(signupResponse.success).toBeTruthy();

    // Step 2: Test signin via UI
    // Login modal appears automatically for unauthenticated users
    await homePage.waitForLoginModalVisible();

    // Navigate to sign in with email form (modal opens in signin mode by default)
    await emailAuthPage.clickEmailAuthBtn();
    await emailAuthPage.waitForEmailSigninFormVisible();

    // Fill in signin credentials
    await emailAuthPage.fillEmailFieldSignin(email);
    await emailAuthPage.fillPasswordFieldSignin(password);

    // Submit signin form
    await emailAuthPage.clickSignInBtn();

    // Wait for successful signin (modal should close)
    await homePage.waitForLoginModalHidden(10000);

    // Verify user is logged in
    const isLoggedIn = await homePage.isLoggedIn();
    expect(isLoggedIn).toBeTruthy();

    // Verify correct user email
    await homePage.clickOnUserMenu();
    const userEmail = await emailAuthPage.getUserEmail();
    expect(userEmail).toBe(email);
  });

  test('should fail signin with wrong password', async ({ request }) => {
    // Step 1: Create user via API
    const email = generateTestEmail('wrong-password');
    const firstName = 'Bob';
    const lastName = 'Johnson';
    const correctPassword = 'CorrectPass789!';
    const wrongPassword = 'WrongPass123!';

    const signupApi = new ApiCalls();
    await signupApi.signupWithEmail(firstName, lastName, email, correctPassword, request);

    // Step 2: Attempt signin with wrong password
    // Login modal appears automatically for unauthenticated users
    await homePage.waitForLoginModalVisible();

    // Navigate to sign in with email form (modal opens in signin mode by default)
    await emailAuthPage.clickEmailAuthBtn();
    await emailAuthPage.waitForEmailSigninFormVisible();

    // Fill with wrong password
    await emailAuthPage.fillEmailFieldSignin(email);
    await emailAuthPage.fillPasswordFieldSignin(wrongPassword);

    // Attempt signin
    await emailAuthPage.clickSignInBtn();

    // Verify error message is shown
    await emailAuthPage.waitForSigninErrorVisible();
    const errorText = await emailAuthPage.getSigninErrorText();
    expect(errorText).toBeTruthy();

    // User should not be logged in
    const isLoggedIn = await homePage.isLoggedIn();
    expect(isLoggedIn).toBeFalsy();
  });

  test('should fail signin with non-existent email', async () => {
    const nonExistentEmail = generateTestEmail('non-existent');
    const password = 'SomePassword123!';

    // Login modal appears automatically for unauthenticated users
    await homePage.waitForLoginModalVisible();

    // Navigate to sign in with email form (modal opens in signin mode by default)
    await emailAuthPage.clickEmailAuthBtn();
    await emailAuthPage.waitForEmailSigninFormVisible();

    // Fill with non-existent credentials
    await emailAuthPage.fillEmailFieldSignin(nonExistentEmail);
    await emailAuthPage.fillPasswordFieldSignin(password);

    // Attempt signin
    await emailAuthPage.clickSignInBtn();

    // Verify error message is shown
    await emailAuthPage.waitForSigninErrorVisible();
    const errorText = await emailAuthPage.getSigninErrorText();
    expect(errorText).toBeTruthy();

    // User should not be logged in
    const isLoggedIn = await homePage.isLoggedIn();
    expect(isLoggedIn).toBeFalsy();
  });

  test('should toggle between signup and signin modes', async () => {
    // Login modal appears automatically for unauthenticated users
    await homePage.waitForLoginModalVisible();

    // Modal opens in signin mode by default, switch to signup mode
    // Note: switchMode() also shows the email form automatically
    await emailAuthPage.clickSwitchModeLink();

    // Wait for signup form (shown automatically after switch)
    await emailAuthPage.waitForEmailSignupFormVisible();

    // Verify signup form is visible
    let isSignupFormVisible = await emailAuthPage.isSignupFormVisible();
    expect(isSignupFormVisible).toBeTruthy();

    // Switch to signin
    await emailAuthPage.clickSwitchToSigninLink();
    await emailAuthPage.waitForEmailSigninFormVisible();

    // Verify signin form is visible
    const isSigninFormVisible = await emailAuthPage.isSigninFormVisible();
    expect(isSigninFormVisible).toBeTruthy();

    // Switch back to signup
    await emailAuthPage.clickSwitchToSignupLink();
    await emailAuthPage.waitForEmailSignupFormVisible();

    // Verify signup form is visible again
    isSignupFormVisible = await emailAuthPage.isSignupFormVisible();
    expect(isSignupFormVisible).toBeTruthy();
  });
});
