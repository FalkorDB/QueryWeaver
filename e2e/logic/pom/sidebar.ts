import { Locator } from "@playwright/test";
import { waitForElementToBeVisible } from "../../infra/utils";
import { HomePage } from "./homePage";

/**
 * Sidebar class extends HomePage to have access to all page elements
 * while providing sidebar-specific locators and methods.
 *
 * Additionally, since this extends HomePage, you can access:
 * - All database-related methods (clickOnConnectDatabase, etc.)
 * - All chat-related methods
 * - All other page elements
 */
export class Sidebar extends HomePage {
  // ==================== LAYER 1: SIDEBAR LOCATORS ====================

  private get sidebarToggleBtn(): Locator {
    return this.page.getByTestId("sidebar-toggle");
  }

  private get themeToggleBtn(): Locator {
    return this.page.getByTestId("theme-toggle");
  }

  private get schemaBtn(): Locator {
    return this.page.getByTestId("schema-button");
  }

  private get docsLink(): Locator {
    return this.page.getByTestId("documentation-link");
  }

  private get supportBtn(): Locator {
    return this.page.getByTestId("support-link");
  }

  private get schemaPanel(): Locator {
    return this.page.getByTestId("schema-panel");
  }

  // ==================== LAYER 2: INTERACT WITH VISIBLE ====================

  private async interactWithSidebarToggleBtn(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.sidebarToggleBtn);
    if (!isVisible) throw new Error("Sidebar toggle is not visible!");
    return this.sidebarToggleBtn;
  }

  private async interactWithThemeToggleBtn(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.themeToggleBtn);
    if (!isVisible) throw new Error("Theme toggle is not visible!");
    return this.themeToggleBtn;
  }

  private async interactWithSchemaBtn(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.schemaBtn);
    if (!isVisible) throw new Error("Schema button is not visible!");
    return this.schemaBtn;
  }

  private async interactWithDocsLink(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.docsLink);
    if (!isVisible) throw new Error("Documentation link is not visible!");
    return this.docsLink;
  }

  private async interactWithSupportBtn(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.supportBtn);
    if (!isVisible) throw new Error("Support link is not visible!");
    return this.supportBtn;
  }

  // ==================== LAYER 3: HIGH-LEVEL ACTIONS ====================

  async clickOnSidebarToggle(): Promise<void> {
    const element = await this.interactWithSidebarToggleBtn();
    await element.click();
  }

  async clickOnThemeToggle(): Promise<void> {
    const element = await this.interactWithThemeToggleBtn();
    await element.click();
  }

  async clickOnSchemaButton(): Promise<void> {
    const element = await this.interactWithSchemaBtn();
    await element.click();
  }

  async clickOnDocumentationLink(): Promise<void> {
    const element = await this.interactWithDocsLink();
    await element.click();
  }

  async clickOnSupportLink(): Promise<void> {
    const element = await this.interactWithSupportBtn();
    await element.click();
  }

  // ==================== VERIFICATION METHODS ====================

  async isSidebarToggleVisible(): Promise<boolean> {
    return await waitForElementToBeVisible(this.sidebarToggleBtn);
  }

  async isThemeToggleVisible(): Promise<boolean> {
    return await waitForElementToBeVisible(this.themeToggleBtn);
  }

  async isSchemaButtonVisible(): Promise<boolean> {
    return await waitForElementToBeVisible(this.schemaBtn);
  }

  async isDocumentationLinkVisible(): Promise<boolean> {
    return await waitForElementToBeVisible(this.docsLink);
  }

  async isSupportLinkVisible(): Promise<boolean> {
    return await waitForElementToBeVisible(this.supportBtn);
  }

  async getDocumentationLinkHref(): Promise<string | null> {
    const element = await this.interactWithDocsLink();
    return await element.getAttribute('href');
  }

  async getSupportLinkHref(): Promise<string | null> {
    const element = await this.interactWithSupportBtn();
    return await element.getAttribute('href');
  }

  async getCurrentTheme(): Promise<string | null> {
    return await this.page.evaluate(() => {
      return document.documentElement.getAttribute('data-theme');
    });
  }

  async isSchemaPanelVisible(): Promise<boolean> {
    return await waitForElementToBeVisible(this.schemaPanel);
  }
}
