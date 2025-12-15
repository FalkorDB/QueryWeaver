import { chromium, Browser, BrowserContext, Page } from 'playwright';
import BasePage from './basePage';

export default class BrowserWrapper {
  private browser: Browser | null = null;
  private context: BrowserContext | null = null;
  private page: Page | null = null;

  async createNewPage<T extends BasePage>(
    PageClass: new (page: Page) => T,
    url?: string
  ) {
    if (!this.browser) {
      this.browser = await chromium.launch();
    }
    if (!this.context) {
      this.context = await this.browser.newContext();
    }
    if (!this.page) {
      this.page = await this.context.newPage();
    }
    if (url) {
      await this.navigateTo(url);
    }

    const pageInstance = new PageClass(this.page);
    return pageInstance;
  }

  getContext(): BrowserContext | null {
    return this.context;
  }

  async getPage() {
    if (!this.page) {
      throw new Error('Browser is not launched yet!');
    }
    return this.page;
  }

  async setPageToFullScreen() {
    if (!this.page) {
      throw new Error('Browser is not launched yet!');
    }
    await this.page.setViewportSize({ width: 1920, height: 1080 });
  }

  async navigateTo(url: string) {
    if (!this.page) {
      throw new Error('Browser is not launched yet!');
    }
    await this.page.goto(url);
    await this.page.waitForLoadState('networkidle');
  }

  async closePage() {
    if (this.page) {
      await this.page.close();
      this.page = null;
    }
  }

  async closeBrowser() {
    await this.closePage();
    if (this.browser) {
      await this.browser.close();
    }
  }
}
