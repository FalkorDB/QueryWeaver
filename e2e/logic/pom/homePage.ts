import { Locator, Page } from "@playwright/test";
import { waitForElementToBeVisible, waitForElementToBeEnabled } from "../../infra/utils";
import BasePage from "../../infra/ui/basePage";
import ApiCalls from "../api/apiCalls";
import { getTestDatabases } from "../../config/urls";

export class HomePage extends BasePage {
  // ==================== LOCATORS ====================

  // Header Elements
  private get logoImage(): Locator {
    return this.page.getByTestId("logo");
  }

  private get databaseStatusBadge(): Locator {
    return this.page.getByTestId("database-status-badge");
  }

  private get githubStarsLink(): Locator {
    return this.page.getByTestId("github-stars-link");
  }

  private get signInBtn(): Locator {
    return this.page.getByTestId("sign-in-btn");
  }

  private get userMenuTrigger(): Locator {
    return this.page.getByTestId("user-menu-trigger");
  }

  private get apiTokensMenuItem(): Locator {
    return this.page.getByTestId("api-tokens-menu-item");
  }

  private get logoutMenuItem(): Locator {
    return this.page.getByTestId("logout-menu-item");
  }

  // Database Controls
  private get refreshSchemaBtn(): Locator {
    return this.page.getByTestId("refresh-schema-btn");
  }

  private get databaseSelectorTrigger(): Locator {
    return this.page.getByTestId("database-selector-trigger");
  }

  private get connectDatabaseBtn(): Locator {
    return this.page.getByTestId("connect-database-btn");
  }

  private get uploadSchemaBtn(): Locator {
    return this.page.getByTestId("upload-schema-btn");
  }

  private get schemaUploadInput(): Locator {
    return this.page.getByTestId("schema-upload-input");
  }

  // Database Dropdown Items
  private getDatabaseOption(databaseId: string): Locator {
    return this.page.getByTestId(`database-option-${databaseId}`);
  }

  private getDeleteGraphBtn(databaseId: string): Locator {
    return this.page.getByTestId(`delete-graph-btn-${databaseId}`);
  }

  // Chat Interface Elements
  private get chatInterface(): Locator {
    return this.page.getByTestId("chat-interface");
  }

  private get queryTextarea(): Locator {
    return this.page.getByTestId("query-textarea");
  }

  private get sendQueryBtn(): Locator {
    return this.page.getByTestId("send-query-btn");
  }

  // Chat Messages
  private get userMessage(): Locator {
    return this.page.getByTestId("user-message");
  }

  private get aiMessage(): Locator {
    return this.page.getByTestId("ai-message");
  }

  private get sqlQueryMessage(): Locator {
    return this.page.getByTestId("sql-query-message");
  }

  private get queryResultsMessage(): Locator {
    return this.page.getByTestId("query-results-message");
  }

  private get resultsTable(): Locator {
    return this.page.getByTestId("results-table");
  }

  // Modals
  private get loginModal(): Locator {
    return this.page.getByTestId("login-modal");
  }

  private get databaseModal(): Locator {
    return this.page.getByTestId("database-modal");
  }

  private get deleteDatabaseModal(): Locator {
    return this.page.getByTestId("delete-database-modal");
  }

  private get tokensModal(): Locator {
    return this.page.getByTestId("tokens-modal");
  }

  // Login Modal Elements
  private get googleLoginBtn(): Locator {
    return this.page.getByTestId("google-login-btn");
  }

  private get githubLoginBtn(): Locator {
    return this.page.getByTestId("github-login-btn");
  }

  // Database Modal Elements
  private get databaseTypeSelect(): Locator {
    // SelectTrigger is wrapped in a div with data-testid, find the button inside
    return this.page.getByTestId("database-type-select").locator('button');
  }

  private get connectionModeUrl(): Locator {
    return this.page.getByTestId("connection-mode-url");
  }

  private get connectionModeManual(): Locator {
    return this.page.getByTestId("connection-mode-manual");
  }

  private get connectionUrlInput(): Locator {
    return this.page.getByTestId("connection-url-input");
  }

  private get hostInput(): Locator {
    return this.page.locator('#host');
  }

  private get portInput(): Locator {
    return this.page.locator('#port');
  }

  private get databaseNameInput(): Locator {
    return this.page.locator('#database');
  }

  private get usernameInput(): Locator {
    return this.page.locator('#username');
  }

  private get passwordInput(): Locator {
    return this.page.locator('#password');
  }

  private get databaseModalConnectBtn(): Locator {
    return this.page.getByTestId("connect-database-button");
  }

  private get databaseModalCancelBtn(): Locator {
    return this.page.getByTestId("database-modal-cancel");
  }

  // Delete Modal Elements
  private get deleteModalConfirmBtn(): Locator {
    return this.page.getByTestId("delete-modal-confirm");
  }

  private get deleteModalCancelBtn(): Locator {
    return this.page.getByTestId("delete-modal-cancel");
  }

  // Tokens Modal Elements
  private get generateTokenBtn(): Locator {
    return this.page.getByTestId("generate-token-btn");
  }

  private get newTokenInput(): Locator {
    return this.page.getByTestId("new-token-input");
  }

  private get copyTokenBtn(): Locator {
    return this.page.getByTestId("copy-token-btn");
  }

  private get tokensTable(): Locator {
    return this.page.getByTestId("tokens-table");
  }

  private getDeleteTokenBtn(tokenId: string): Locator {
    return this.page.getByTestId(`delete-token-btn-${tokenId}`);
  }

  // Toast Elements
  private get toastNotification(): Locator {
    return this.page.getByTestId("toast-notification");
  }

  private get toastTitle(): Locator {
    return this.page.getByTestId("toast-title");
  }

  private get toastDescription(): Locator {
    return this.page.getByTestId("toast-description");
  }

  // Processing Indicator
  private get processingQueryIndicator(): Locator {
    return this.page.getByTestId("processing-query-indicator");
  }

  // ==================== LAYER 2: INTERACT WHEN VISIBLE ====================

  // Header Elements - InteractWhenVisible
  private async interactWithLogoImage(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.logoImage);
    if (!isVisible) throw new Error("Logo image is not visible!");
    return this.logoImage;
  }

  private async interactWithDatabaseStatusBadge(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.databaseStatusBadge);
    if (!isVisible) throw new Error("Database status badge is not visible!");
    return this.databaseStatusBadge;
  }

  private async interactWithGithubStarsLink(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.githubStarsLink);
    if (!isVisible) throw new Error("GitHub stars link is not visible!");
    return this.githubStarsLink;
  }

  private async interactWithSignInBtn(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.signInBtn);
    if (!isVisible) throw new Error("Sign in button is not visible!");
    return this.signInBtn;
  }

  private async interactWithUserMenuTrigger(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.userMenuTrigger);
    if (!isVisible) throw new Error("User menu trigger is not visible!");
    return this.userMenuTrigger;
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

  // Database Controls - InteractWhenVisible
  private async interactWithRefreshSchemaBtn(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.refreshSchemaBtn);
    if (!isVisible) throw new Error("Refresh schema button is not visible!");
    const isEnabled = await waitForElementToBeEnabled(this.refreshSchemaBtn);
    if (!isEnabled) throw new Error("Refresh schema button is not enabled!");
    return this.refreshSchemaBtn;
  }

  private async interactWithDatabaseSelectorTrigger(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.databaseSelectorTrigger);
    if (!isVisible) throw new Error("Database selector trigger is not visible!");
    return this.databaseSelectorTrigger;
  }

  private async interactWithConnectDatabaseBtn(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.connectDatabaseBtn);
    if (!isVisible) throw new Error("Connect database button is not visible!");
    return this.connectDatabaseBtn;
  }

  private async interactWithUploadSchemaBtn(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.uploadSchemaBtn);
    if (!isVisible) throw new Error("Upload schema button is not visible!");
    return this.uploadSchemaBtn;
  }

  private async interactWithSchemaUploadInput(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.schemaUploadInput);
    if (!isVisible) throw new Error("Schema upload input is not visible!");
    return this.schemaUploadInput;
  }

  // Database Dropdown Items - InteractWhenVisible
  private async interactWithDatabaseOption(databaseId: string): Promise<Locator> {
    const dbOption = this.getDatabaseOption(databaseId);
    const isVisible = await waitForElementToBeVisible(dbOption);
    if (!isVisible) throw new Error(`Database option ${databaseId} is not visible!`);
    return dbOption;
  }

  private async interactWithDeleteGraphBtn(databaseId: string): Promise<Locator> {
    const deleteBtn = this.getDeleteGraphBtn(databaseId);
    const isVisible = await waitForElementToBeVisible(deleteBtn);
    if (!isVisible) throw new Error(`Delete graph button for ${databaseId} is not visible!`);
    return deleteBtn;
  }

  // Chat Interface Elements - InteractWhenVisible
  private async interactWithChatInterface(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.chatInterface);
    if (!isVisible) throw new Error("Chat interface is not visible!");
    return this.chatInterface;
  }

  private async interactWithQueryTextarea(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.queryTextarea);
    if (!isVisible) throw new Error("Query textarea is not visible!");
    return this.queryTextarea;
  }

  private async interactWithSendQueryBtn(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.sendQueryBtn);
    if (!isVisible) throw new Error("Send query button is not visible!");
    const isEnabled = await waitForElementToBeEnabled(this.sendQueryBtn);
    if (!isEnabled) throw new Error("Send query button is not enabled!");
    return this.sendQueryBtn;
  }

  // Chat Messages - InteractWhenVisible
  private async interactWithUserMessage(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.userMessage);
    if (!isVisible) throw new Error("User message is not visible!");
    return this.userMessage;
  }

  private async interactWithAiMessage(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.aiMessage);
    if (!isVisible) throw new Error("AI message is not visible!");
    return this.aiMessage;
  }

  private async interactWithSqlQueryMessage(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.sqlQueryMessage);
    if (!isVisible) throw new Error("SQL query message is not visible!");
    return this.sqlQueryMessage;
  }

  private async interactWithQueryResultsMessage(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.queryResultsMessage);
    if (!isVisible) throw new Error("Query results message is not visible!");
    return this.queryResultsMessage;
  }

  private async interactWithResultsTable(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.resultsTable);
    if (!isVisible) throw new Error("Results table is not visible!");
    return this.resultsTable;
  }

  // Modals - InteractWhenVisible
  private async interactWithLoginModal(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.loginModal);
    if (!isVisible) throw new Error("Login modal is not visible!");
    return this.loginModal;
  }

  private async interactWithDatabaseModal(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.databaseModal);
    if (!isVisible) throw new Error("Database modal is not visible!");
    return this.databaseModal;
  }

  private async interactWithDeleteDatabaseModal(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.deleteDatabaseModal);
    if (!isVisible) throw new Error("Delete database modal is not visible!");
    return this.deleteDatabaseModal;
  }

  private async interactWithTokensModal(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.tokensModal);
    if (!isVisible) throw new Error("Tokens modal is not visible!");
    return this.tokensModal;
  }

  // Login Modal Elements - InteractWhenVisible
  private async interactWithGoogleLoginBtn(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.googleLoginBtn);
    if (!isVisible) throw new Error("Google login button is not visible!");
    return this.googleLoginBtn;
  }

  private async interactWithGithubLoginBtn(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.githubLoginBtn);
    if (!isVisible) throw new Error("GitHub login button is not visible!");
    return this.githubLoginBtn;
  }

  // Database Modal Elements - InteractWhenVisible
  private async interactWithDatabaseTypeSelect(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.databaseTypeSelect);
    if (!isVisible) throw new Error("Database type select is not visible!");
    return this.databaseTypeSelect;
  }

  private async interactWithConnectionModeUrl(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.connectionModeUrl);
    if (!isVisible) throw new Error("Connection mode URL button is not visible!");
    return this.connectionModeUrl;
  }

  private async interactWithConnectionModeManual(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.connectionModeManual);
    if (!isVisible) throw new Error("Connection mode Manual button is not visible!");
    return this.connectionModeManual;
  }

  private async interactWithConnectionUrlInput(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.connectionUrlInput);
    if (!isVisible) throw new Error("Connection URL input is not visible!");
    return this.connectionUrlInput;
  }

  private async interactWithHostInput(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.hostInput);
    if (!isVisible) throw new Error("Host input is not visible!");
    return this.hostInput;
  }

  private async interactWithPortInput(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.portInput);
    if (!isVisible) throw new Error("Port input is not visible!");
    return this.portInput;
  }

  private async interactWithDatabaseNameInput(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.databaseNameInput);
    if (!isVisible) throw new Error("Database name input is not visible!");
    return this.databaseNameInput;
  }

  private async interactWithUsernameInput(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.usernameInput);
    if (!isVisible) throw new Error("Username input is not visible!");
    return this.usernameInput;
  }

  private async interactWithPasswordInput(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.passwordInput);
    if (!isVisible) throw new Error("Password input is not visible!");
    return this.passwordInput;
  }

  private async interactWithDatabaseModalConnectBtn(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.databaseModalConnectBtn);
    if (!isVisible) throw new Error("Database modal connect button is not visible!");
    return this.databaseModalConnectBtn;
  }

  private async interactWithDatabaseModalCancelBtn(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.databaseModalCancelBtn);
    if (!isVisible) throw new Error("Database modal cancel button is not visible!");
    return this.databaseModalCancelBtn;
  }

  // Delete Modal Elements - InteractWhenVisible
  private async interactWithDeleteModalConfirmBtn(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.deleteModalConfirmBtn);
    if (!isVisible) throw new Error("Delete modal confirm button is not visible!");
    return this.deleteModalConfirmBtn;
  }

  private async interactWithDeleteModalCancelBtn(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.deleteModalCancelBtn);
    if (!isVisible) throw new Error("Delete modal cancel button is not visible!");
    return this.deleteModalCancelBtn;
  }

  // Tokens Modal Elements - InteractWhenVisible
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

  private async interactWithCopyTokenBtn(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.copyTokenBtn);
    if (!isVisible) throw new Error("Copy token button is not visible!");
    return this.copyTokenBtn;
  }

  private async interactWithTokensTable(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.tokensTable);
    if (!isVisible) throw new Error("Tokens table is not visible!");
    return this.tokensTable;
  }

  private async interactWithDeleteTokenBtn(tokenId: string): Promise<Locator> {
    const deleteBtn = this.getDeleteTokenBtn(tokenId);
    const isVisible = await waitForElementToBeVisible(deleteBtn);
    if (!isVisible) throw new Error(`Delete token button for ${tokenId} is not visible!`);
    return deleteBtn;
  }

  // ==================== LAYER 3: HIGH-LEVEL ACTION FUNCTIONS ====================

  // Navigation Functions
  async clickOnSignInBtn(): Promise<void> {
    const element = await this.interactWithSignInBtn();
    await element.click();
  }

  async clickOnUserMenu(): Promise<void> {
    const element = await this.interactWithUserMenuTrigger();
    await element.click();
  }

  async clickOnLogout(): Promise<void> {
    const element = await this.interactWithLogoutMenuItem();
    await element.click();
  }

  async clickOnAPITokensMenuItem(): Promise<void> {
    const element = await this.interactWithApiTokensMenuItem();
    await element.click();
  }

  // Database Management Functions
  async clickOnRefreshSchema(): Promise<void> {
    const element = await this.interactWithRefreshSchemaBtn();
    await element.click();
  }

  async clickOnDatabaseSelector(): Promise<void> {
    const element = await this.interactWithDatabaseSelectorTrigger();
    await element.click();
  }

  async selectDatabase(databaseId: string): Promise<void> {
    await this.clickOnDatabaseSelector();
    const element = await this.interactWithDatabaseOption(databaseId);
    await element.click();
  }

  async clickOnConnectDatabase(): Promise<void> {
    const element = await this.interactWithConnectDatabaseBtn();
    await element.click();
  }

  async clickOnDeleteGraph(databaseId: string): Promise<void> {
    const element = await this.interactWithDeleteGraphBtn(databaseId);
    await element.click();
  }

  // Chat Functions
  async enterQuery(query: string): Promise<void> {
    const element = await this.interactWithQueryTextarea();
    await element.fill(query);
  }

  async clickOnSendQuery(): Promise<void> {
    const element = await this.interactWithSendQueryBtn();
    await element.click();
  }

  async sendQuery(query: string): Promise<void> {
    await this.enterQuery(query);
    await this.clickOnSendQuery();
  }

  // Login Modal Functions
  async clickOnGoogleLogin(): Promise<void> {
    const element = await this.interactWithGoogleLoginBtn();
    await element.click();
  }

  async clickOnGithubLogin(): Promise<void> {
    const element = await this.interactWithGithubLoginBtn();
    await element.click();
  }

  // Database Connection Modal Functions
  async selectDatabaseType(type: "postgresql" | "mysql"): Promise<void> {
    const element = await this.interactWithDatabaseTypeSelect();
    await element.click();
    // Select by test-id
    await this.page.getByTestId(`${type}-option`).click();
  }

  async selectConnectionModeUrl(): Promise<void> {
    const element = await this.interactWithConnectionModeUrl();
    await element.click();
  }

  async selectConnectionModeManual(): Promise<void> {
    const element = await this.interactWithConnectionModeManual();
    await element.click();
  }

  async enterConnectionUrl(url: string): Promise<void> {
    const element = await this.interactWithConnectionUrlInput();
    await element.fill(url);
  }

  async enterConnectionDetails(
    host: string,
    port: string,
    database: string,
    username: string,
    password: string
  ): Promise<void> {
    const hostElement = await this.interactWithHostInput();
    await hostElement.fill(host);

    const portElement = await this.interactWithPortInput();
    await portElement.fill(port);

    const databaseElement = await this.interactWithDatabaseNameInput();
    await databaseElement.fill(database);

    const usernameElement = await this.interactWithUsernameInput();
    await usernameElement.fill(username);

    const passwordElement = await this.interactWithPasswordInput();
    await passwordElement.fill(password);
  }

  async clickOnDatabaseModalConnect(): Promise<void> {
    const element = await this.interactWithDatabaseModalConnectBtn();
    await element.click();
  }

  async clickOnDatabaseModalCancel(): Promise<void> {
    const element = await this.interactWithDatabaseModalCancelBtn();
    await element.click();
  }

  // ==================== COMPLEX WORKFLOWS ====================

  /**
   * Connect to database using URL mode
   */
  async connectDatabaseViaUrl(
    type: "postgresql" | "mysql",
    connectionUrl: string
  ): Promise<void> {
    await this.clickOnConnectDatabase();
    await this.selectDatabaseType(type);
    await this.selectConnectionModeUrl();
    await this.enterConnectionUrl(connectionUrl);
    await this.clickOnDatabaseModalConnect();
  }

  /**
   * Connect to database using manual mode
   */
  async connectDatabaseManually(
    type: "postgresql" | "mysql",
    host: string,
    port: string,
    database: string,
    username: string,
    password: string
  ): Promise<void> {
    await this.clickOnConnectDatabase();
    await this.selectDatabaseType(type);
    await this.selectConnectionModeManual();
    await this.enterConnectionDetails(host, port, database, username, password);
    await this.clickOnDatabaseModalConnect();
  }

  /**
   * Delete a database
   */
  async deleteDatabase(databaseId: string): Promise<void> {
    await this.clickOnDatabaseSelector();
    await this.clickOnDeleteGraph(databaseId);
    await this.interactWithDeleteDatabaseModal();
    await this.clickOnDeleteModalConfirm();
  }

  async clickOnDeleteModalConfirm(): Promise<void> {
    const element = await this.interactWithDeleteModalConfirmBtn();
    await element.click();
  }

  async clickOnDeleteModalCancel(): Promise<void> {
    const element = await this.interactWithDeleteModalCancelBtn();
    await element.click();
  }

  // Token Management Functions
  async clickOnGenerateToken(): Promise<void> {
    const element = await this.interactWithGenerateTokenBtn();
    await element.click();
  }

  async copyNewToken(): Promise<void> {
    const element = await this.interactWithCopyTokenBtn();
    await element.click();
  }

  async getNewTokenValue(): Promise<string> {
    const element = await this.interactWithNewTokenInput();
    const value = await element.inputValue();
    return value;
  }

  async deleteToken(tokenId: string): Promise<void> {
    const element = await this.interactWithDeleteTokenBtn(tokenId);
    await element.click();

    // Confirm deletion in alert dialog
    await this.page.getByTestId("delete-token-confirm-action").click();
  }

  // ==================== VERIFICATION FUNCTIONS ====================

  async isLoggedIn(): Promise<boolean> {
    try {
      return await this.userMenuTrigger.isVisible();
    } catch {
      return false;
    }
  }

  async isDatabaseConnected(): Promise<boolean> {
    const badgeText = await this.databaseStatusBadge.textContent();
    return badgeText?.includes("Connected") || false;
  }

  async getSelectedDatabaseName(): Promise<string> {
    const badgeText = await this.databaseStatusBadge.textContent();
    return badgeText?.replace("Connected: ", "") || "";
  }

  async waitForQueryResults(): Promise<boolean> {
    try {
      // Wait for at least one query results message to appear (using count to avoid strict mode violation)
      await this.page.waitForFunction(
        () => {
          const messages = document.querySelectorAll('[data-testid="query-results-message"]');
          return messages.length > 0;
        },
        { timeout: 30000 }
      );
      return true;
    } catch {
      return false;
    }
  }

  async waitForSQLQuery(): Promise<boolean> {
    try {
      // Wait for at least one SQL query message to appear (using count to avoid strict mode violation)
      await this.page.waitForFunction(
        () => {
          const messages = document.querySelectorAll('[data-testid="sql-query-message"]');
          return messages.length > 0;
        },
        { timeout: 30000 }
      );
      return true;
    } catch {
      return false;
    }
  }

  async waitForAIResponse(): Promise<boolean> {
    try {
      // Wait for at least one AI message to appear (using count to avoid strict mode violation)
      await this.page.waitForFunction(
        () => {
          const messages = document.querySelectorAll('[data-testid="ai-message"]');
          return messages.length > 0;
        },
        { timeout: 30000 }
      );
      return true;
    } catch {
      return false;
    }
  }

  async isDatabaseInList(databaseId: string): Promise<boolean> {
    const dbOption = this.getDatabaseOption(databaseId);
    try {
      return await dbOption.isVisible();
    } catch {
      return false;
    }
  }

  async waitForDatabaseConnection(timeoutMs: number = 30000): Promise<boolean> {
    try {
      await this.page.waitForFunction(
        () => {
          const badge = document.querySelector('[data-testid="database-status-badge"]');
          return badge?.textContent?.includes('Connected') || false;
        },
        { timeout: timeoutMs }
      );
      return true;
    } catch {
      return false;
    }
  }

  async getDatabaseStatusBadgeText(): Promise<string> {
    try {
      const badge = await this.databaseStatusBadge;
      return await badge.textContent() || '';
    } catch {
      return '';
    }
  }

  async wait(milliseconds: number): Promise<void> {
    await this.page.waitForTimeout(milliseconds);
  }

  // ==================== CHAT-SPECIFIC VERIFICATION METHODS ====================

  /**
   * Check if query textarea is disabled
   */
  async isQueryTextareaDisabled(): Promise<boolean> {
    try {
      return await this.queryTextarea.isDisabled();
    } catch {
      return false;
    }
  }

  /**
   * Check if send query button is disabled
   */
  async isSendQueryButtonDisabled(): Promise<boolean> {
    try {
      return await this.sendQueryBtn.isDisabled();
    } catch {
      return false;
    }
  }

  /**
   * Check if SQL query message is visible (without waiting)
   */
  async isSQLQueryMessageVisible(): Promise<boolean> {
    try {
      const count = await this.sqlQueryMessage.count();
      return count > 0;
    } catch {
      return false;
    }
  }

  /**
   * Check if query results message is visible (without waiting)
   */
  async isQueryResultsMessageVisible(): Promise<boolean> {
    try {
      const count = await this.queryResultsMessage.count();
      return count > 0;
    } catch {
      return false;
    }
  }

  /**
   * Check if AI message is visible (without waiting)
   */
  async isAIMessageVisible(): Promise<boolean> {
    try {
      const count = await this.aiMessage.count();
      return count > 0;
    } catch {
      return false;
    }
  }

  /**
   * Get the number of rows in the results table
   */
  async getResultsTableRowCount(): Promise<number> {
    try {
      const table = await this.interactWithResultsTable();
      const tbody = table.locator('tbody');
      const rows = await tbody.locator('tr').count();
      return rows;
    } catch {
      return 0;
    }
  }

  /**
   * Verify SQL query message contains specific text
   */
  async verifySQLQueryContains(expectedText: string): Promise<boolean> {
    try {
      const sqlMessage = await this.interactWithSqlQueryMessage();
      const content = await sqlMessage.textContent();
      return content?.includes(expectedText) || false;
    } catch {
      return false;
    }
  }

  /**
   * Get text content of the last AI message
   */
  async getLastAIMessageText(): Promise<string> {
    try {
      const aiMessages = await this.aiMessage.all();
      if (aiMessages.length === 0) return '';
      const lastMessage = aiMessages[aiMessages.length - 1];
      return await lastMessage.textContent() || '';
    } catch {
      return '';
    }
  }

  /**
   * Get count of all messages in chat container
   * Useful for verifying message sequence
   */
  async getMessageCount(): Promise<number> {
    try {
      // Count all message types using their specific locators
      const userCount = await this.userMessage.count();
      const aiCount = await this.aiMessage.count();
      const sqlCount = await this.sqlQueryMessage.count();
      const resultsCount = await this.queryResultsMessage.count();

      return userCount + aiCount + sqlCount + resultsCount;
    } catch {
      return 0;
    }
  }

  async getAIMessageCount(): Promise<number> {
    try {
      return await this.aiMessage.count();
    } catch {
      return 0;
    }
  }

  /**
   * Wait for AI message to appear (for off-topic/follow-up responses)
   * Uses longer timeout than existing methods since AI responses can be slow
   */
  async waitForAIMessage(timeoutMs: number = 30000): Promise<boolean> {
    return await waitForElementToBeVisible(this.aiMessage, 1000, timeoutMs / 1000);
  }

  /**
   * Wait for the processing indicator to disappear
   * This indicates the query has finished processing
   */
  async waitForProcessingToComplete(timeoutMs: number = 50000): Promise<boolean> {
    try {
      // Wait a brief moment for the indicator to appear
      await this.page.waitForTimeout(500);

      // Check if the indicator is visible
      const isVisible = await this.processingQueryIndicator.isVisible().catch(() => false);

      if (!isVisible) {
        // If not visible, processing might have already completed or not started
        return true;
      }

      await this.processingQueryIndicator.waitFor({ state: 'hidden', timeout: timeoutMs });
      return true;
    } catch (error) {
      console.error('Error waiting for processing to complete:', error);
      return false;
    }
  }

  /**
   * Wait for complete query response (SQL + Results + AI response)
   * This is the full flow for valid database queries
   */
  async waitForCompleteQueryResponse(): Promise<boolean> {
    try {
      // Wait for all three components in sequence (each has 30s timeout)
      const sqlVisible = await this.waitForSQLQuery();
      if (!sqlVisible) return false;

      const resultsVisible = await this.waitForQueryResults();
      if (!resultsVisible) return false;

      const aiVisible = await this.waitForAIResponse();
      return aiVisible;
    } catch {
      return false;
    }
  }

  // ==================== TOAST VERIFICATION METHODS ====================

  /**
   * Check if toast notification is visible
   */
  async isToastVisible(): Promise<boolean> {
    try {
      return await this.toastNotification.isVisible();
    } catch {
      return false;
    }
  }

  /**
   * Wait for toast to appear
   */
  async waitForToast(timeoutMs: number = 5000): Promise<boolean> {
    return await waitForElementToBeVisible(this.toastNotification, 1000, timeoutMs / 1000);
  }

  /**
   * Get toast title text
   */
  async getToastTitle(): Promise<string> {
    try {
      return await this.toastTitle.textContent() || '';
    } catch {
      return '';
    }
  }

  /**
   * Get toast description text
   */
  async getToastDescription(): Promise<string> {
    try {
      return await this.toastDescription.textContent() || '';
    } catch {
      return '';
    }
  }

  /**
   * Verify toast contains expected title
   */
  async verifyToastTitle(expectedTitle: string): Promise<boolean> {
    try {
      const title = await this.getToastTitle();
      return title.includes(expectedTitle);
    } catch {
      return false;
    }
  }

  /**
   * Verify toast contains expected description
   */
  async verifyToastDescription(expectedDescription: string): Promise<boolean> {
    try {
      const description = await this.getToastDescription();
      return description.includes(expectedDescription);
    } catch {
      return false;
    }
  }

  // ==================== DATABASE CONNECTION HELPER ====================

  /**
   * Ensure database is connected
   * Checks if database exists, if not connects to test database
   * Returns true if connection was needed and successful, false if already connected
   */
  async ensureDatabaseConnected(apiCall: ApiCalls): Promise<boolean> {
    try {
      // Check if any databases exist (returns string[] of graph IDs)
      const graphs = await apiCall.getGraphs();

      // If we have graphs, database is already connected
      if (graphs && graphs.length > 0) {
        return false;
      }
    } catch (error) {
      console.log('Error checking existing graphs, will attempt to connect:', error);
    }

    // No database exists, connect to test database
    const { postgres: postgresUrl } = getTestDatabases();
    const response = await apiCall.connectDatabase(postgresUrl);
    await apiCall.parseStreamingResponse(response);

    // Refresh the page so the frontend can fetch the updated database list
    await this.page.reload();

    return true;
  }
}
