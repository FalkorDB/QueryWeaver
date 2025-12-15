import { APIRequestContext } from "@playwright/test";

export default class ApiCalls {
  /**
   * Get health check status
   */
  async healthCheck(request: APIRequestContext, baseURL: string): Promise<boolean> {
    try {
      const response = await request.get(`${baseURL}/`);
      return response.ok();
    } catch {
      return false;
    }
  }

  /**
   * Get graphs list (requires authentication)
   */
  async getGraphs(request: APIRequestContext, baseURL: string) {
    const response = await request.get(`${baseURL}/graphs`);
    return response;
  }

  /**
   * Test authentication endpoints
   */
  async testAuthEndpoint(
    request: APIRequestContext,
    baseURL: string,
    provider: string
  ) {
    const response = await request.get(`${baseURL}/login/${provider}`, {
      maxRedirects: 0,
    });
    return response;
  }

  /**
   * Upload a file
   */
  async uploadFile(
    request: APIRequestContext,
    baseURL: string,
    filePath: string
  ) {
    const response = await request.post(`${baseURL}/upload`, {
      multipart: {
        file: filePath,
      },
    });
    return response;
  }
}
