import { chromium, Browser, BrowserContext, Page, firefox } from 'playwright';
import { test } from '@playwright/test';
import BasePage from './basePage';

async function launchBrowser(projectName: string): Promise<Browser> {
    if (projectName.toLowerCase().includes('firefox')) {
        return firefox.launch();
    }

    return chromium.launch();
}

export default class BrowserWrapper {

    private browser: Browser | null = null;

    private context: BrowserContext | null = null;

    private page: Page | null = null;

    async createNewPage<T extends BasePage>(
        PageClass: new (page: Page) => T,
        url?: string,
        storageStatePath?: string
    ) {
        if (!this.browser) {
            const projectName = test.info().project.name;
            this.browser = await launchBrowser(projectName);
        }

        // If storageStatePath is explicitly provided and context already exists,
        // we need to close the existing context and create a new one with the new auth
        if (storageStatePath && this.context) {
            await this.closeContext();
        }

        if (!this.context) {
            const projectName = test.info().project.name;
            const isFirefox = projectName.toLowerCase().includes('firefox');

            // Firefox doesn't support clipboard-read/write permissions
            const contextOptions: any = isFirefox ? {} : { permissions: ['clipboard-read', 'clipboard-write'] };

            // Add storage state if provided
            if (storageStatePath) {
                contextOptions.storageState = storageStatePath;
            }

            this.context = await this.browser.newContext(contextOptions);
        }
        if (!this.page) {
            this.page = await this.context.newPage();
        }
        if (url) {
            await this.navigateTo(url)
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

    async closeContext() {
        await this.closePage();
        
        if (this.context) {
            await this.context.close();
            this.context = null;
        }
    }

    async closeBrowser() {
        await this.closeContext();
        
        if (this.browser) {
            await this.browser.close();
        }
    }

}