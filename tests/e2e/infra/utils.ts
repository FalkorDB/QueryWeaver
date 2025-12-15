import { Page, Locator } from "@playwright/test";

/**
 * Wait for an element to be visible on the page
 */
export async function waitForElementToBeVisible(
  page: Page,
  selector: string,
  timeout: number = 10000
): Promise<Locator> {
  const element = page.locator(selector);
  await element.waitFor({ state: "visible", timeout });
  return element;
}

/**
 * Poll for element content to match expected value
 */
export async function pollForElementContent(
  page: Page,
  selector: string,
  expectedContent: string,
  timeout: number = 10000
): Promise<boolean> {
  const endTime = Date.now() + timeout;
  while (Date.now() < endTime) {
    try {
      const element = page.locator(selector);
      const content = await element.textContent();
      if (content?.includes(expectedContent)) {
        return true;
      }
    } catch (error) {
      // Element not found yet, continue polling
    }
    await page.waitForTimeout(100);
  }
  return false;
}

/**
 * Wait for network to be idle
 */
export async function waitForNetworkIdle(page: Page, timeout: number = 10000) {
  await page.waitForLoadState("networkidle", { timeout });
}

/**
 * Take a screenshot with timestamp
 */
export async function takeScreenshot(page: Page, name: string) {
  const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
  await page.screenshot({
    path: `test-results/screenshots/${name}-${timestamp}.png`,
    fullPage: true,
  });
}
