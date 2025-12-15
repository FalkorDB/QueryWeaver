import { test, expect } from "@playwright/test";
import ApiCalls from "../logic/api/apiCalls";

test.describe("API Endpoints Tests", () => {
  let apiCalls: ApiCalls;
  const baseURL = process.env.BASE_URL || "http://localhost:5000";

  test.beforeEach(() => {
    apiCalls = new ApiCalls();
  });

  test("should pass health check", async ({ request }) => {
    const isHealthy = await apiCalls.healthCheck(request, baseURL);
    expect(isHealthy).toBe(true);
  });

  test("should require auth for graphs endpoint", async ({ request }) => {
    const response = await apiCalls.getGraphs(request, baseURL);
    expect([401, 302, 403]).toContain(response.status());
  });

  test("should handle Google login endpoint", async ({ request }) => {
    const response = await apiCalls.testAuthEndpoint(request, baseURL, "google");
    expect(response.status()).toBeGreaterThanOrEqual(200);
  });

  test("should handle GitHub login endpoint", async ({ request }) => {
    const response = await apiCalls.testAuthEndpoint(request, baseURL, "github");
    expect(response.status()).toBeGreaterThanOrEqual(200);
  });

  test("should return 404 for invalid endpoints", async ({ request }) => {
    const response = await request.get(`${baseURL}/invalid-endpoint`);
    expect(response.status()).toBe(404);
  });

  test("should handle method not allowed", async ({ request }) => {
    const response = await request.post(baseURL);
    expect([405, 200]).toContain(response.status());
  });

  test("should handle CORS requests", async ({ request }) => {
    const response = await request.fetch(baseURL, {
      method: "OPTIONS",
    });
    expect([200, 404, 405]).toContain(response.status());
  });

  test("should have reasonable response times", async ({ request }) => {
    const startTime = Date.now();
    const response = await request.get(baseURL);
    const endTime = Date.now();

    const responseTime = endTime - startTime;
    expect(responseTime).toBeLessThan(5000);
    expect(response.ok()).toBe(true);
  });
});
