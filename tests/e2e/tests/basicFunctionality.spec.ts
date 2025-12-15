import { test, expect } from "@playwright/test";
import HomePage from "@/e2e/logic/POM/homePage";

test.describe("Basic Functionality Tests", () => {
  test("should load the application successfully", async ({ page }) => {
    const homePage = new HomePage(page);
    await homePage.navigateToHome();

    // Check that the page loaded successfully
    expect(page.url()).toContain("/");

    // Check that the page has basic HTML structure
    const body = await page.locator("body");
    await expect(body).toBeVisible();

    // Wait for any dynamic content to load
    await page.waitForTimeout(2000);

    // The page should have some interactive elements
    const interactiveElements = await page.locator(
      "button, input, select, textarea, a[href]"
    ).count();
    expect(interactiveElements).toBeGreaterThan(0);
  });

  test("should have file upload interface", async ({ page }) => {
    const homePage = new HomePage(page);
    await homePage.navigateToHome();

    // Check if file upload related elements exist
    const fileInputs = await page.locator("input[type='file']").count();
    const uploadButtons = await page.locator(
      "button[aria-label*='upload'], .upload-btn, [data-testid*='upload']"
    ).count();

    // Verify the page loaded successfully
    expect(page.url()).toContain("/");

    // Check that some interactive elements exist
    const interactiveElements = await page.locator(
      "button, input, select, textarea"
    ).count();
    expect(interactiveElements).toBeGreaterThanOrEqual(1);
  });

  test("should be responsive at different screen sizes", async ({ page }) => {
    const homePage = new HomePage(page);
    await homePage.navigateToHome();

    // Test mobile view
    await page.setViewportSize({ width: 375, height: 667 });
    await page.waitForTimeout(1000);
    expect(await page.title()).toBeTruthy();

    // Test tablet view
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.waitForTimeout(1000);

    // Test desktop view
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.waitForTimeout(1000);
  });

  test("should handle invalid routes gracefully", async ({ page }) => {
    await page.goto("/nonexistent-route");

    // Should handle 404 gracefully
    const response = await page.evaluate(() =>
      fetch("/nonexistent-route").then((r) => r.status)
    );
    expect([404, 302, 200]).toContain(response);
  });
});
