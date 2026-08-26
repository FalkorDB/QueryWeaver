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

  private get settingsBtn(): Locator {
    return this.page.getByTestId("settings-button");
  }

  /** Public accessor: strict assertions need the raw toggle locator. */
  get sidebarToggle(): Locator {
    return this.sidebarToggleBtn;
  }

  /** Anchors inside the sidebar that go nowhere — see issue #239. */
  get sidebarDeadLinks(): Locator {
    return this.page.locator('aside a[href="#"], aside a:not([href])');
  }

  get schemaPanelResizeHandle(): Locator {
    return this.page.getByTestId("schema-panel-resize-handle");
  }

  /** Public accessor for the schema panel, for strict web-first assertions. */
  get schemaPanelLocator(): Locator {
    return this.schemaPanel;
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

  private async interactWithSettingsBtn(): Promise<Locator> {
    const isVisible = await waitForElementToBeVisible(this.settingsBtn);
    if (!isVisible) throw new Error("Settings button is not visible!");
    return this.settingsBtn;
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

  async clickOnSettingsButton(): Promise<void> {
    const element = await this.interactWithSettingsBtn();
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

  async getSchemaPanelWidth(): Promise<number> {
    const box = await this.schemaPanel.boundingBox();
    if (!box) throw new Error("Schema panel is not rendered!");
    return box.width;
  }

  async getViewportWidth(): Promise<number> {
    return await this.page.evaluate(() => window.innerWidth);
  }

  /** Resizes the browser viewport, which re-derives the panel's width bounds. */
  async setViewportWidth(width: number, height = 1080): Promise<void> {
    await this.page.setViewportSize({ width, height });
  }

  /**
   * Presses and releases the handle without moving the pointer. A bare click is
   * how a keyboard user focuses the separator, so it must not count as a
   * user-chosen width.
   */
  async clickSchemaPanelResizeHandle(): Promise<void> {
    const box = await this.schemaPanelResizeHandle.boundingBox();
    if (!box) throw new Error("Schema panel resize handle is not rendered!");

    await this.page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await this.page.mouse.down();
    await this.page.mouse.up();
  }

  /**
   * Drags the schema panel's resize handle so the panel's right edge lands on
   * `targetX`. Overshooting the min/max is intentional in tests: the panel is
   * expected to clamp rather than freeze mid-drag.
   */
  async dragSchemaPanelResizeHandleTo(targetX: number): Promise<void> {
    const box = await this.schemaPanelResizeHandle.boundingBox();
    if (!box) throw new Error("Schema panel resize handle is not rendered!");

    const startY = box.y + box.height / 2;
    await this.page.mouse.move(box.x + box.width / 2, startY);
    await this.page.mouse.down();
    await this.page.mouse.move(targetX, startY, { steps: 10 });
    await this.page.mouse.up();
  }

  /**
   * Focuses the resize handle and presses `key` `times` times. The handle is
   * a `role="separator"` with `tabIndex={0}`, so keyboard resizing is the only
   * way to size the panel without a pointer.
   */
  async pressSchemaPanelResizeKey(key: string, times = 1): Promise<void> {
    await this.schemaPanelResizeHandle.focus();
    for (let i = 0; i < times; i += 1) {
      await this.schemaPanelResizeHandle.press(key);
    }
  }

  /** Reads `aria-valuenow` off the handle, which must track the real width. */
  async getSchemaPanelAriaValueNow(): Promise<number> {
    const value = await this.schemaPanelResizeHandle.getAttribute('aria-valuenow');
    if (value === null) throw new Error('Schema panel resize handle has no aria-valuenow!');
    return Number(value);
  }
}
