import { test, expect } from '@playwright/test';
import { getBaseUrl, getTestUser3 } from '../config/urls';
import { UserProfile } from '../logic/pom/userProfile';
import BrowserWrapper from '../infra/ui/browserWrapper';
import ApiCalls from '../logic/api/apiCalls';

// User Profile tests - uses authenticated storageState from auth.setup
test.describe('User Profile Tests', () => {
  let browser: BrowserWrapper;

  test.beforeEach(async () => {
    browser = new BrowserWrapper();
  });

  test.afterEach(async () => {
    await browser.closeBrowser();
  });

  test('GitHub repository link is visible and correct', async () => {
    const userProfile = await browser.createNewPage(UserProfile, getBaseUrl());
    await browser.setPageToFullScreen();

    const isGitHubLinkVisible = await userProfile.isGitHubLinkVisible();
    expect(isGitHubLinkVisible).toBeTruthy();

    const gitHubUrl = await userProfile.getGitHubLinkUrl();
    expect(gitHubUrl).toBe('https://github.com/FalkorDB/QueryWeaver');
  });

  test('viewable email and username fields in user dropdown', async () => {
    const userProfile = await browser.createNewPage(UserProfile, getBaseUrl());
    await browser.setPageToFullScreen();

    await userProfile.clickOnUserMenu();

    const isUserInfoVisible = await userProfile.isUserInfoSectionVisible();
    expect(isUserInfoVisible).toBeTruthy();

    const userName = await userProfile.getUserName();
    expect(userName).toBeTruthy();
    expect(userName).not.toBe('');

    const userEmail = await userProfile.getUserEmail();
    expect(userEmail).toBeTruthy();
    expect(userEmail).not.toBe('');
    expect(userEmail).toContain('@');
  });

  test('logout button functionality', async () => {
    // Step 1: Create page first (without navigation to get access to request context)
    const userProfile = await browser.createNewPage(UserProfile, getBaseUrl());
    await browser.setPageToFullScreen();
    
    // Step 2: Login via API using user3 credentials and page's request context
    const apiCall = new ApiCalls();
    const { email, password } = getTestUser3();
    
    // Get the page to access its request context
    const page = await browser.getPage();
    
    // Login via API using the page's request context - this shares cookies with the browser
    const loginResponse = await apiCall.loginWithEmail(email, password, page.request);
    expect(loginResponse.success).toBeTruthy();

    // Step 3: Navigate to the page to establish the session in the browser
    await page.goto(getBaseUrl());
    await userProfile.waitForTimeout(1000);

    // Step 4: Verify user is logged in and proceed with logout
    await userProfile.clickOnUserMenu();

    const isLogoutVisible = await userProfile.isLogoutMenuItemVisible();
    expect(isLogoutVisible).toBeTruthy();

    await userProfile.clickOnLogout();

    // Verify user is logged out - user menu should not be visible
    const isUserMenuVisible = await userProfile.isUserMenuVisible();
    expect(isUserMenuVisible).toBeFalsy();

    // Verify welcome screen with login options is shown
    const isGoogleLoginVisible = await userProfile.isGoogleLoginBtnVisible();
    const isGithubLoginVisible = await userProfile.isGithubLoginBtnVisible();

    // At least one login option should be visible
    expect(isGoogleLoginVisible || isGithubLoginVisible).toBeTruthy();
  });

  test('generate token and copy token', async () => {
    const userProfile = await browser.createNewPage(UserProfile, getBaseUrl());
    await browser.setPageToFullScreen();

    await userProfile.clickOnUserMenu();
    await userProfile.clickOnApiTokensMenuItem();
    await userProfile.waitForTimeout(500);

    const isGenerateTokenBtnVisible = await userProfile.isGenerateTokenBtnVisible();
    expect(isGenerateTokenBtnVisible).toBeTruthy();

    await userProfile.clickOnGenerateToken();
    await userProfile.waitForTimeout(1000);

    const isNewTokenAlertVisible = await userProfile.isNewTokenAlertVisible();
    expect(isNewTokenAlertVisible).toBeTruthy();

    const tokenValue = await userProfile.getNewTokenValue();
    expect(tokenValue).toBeTruthy();
    expect(tokenValue).not.toBe('');

    const isCopyBtnVisible = await userProfile.isCopyTokenBtnVisible();
    expect(isCopyBtnVisible).toBeTruthy();

    await userProfile.clickOnCopyToken();

    const clipboardText = await userProfile.getClipboardText();
    expect(clipboardText).toBe(tokenValue);
  });

  test('revoke/delete token', async () => {
    const userProfile = await browser.createNewPage(UserProfile, getBaseUrl());
    await browser.setPageToFullScreen();

    await userProfile.clickOnUserMenu();
    await userProfile.clickOnApiTokensMenuItem();

    // Generate a token
    await userProfile.clickOnGenerateToken();
    await userProfile.waitForTimeout(1000);

    const tokenValue = await userProfile.getNewTokenValue();
    expect(tokenValue).toBeTruthy();

    const tokenId = userProfile.extractTokenId(tokenValue || '');
    expect(tokenId.length).toBe(4);

    // Verify the token exists in the list before deletion
    const tokenIdsBeforeDelete = await userProfile.getTokenIdsFromRows();
    expect(tokenIdsBeforeDelete).toContain(tokenId);

    // Delete the token and wait for API response
    const deleteStatus = await userProfile.deleteTokenAndWaitForResponse(tokenId);
    expect(deleteStatus).toBe(200);

    // Verify the specific token was deleted from the list
    const tokenIdsAfterDelete = await userProfile.getTokenIdsFromRows();
    expect(tokenIdsAfterDelete).not.toContain(tokenId);
  });

  test('created token appears in list with correct details', async () => {
    const userProfile = await browser.createNewPage(UserProfile, getBaseUrl());
    await browser.setPageToFullScreen();

    await userProfile.clickOnUserMenu();
    await userProfile.clickOnApiTokensMenuItem();

    await userProfile.clickOnGenerateToken();
    await userProfile.waitForTimeout(1000);

    const tokenValue = await userProfile.getNewTokenValue();
    expect(tokenValue).toBeTruthy();
    
    // Extract token ID (last 4 characters) using the POM helper
    const tokenId = userProfile.extractTokenId(tokenValue || '');
    expect(tokenId).toBeTruthy();
    expect(tokenId.length).toBe(4);

    // Wait for table to update
    await userProfile.waitForTimeout(1000);

    // Verify token value in UI shows masked format: ****xxxx
    const tokenValueInUI = await userProfile.getTokenValueText(tokenId);
    expect(tokenValueInUI).toBe(`****${tokenId}`);
    
    // Verify created date exists
    const createdDate = await userProfile.getTokenCreatedDateText(tokenId);
    expect(createdDate).toBeTruthy();
  });

  test('hide and unhide token visibility', async () => {
    const userProfile = await browser.createNewPage(UserProfile, getBaseUrl());
    await browser.setPageToFullScreen();

    await userProfile.clickOnUserMenu();
    await userProfile.clickOnApiTokensMenuItem();
    await userProfile.clickOnGenerateToken();

    const tokenValue = await userProfile.getNewTokenValue();
    expect(tokenValue).toBeTruthy();

    // Initially token should be hidden (password type)
    const tokenInputType = await userProfile.getTokenInputType();
    expect(tokenInputType).toBe('password');

    await userProfile.clickOnToggleTokenVisibility();

    const tokenInputTypeAfterShow = await userProfile.getTokenInputType();
    expect(tokenInputTypeAfterShow).toBe('text');

    // Click to hide token again
    await userProfile.clickOnToggleTokenVisibility();

    const tokenInputTypeAfterHide = await userProfile.getTokenInputType();
    expect(tokenInputTypeAfterHide).toBe('password');
  });

  test('one-time token copy message after refresh', async () => {
    const userProfile = await browser.createNewPage(UserProfile, getBaseUrl());
    await browser.setPageToFullScreen();

    await userProfile.clickOnUserMenu();
    await userProfile.clickOnApiTokensMenuItem();
    await userProfile.clickOnGenerateToken();

    // Verify new token alert is visible
    const isNewTokenAlertVisible = await userProfile.isNewTokenAlertVisible();
    expect(isNewTokenAlertVisible).toBeTruthy();

    const isCopyBtnVisible = await userProfile.isCopyTokenBtnVisible();
    expect(isCopyBtnVisible).toBeTruthy();

    await userProfile.pressEscape();
    await userProfile.reloadPage();

    // Open tokens modal again
    await userProfile.clickOnUserMenu();
    await userProfile.clickOnApiTokensMenuItem();

    // Verify new token alert is NOT visible after refresh
    const isNewTokenAlertVisibleAfterRefresh = await userProfile.isNewTokenAlertVisible();
    expect(isNewTokenAlertVisibleAfterRefresh).toBeFalsy();

    const isCopyBtnVisibleAfterRefresh = await userProfile.isCopyTokenBtnVisible();
    expect(isCopyBtnVisibleAfterRefresh).toBeFalsy();
  });

  test('create two tokens and verify via UI', async () => {
    const userProfile = await browser.createNewPage(UserProfile, getBaseUrl());
    await browser.setPageToFullScreen();

    await userProfile.clickOnUserMenu();
    await userProfile.clickOnApiTokensMenuItem();

    // Generate first token
    await userProfile.clickOnGenerateToken();

    const firstTokenValue = await userProfile.getNewTokenValue();
    const firstTokenId = userProfile.extractTokenId(firstTokenValue || '');

    // Generate second token
    await userProfile.clickOnGenerateToken();

    const secondTokenValue = await userProfile.getNewTokenValue();
    const secondTokenId = userProfile.extractTokenId(secondTokenValue || '');

    // Verify both tokens exist in the list by their IDs
    const tokenIds = await userProfile.getTokenIdsFromRows();
    expect(tokenIds).toContain(firstTokenId);
    expect(tokenIds).toContain(secondTokenId);
  });

  test('multi-user token isolation', async () => {
    // This test verifies that tokens are isolated between different users
    // User1 should not see User2's tokens and vice versa
    
    // Create page for user1 using BrowserWrapper's existing createNewPage
    const userProfile1 = await browser.createNewPage(UserProfile, getBaseUrl());
    await browser.setPageToFullScreen();
    
    // Generate a token as user1
    await userProfile1.clickOnUserMenu();
    await userProfile1.clickOnApiTokensMenuItem();
    await userProfile1.clickOnGenerateToken();
    
    // Get last token ID (the newly created one)
    await userProfile1.waitForTimeout(1000);
    const lastTokenIdUser1 = await userProfile1.getLastTokenIdFromRows();
    
    // Close user1's context (this will force a new context for user2)
    await browser.closeContext();
    
    // Create page for user2 with user2's storage state
    const userProfile2 = await browser.createNewPage(UserProfile, getBaseUrl(), 'e2e/.auth/user2.json');
    await browser.setPageToFullScreen();
    
    // Check user2's tokens
    await userProfile2.clickOnUserMenu();
    await userProfile2.clickOnApiTokensMenuItem();
    await userProfile2.waitForTimeout(500);
    
    // Verify that user2 cannot see user1's token
    const user2TokenIds = await userProfile2.getTokenIdsFromRows();
    expect(user2TokenIds).not.toContain(lastTokenIdUser1);
  });
});
