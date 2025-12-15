import { Page, Locator } from "@playwright/test";
import BasePage from "../../infra/ui/basePage";

export default class HomePage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  // Selectors
  get loginButton(): Locator {
    return this.page.locator("a[href*='login']");
  }

  get chatContainer(): Locator {
    return this.page.locator(".chat-container");
  }

  get messageInput(): Locator {
    return this.page.locator("input[type='text'], textarea").first();
  }

  get sendButton(): Locator {
    return this.page.locator("button[type='submit']");
  }

  get graphSelector(): Locator {
    return this.page.locator("select[name='graph']");
  }

  get fileUpload(): Locator {
    return this.page.locator("#schema-upload");
  }

  get loadingIndicator(): Locator {
    return this.page.locator(".loading");
  }

  // Actions
  async navigateToHome() {
    await this.page.goto("/");
    await this.page.waitForLoadState("domcontentloaded", { timeout: 30000 });
  }

  async isAuthenticated(): Promise<boolean> {
    try {
      await this.loginButton.waitFor({ state: "visible", timeout: 2000 });
      return false;
    } catch {
      return true;
    }
  }

  async clickLogin() {
    await this.loginButton.waitFor({ state: "visible", timeout: 5000 });
    await this.loginButton.click();
  }

  async hasChatInterface(): Promise<boolean> {
    try {
      await this.chatContainer.waitFor({ state: "visible", timeout: 5000 });
      return true;
    } catch {
      return false;
    }
  }

  async typeMessage(message: string) {
    await this.messageInput.fill(message);
  }

  async sendMessage() {
    await this.sendButton.click();
  }

  async uploadFile(filePath: string) {
    await this.fileUpload.setInputFiles(filePath);
  }

  async selectGraph(graphName: string) {
    await this.graphSelector.selectOption(graphName);
  }

  async waitForResponse(timeout: number = 10000) {
    try {
      await this.loadingIndicator.waitFor({ state: "hidden", timeout });
    } catch {
      // Loading indicator might not be present
    }
  }

  async getChatMessages() {
    return await this.page.locator(".message").all();
  }
}
