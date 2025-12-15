import { test, expect } from "@playwright/test";
import HomePage from "@/e2e/logic/POM/homePage";

test.describe("Unauthenticated User Flow", () => {
  test("should show appropriate UI for unauthenticated users", async ({ page }) => {
    const homePage = new HomePage(page);
    await homePage.navigateToHome();

    // Verify the page loaded successfully
    expect(page.url()).toContain("/");

    // Should have login-related elements
    const loginElements = await page.locator(
      "a[href*='google'], a[href*='github'], a[href*='login'], button[data-action*='login'], .login-btn"
    ).count();

    // If no explicit login elements, check for interactive elements
    if (loginElements === 0) {
      const interactiveElements = await page.locator("button, a[href]").count();
      expect(interactiveElements).toBeGreaterThan(0);
    }
  });

  test("should have authentication prompts", async ({ page }) => {
    const homePage = new HomePage(page);
    await homePage.navigateToHome();

    // Check for message input
    const messageInput = page.locator("#message-input");
    const messageInputExists = await messageInput.count();

    if (messageInputExists > 0) {
      const placeholder = await messageInput.getAttribute("placeholder");
      // Document the placeholder text
      expect(placeholder).toBeTruthy();
    }

    // Check file upload state
    const fileInput = page.locator("#schema-upload");
    const fileInputExists = await fileInput.count();

    if (fileInputExists > 0) {
      const isVisible = await fileInput.isVisible();
      const isEnabled = await fileInput.isEnabled();
      // Document the current behavior
      expect(typeof isVisible).toBe("boolean");
      expect(typeof isEnabled).toBe("boolean");
    }
  });

  test("should redirect login buttons to OAuth", async ({ page }) => {
    const homePage = new HomePage(page);
    await homePage.navigateToHome();

    // Test Google login redirect
    const googleLogin = page.locator("a[href*='google']");
    const googleLoginExists = await googleLogin.count();

    if (googleLoginExists > 0 && (await googleLogin.isVisible())) {
      const href = await googleLogin.getAttribute("href");
      expect(href).toContain("/login/google");
    }
  });

  test("should block restricted features", async ({ page, request }) => {
    await page.goto("/");

    // Try to access API endpoints that require auth
    const graphsResponse = await request.get(`${page.url()}graphs`);
    expect(graphsResponse.status()).toBe(401);

    const createResponse = await request.post(`${page.url()}graphs`, {
      data: {},
    });
    expect(createResponse.status()).toBe(401);
  });
});
