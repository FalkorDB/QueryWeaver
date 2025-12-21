import { Locator } from "@playwright/test";
import { waitForElementToBeVisible } from "../../infra/utils";
import BasePage from "../../infra/ui/basePage";

/**
 * UserProfile class handles all user profile dropdown and API tokens functionality.
 * This POM extends BasePage to work with BrowserWrapper.
 */
export class UserProfile extends BasePage {

  // ==================== LAYER 1: USER PROFILE LOCATORS ====================

  private get gitHubLink(): Locator {
    return this.page.getByTestId("github-repo-link");
  }

  private get userMenuBtn(): Locator {
    return this.page.getByTestId("user-menu-trigger");
  }

  private get userInfoSection(): Locator {
    return this.page.getByTestId("user-info-section");
  }

  private get userName(): Locator {
    return this.page.getByTestId("user-name-display");
  }

  private get userEmail(): Locator {
    return this.page.getByTestId("user-email-display");
  }

  private get apiTokensMenuItem(): Locator {
    return this.page.getByTestId("api-tokens-menu-item");
  }

  private get logoutMenuItem(): Locator {
    return this.page.getByTestId("logout-menu-item");
  }

  // Login screen locators (for logout verification)
  private get googleLoginBtn(): Locator {
    return this.page.getByTestId("google-login-btn");
  }

  private get githubLoginBtn(): Locator {
    return this.page.getByTestId("github-login-btn");
  }

  // ==================== TOKENS MODAL LOCATORS ====================

  private get generateTokenBtn(): Locator {
    return this.page.getByTestId("generate-token-btn");
  }

  private get newTokenAlert(): Locator {
    return this.page.getByTestId("new-token-alert");
  }

  private get newTokenInput(): Locator {
    return this.page.getByTestId("new-token-input");
  }

  private get toggleTokenVisibilityBtn(): Locator {
    return this.page.getByTestId("toggle-token-visibility");
  }

  private get copyTokenBtn(): Locator {
    return this.page.getByTestId("copy-token-btn");
  }

  private get tokensTable(): Locator {
    return this.page.getByTestId("tokens-table");
  }

  private getTokenRow(tokenId: string): Locator {
    return this.page.getByTestId(`token-row-${tokenId}`);
  }

  private getTokenValue(tokenId: string): Locator {
    return this.page.getByTestId(`token-value-${tokenId}`);
  }

  private getTokenCreatedDate(tokenId: string): Locator {
    return this.page.getByTestId(`token-created-${tokenId}`);
  }

  private getDeleteTokenBtn(tokenId: string): Locator {
    return this.page.getByTestId(`delete-token-btn-${tokenId}`);
  }

  private get deleteTokenConfirmDialog(): Locator {
    return this.page.getByTestId("delete-token-confirm-dialog");
  }

  private get deleteTokenCancelBtn(): Locator {
    return this.page.getByTestId("delete-token-cancel-btn");
  }

  private get deleteTokenConfirmAction(): Locator {
    return this.page.getByTestId("delete-token-confirm-action");
  }

  // ==================== LAYER 2: INTERACT WITH VISIBLE ====================

  private async interactWithUserMenuBtn(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.userMenuBtn);
    if (!isVisible) throw new Error("User menu button is not visible!");
    return this.userMenuBtn;
  }

  private async interactWithUserName(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.userName);
    if (!isVisible) throw new Error("User name is not visible!");
    return this.userName;
  }

  private async interactWithUserEmail(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.userEmail);
    if (!isVisible) throw new Error("User email is not visible!");
    return this.userEmail;
  }

  private async interactWithApiTokensMenuItem(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.apiTokensMenuItem);
    if (!isVisible) throw new Error("API tokens menu item is not visible!");
    return this.apiTokensMenuItem;
  }

  private async interactWithLogoutMenuItem(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.logoutMenuItem);
    if (!isVisible) throw new Error("Logout menu item is not visible!");
    return this.logoutMenuItem;
  }

  private async interactWithGenerateTokenBtn(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.generateTokenBtn);
    if (!isVisible) throw new Error("Generate token button is not visible!");
    return this.generateTokenBtn;
  }

  private async interactWithNewTokenInput(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.newTokenInput);
    if (!isVisible) throw new Error("New token input is not visible!");
    return this.newTokenInput;
  }

  private async interactWithToggleTokenVisibilityBtn(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.toggleTokenVisibilityBtn);
    if (!isVisible) throw new Error("Toggle token visibility button is not visible!");
    return this.toggleTokenVisibilityBtn;
  }

  private async interactWithCopyTokenBtn(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.copyTokenBtn);
    if (!isVisible) throw new Error("Copy token button is not visible!");
    return this.copyTokenBtn;
  }

  private async interactWithDeleteTokenBtn(tokenId: string): Promise<Locator> {
    const deleteBtn = this.getDeleteTokenBtn(tokenId);
    const isVisible = await waitForElementToBeVisible(deleteBtn);
    if (!isVisible) throw new Error(`Delete token button for ${tokenId} is not visible!`);
    return deleteBtn;
  }

  private async interactWithDeleteTokenConfirmAction(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.deleteTokenConfirmAction);
    if (!isVisible) throw new Error("Delete token confirm action is not visible!");
    return this.deleteTokenConfirmAction;
  }

  // ==================== LAYER 3: HIGH-LEVEL ACTIONS ====================

  async clickOnUserMenu(): Promise<void> {
    const element = await this.interactWithUserMenuBtn();
    await element.click();
  }

  async clickOnApiTokensMenuItem(): Promise<void> {
    const element = await this.interactWithApiTokensMenuItem();
    await element.click();
  }

  async clickOnLogout(): Promise<void> {
    const element = await this.interactWithLogoutMenuItem();
    await element.click();
  }

  async clickOnGenerateToken(): Promise<void> {
    const element = await this.interactWithGenerateTokenBtn();
    await element.click();
  }

  async clickOnToggleTokenVisibility(): Promise<void> {
    const element = await this.interactWithToggleTokenVisibilityBtn();
    await element.click();
  }

  async clickOnCopyToken(): Promise<void> {
    const element = await this.interactWithCopyTokenBtn();
    await element.click();
  }

  async clickOnDeleteToken(tokenId: string): Promise<void> {
    const element = await this.interactWithDeleteTokenBtn(tokenId);
    await element.click();
  }

  async clickOnDeleteTokenConfirmAction(): Promise<void> {
    const element = await this.interactWithDeleteTokenConfirmAction();
    await element.click();
  }

  async deleteTokenAndWaitForResponse(tokenId: string): Promise<number> {
    // Set up listener for the delete API call BEFORE clicking delete
    const deleteResponsePromise = this.page.waitForResponse(
      response => response.url().includes(`/tokens/${tokenId}`) && response.request().method() === 'DELETE',
      { timeout: 10000 }
    );

    // Delete the token
    await this.clickOnDeleteToken(tokenId);
    await this.clickOnDeleteTokenConfirmAction();
    
    // Wait for the delete API call to complete and return status
    const deleteResponse = await deleteResponsePromise;
    return deleteResponse.status();
  }

  // ==================== VERIFICATION METHODS ====================

  async isUserMenuVisible(): Promise<boolean> {
    return await waitForElementToBeVisible(this.userMenuBtn);
  }

  async isUserInfoSectionVisible(): Promise<boolean> {
    return await waitForElementToBeVisible(this.userInfoSection);
  }

  async getUserName(): Promise<string | null> {
    const element = await this.interactWithUserName();
    return await element.textContent();
  }

  async getUserEmail(): Promise<string | null> {
    const element = await this.interactWithUserEmail();
    return await element.textContent();
  }

  async isApiTokensMenuItemVisible(): Promise<boolean> {
    return await waitForElementToBeVisible(this.apiTokensMenuItem);
  }

  async isLogoutMenuItemVisible(): Promise<boolean> {
    return await waitForElementToBeVisible(this.logoutMenuItem);
  }

  async isGoogleLoginBtnVisible(): Promise<boolean> {
    try {
      return await this.googleLoginBtn.isVisible();
    } catch {
      return false;
    }
  }

  async isGithubLoginBtnVisible(): Promise<boolean> {
    try {
      return await this.githubLoginBtn.isVisible();
    } catch {
      return false;
    }
  }

  async isGenerateTokenBtnVisible(): Promise<boolean> {
    return await waitForElementToBeVisible(this.generateTokenBtn);
  }

  async isNewTokenAlertVisible(): Promise<boolean> {
    return await waitForElementToBeVisible(this.newTokenAlert);
  }

  async getNewTokenValue(): Promise<string | null> {
    const element = await this.interactWithNewTokenInput();
    return await element.inputValue();
  }

  extractTokenId(tokenValue: string): string {
    // Token ID is the last 4 characters of the full token
    return tokenValue.slice(-4);
  }

  async isCopyTokenBtnVisible(): Promise<boolean> {
    return await waitForElementToBeVisible(this.copyTokenBtn);
  }

  async isTokensTableVisible(): Promise<boolean> {
    return await waitForElementToBeVisible(this.tokensTable);
  }

  async isTokenRowVisible(tokenId: string): Promise<boolean> {
    return await waitForElementToBeVisible(this.getTokenRow(tokenId));
  }

  async getTokenValueText(tokenId: string): Promise<string | null> {
    const element = this.getTokenValue(tokenId);
    const isVisible = await waitForElementToBeVisible(element);
    if (!isVisible) throw new Error(`Token value for ${tokenId} is not visible!`);
    return await element.textContent();
  }

  async getTokenCreatedDateText(tokenId: string): Promise<string | null> {
    const element = this.getTokenCreatedDate(tokenId);
    const isVisible = await waitForElementToBeVisible(element);
    if (!isVisible) throw new Error(`Token created date for ${tokenId} is not visible!`);
    return await element.textContent();
  }

  async isDeleteTokenConfirmDialogVisible(): Promise<boolean> {
    return await waitForElementToBeVisible(this.deleteTokenConfirmDialog);
  }

  async getAllTokenRows(): Promise<Locator[]> {
    // Try to wait for token rows, but don't fail if none exist
    try {
      await this.page.waitForSelector('[data-testid^="token-row-"]', { timeout: 5000 });
    } catch {
      // No token rows found, return empty array
      return [];
    }
    return await this.page.locator('[data-testid^="token-row-"]').all();
  }

  async getTokenCount(): Promise<number> {
    const rows = await this.getAllTokenRows();
    return rows.length;
  }

  async waitForTimeout(ms: number): Promise<void> {
    await this.page.waitForTimeout(ms);
  }

  async waitForTokenRowToDisappear(tokenId: string): Promise<void> {
    const tokenRowSelector = `[data-testid="token-row-${tokenId}"]`;
    await this.page.waitForSelector(tokenRowSelector, { state: 'detached', timeout: 10000 });
  }

  async waitForLoginUrl(): Promise<void> {
    await this.page.waitForURL(/.*login.*/i, { timeout: 10000 });
  }

  async getCurrentUrl(): Promise<string> {
    return this.page.url();
  }

  async getClipboardText(): Promise<string> {
    return await this.page.evaluate(() => navigator.clipboard.readText());
  }

  async getTokenInputType(): Promise<string | null> {
    return await this.newTokenInput.getAttribute('type');
  }

  async pressEscape(): Promise<void> {
    await this.page.keyboard.press('Escape');
  }

  async reloadPage(): Promise<void> {
    await this.page.reload();
  }

  async getFirstTokenIdFromRows(): Promise<string> {
    const tokenRows = await this.getAllTokenRows();
    const firstTokenRow = tokenRows[0];
    const firstTokenId = await firstTokenRow.getAttribute('data-testid');
    return firstTokenId?.replace('token-row-', '') || '';
  }

  async getLastTokenIdFromRows(): Promise<string> {
    const tokenRows = await this.getAllTokenRows();
    const lastTokenRow = tokenRows[tokenRows.length - 1];
    const lastTokenId = await lastTokenRow.getAttribute('data-testid');
    return lastTokenId?.replace('token-row-', '') || '';
  }

  async getTokenIdsFromRows(): Promise<string[]> {
    const rows = await this.getAllTokenRows();
    const tokenIds: string[] = [];

    for (const row of rows) {
      const rowTestId = await row.getAttribute('data-testid');
      const tokenId = rowTestId?.replace('token-row-', '') || '';
      tokenIds.push(tokenId);
    }

    return tokenIds;
  }

  async findTokenInList(tokenValue: string): Promise<boolean> {
    const tokenRows = await this.getAllTokenRows();

    for (const row of tokenRows) {
      const rowTestId = await row.getAttribute('data-testid');
      const tokenId = rowTestId?.replace('token-row-', '') || '';

      if (tokenValue?.includes(tokenId)) {
        const tokenValueText = await this.getTokenValueText(tokenId);
        const createdDate = await this.getTokenCreatedDateText(tokenId);

        // Verify token format and date exist
        if (tokenValueText?.includes('****') &&
            tokenValueText?.includes(tokenId) &&
            createdDate) {
          return true;
        }
      }
    }

    return false;
  }

  async isGitHubLinkVisible(): Promise<boolean> {
    return await waitForElementToBeVisible(this.gitHubLink);
  }

  async getGitHubLinkUrl(): Promise<string | null> {
    const isVisible = await waitForElementToBeVisible(this.gitHubLink);
    if (!isVisible) throw new Error("GitHub link is not visible!");
    return await this.gitHubLink.getAttribute('href');
  }
}
