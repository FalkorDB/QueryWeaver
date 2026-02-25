/* eslint-disable @typescript-eslint/no-explicit-any */

import { APIRequestContext, APIResponse } from "@playwright/test";
import { getRequest, postRequest, deleteRequest } from "../../infra/api/apiRequests";
import { getBaseUrl } from "../../config/urls";
import type {
  AuthStatusResponse,
  LoginResponse,
  SignupResponse,
  LogoutResponse,
  GraphsListResponse,
  GraphDataResponse,
  GraphUploadResponse,
  DeleteGraphResponse,
  StreamMessage,
  TokenListResponse,
  GenerateTokenResponse,
  DeleteTokenResponse,
} from "./apiResponses";

// ==================== AUTHENTICATION ENDPOINTS ====================
export default class ApiCalls {
  /**
   * Check authentication status
   * GET /auth-status
   */
  async getAuthStatus(
    requestContext?: APIRequestContext
  ): Promise<AuthStatusResponse> {
    try {
      const baseUrl = getBaseUrl();
      const response = await getRequest(
        `${baseUrl}/auth-status`,
        undefined,
        undefined,
        requestContext
      );
      return await response.json();
    } catch (error) {
      throw new Error(
        `Failed to get auth status. \n Error: ${(error as Error).message}`
      );
    }
  }

  /**
   * Login with email and password
   * POST /login/email
   */
  async loginWithEmail(
    email: string,
    password: string,
    requestContext?: APIRequestContext
  ): Promise<LoginResponse> {
    try {
      const baseUrl = getBaseUrl();
      const response = await postRequest(
        `${baseUrl}/login/email`,
        { email, password },
        requestContext
      );

      const data = await response.json();
      return data;
    } catch (error) {
      throw new Error(
        `Failed to login with email. \n Error: ${(error as Error).message}`
      );
    }
  }

  /**
   * Signup with email and password
   * POST /signup/email
   */
  async signupWithEmail(
    firstName: string,
    lastName: string,
    email: string,
    password: string,
    requestContext?: APIRequestContext
  ): Promise<SignupResponse> {
    try {
      const baseUrl = getBaseUrl();
      const response = await postRequest(
        `${baseUrl}/signup/email`,
        { firstName, lastName, email, password },
        requestContext
      );
      return await response.json();
    } catch (error) {
      throw new Error(
        `Failed to signup with email. \n Error: ${(error as Error).message}`
      );
    }
  }

  /**
   * Logout
   * POST /logout
   */
  async logout(
    requestContext?: APIRequestContext
  ): Promise<LogoutResponse> {
    try {
      const baseUrl = getBaseUrl();
      const response = await postRequest(
        `${baseUrl}/logout`,
        undefined,
        requestContext
      );
      return await response.json();
    } catch (error) {
      throw new Error(
        `Failed to logout. \n Error: ${(error as Error).message}`
      );
    }
  }

  /**
   * Get Google OAuth login URL
   * GET /login/google
   */
  async getGoogleLoginUrl(): Promise<string> {
    const baseUrl = getBaseUrl();
    return `${baseUrl}/login/google`;
  }

  /**
   * Get GitHub OAuth login URL
   * GET /login/github
   */
  async getGithubLoginUrl(): Promise<string> {
    const baseUrl = getBaseUrl();
    return `${baseUrl}/login/github`;
  }

  // ==================== GRAPH/DATABASE MANAGEMENT ENDPOINTS ====================

  /**
   * Get list of all graphs for authenticated user
   * GET /graphs
   */
  async getGraphs(): Promise<GraphsListResponse> {
    try {
      const baseUrl = getBaseUrl();
      const response = await getRequest(
        `${baseUrl}/graphs`,
        undefined,
        undefined
      );
      return await response.json();
    } catch (error) {
      throw new Error(
        `Failed to get graphs. \n Error: ${(error as Error).message}`
      );
    }
  }

  /**
   * Get graph schema data (nodes and links)
   * GET /graphs/{graph_id}/data
   */
  async getGraphData(
    graphId: string
  ): Promise<GraphDataResponse> {
    try {
      const baseUrl = getBaseUrl();
      const response = await getRequest(
        `${baseUrl}/graphs/${graphId}/data`,
        undefined,
        undefined
      );
      return await response.json();
    } catch (error) {
      throw new Error(
        `Failed to get graph data for ${graphId}. \n Error: ${(error as Error).message}`
      );
    }
  }

  /**
   * Upload graph data file (JSON, CSV, XML)
   * POST /graphs
   */
  async uploadGraph(
    filePath: string,
    database?: string,
    description?: string
  ): Promise<GraphUploadResponse> {
    try {
      const baseUrl = getBaseUrl();
      const formData: Record<string, string> = {
        file: filePath,
      };

      if (database) formData.database = database;
      if (description) formData.description = description;

      const response = await postRequest(
        `${baseUrl}/graphs`,
        formData,
        undefined,
        { "Content-Type": "multipart/form-data" }
      );
      return await response.json();
    } catch (error) {
      throw new Error(
        `Failed to upload graph. \n Error: ${(error as Error).message}`
      );
    }
  }

  /**
   * Query a database with natural language (streaming)
   * POST /graphs/{graph_id}
   * Returns streaming SSE response
   */
  async queryGraph(
    graphId: string,
    chat: string[],
    result?: string[] | null,
    instructions?: string
  ): Promise<APIResponse> {
    try {
      const baseUrl = getBaseUrl();
      const body = {
        chat,
        result: result || null,
        instructions: instructions || undefined,
      };

      const response = await postRequest(
        `${baseUrl}/graphs/${graphId}`,
        body,
        undefined,
        { "Content-Type": "application/json" }
      );

      return response;
    } catch (error) {
      throw new Error(
        `Failed to query graph ${graphId}. \n Error: ${(error as Error).message}`
      );
    }
  }

  /**
   * Parse streaming SSE response
   * Helper to parse streaming messages separated by |||FALKORDB_MESSAGE_BOUNDARY|||
   */
  async parseStreamingResponse(
    response: APIResponse
  ): Promise<StreamMessage[]> {
    try {
      const body = await response.text();
      const messages = body
        .split("|||FALKORDB_MESSAGE_BOUNDARY|||")
        .filter((msg) => msg.trim())
        .map((msg) => JSON.parse(msg.trim()));
      // Log error messages to help diagnose CI failures
      const errorMessages = messages.filter((m) => m.type === "error");
      if (errorMessages.length > 0) {
        console.log(
          `[parseStreamingResponse] HTTP status: ${response.status()}, error messages received:`,
          JSON.stringify(errorMessages)
        );
      }
      return messages;
    } catch (error) {
      throw new Error(
        `Failed to parse streaming response. \n Error: ${(error as Error).message}`
      );
    }
  }

  /**
   * Poll getGraphs() until the predicate is satisfied, or until timeout.
   * Returns the last observed graph list (for diagnostics even on timeout).
   * Can be used to wait for a graph to appear or to disappear.
   */
  async waitForGraphs(
    predicate: (graphs: GraphsListResponse) => boolean,
    timeoutMs: number = 30000,
    pollIntervalMs: number = 2000
  ): Promise<GraphsListResponse> {
    const deadline = Date.now() + timeoutMs;
    let lastGraphs: GraphsListResponse = [];
    while (Date.now() < deadline) {
      try {
        lastGraphs = await this.getGraphs();
        if (predicate(lastGraphs)) {
          return lastGraphs;
        }
      } catch (err) {
        console.log(
          `[waitForGraphs] getGraphs() error: ${(err as Error).message}`
        );
      }
      const remaining = deadline - Date.now();
      if (remaining <= 0) break;
      await new Promise((resolve) =>
        setTimeout(resolve, Math.min(pollIntervalMs, remaining))
      );
    }
    console.log(
      `[waitForGraphs] timed out after ${timeoutMs}ms. Last graphs: ${JSON.stringify(lastGraphs)}`
    );
    return lastGraphs;
  }

  /**
   * Connect to external database with retry on transient errors.
   * Retries up to `maxAttempts` times if the streaming response final message is not 'final_result'.
   */
  async connectDatabaseWithRetry(
    connectionUrl: string,
    maxAttempts: number = 3,
    retryDelayMs: number = 3000
  ): Promise<StreamMessage[]> {
    let lastMessages: StreamMessage[] = [];
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      try {
        const response = await this.connectDatabase(connectionUrl);
        const messages = await this.parseStreamingResponse(response);
        const finalMessage = messages[messages.length - 1];
        if (finalMessage && finalMessage.type === "final_result") {
          return messages;
        }
        console.log(
          `[connectDatabaseWithRetry] attempt ${attempt}/${maxAttempts} did not return final_result.`,
          `Last message: ${JSON.stringify(finalMessage)}`
        );
        lastMessages = messages;
      } catch (err) {
        console.error(
          `[connectDatabaseWithRetry] attempt ${attempt}/${maxAttempts} threw an error:`,
          (err as Error).message
        );
      }
      if (attempt < maxAttempts) {
        await new Promise((resolve) => setTimeout(resolve, retryDelayMs));
      }
    }
    console.log(
      `[connectDatabaseWithRetry] all ${maxAttempts} attempts exhausted. Last messages: ${JSON.stringify(lastMessages)}`
    );
    return lastMessages;
  }

  /**
   * Confirm destructive SQL operation
   * POST /graphs/{graph_id}/confirm
   */
  async confirmGraphOperation(
    graphId: string,
    sqlQuery: string,
    confirmation: string,
    chat: any[] = []
  ): Promise<APIResponse> {
    try {
      const baseUrl = getBaseUrl();
      const body = {
        sql_query: sqlQuery,
        confirmation,
        chat,
      };

      const response = await postRequest(
        `${baseUrl}/graphs/${graphId}/confirm`,
        body,
        undefined,
        { "Content-Type": "application/json" }
      );

      return response;
    } catch (error) {
      throw new Error(
        `Failed to confirm operation for graph ${graphId}. \n Error: ${(error as Error).message}`
      );
    }
  }

  /**
   * Refresh graph schema
   * POST /graphs/{graph_id}/refresh
   */
  async refreshGraphSchema(
    graphId: string
  ): Promise<APIResponse> {
    try {
      const baseUrl = getBaseUrl();
      const response = await postRequest(
        `${baseUrl}/graphs/${graphId}/refresh`,
        undefined,
        undefined,
        { "Content-Type": "application/json" }
      );

      return response;
    } catch (error) {
      throw new Error(
        `Failed to refresh schema for graph ${graphId}. \n Error: ${(error as Error).message}`
      );
    }
  }

  /**
   * Delete a graph
   * DELETE /graphs/{graph_id}
   */
  async deleteGraph(
    graphId: string,
    requestContext?: APIRequestContext
  ): Promise<DeleteGraphResponse> {
    try {
      const baseUrl = getBaseUrl();
      const response = await deleteRequest(
        `${baseUrl}/graphs/${graphId}`,
        undefined,
        undefined,
        requestContext
      );
      return await response.json();
    } catch (error) {
      throw new Error(
        `Failed to delete graph ${graphId}. \n Error: ${(error as Error).message}`
      );
    }
  }

  // ==================== DATABASE CONNECTION ENDPOINTS ====================

  /**
   * Connect to external database using connection URL
   * POST /database
   * Supports PostgreSQL and MySQL
   */
  async connectDatabase(
    connectionUrl: string
  ): Promise<APIResponse> {
    try {
      const baseUrl = getBaseUrl();
      const body = {
        url: connectionUrl,
      };

      const response = await postRequest(
        `${baseUrl}/database`,
        body,
        undefined,
        { "Content-Type": "application/json" }
      );

      return response;
    } catch (error) {
      throw new Error(
        `Failed to connect to database. \n Error: ${(error as Error).message}`
      );
    }
  }

  // ==================== TOKEN MANAGEMENT ENDPOINTS ====================

  /**
   * Generate a new API token
   * POST /tokens/generate
   */
  async generateToken(): Promise<GenerateTokenResponse> {
    try {
      const baseUrl = getBaseUrl();
      const response = await postRequest(
        `${baseUrl}/tokens/generate`,
        undefined
      );
      return await response.json();
    } catch (error) {
      throw new Error(
        `Failed to generate token. \n Error: ${(error as Error).message}`
      );
    }
  }

  /**
   * List all tokens for authenticated user
   * GET /tokens/list
   */
  async listTokens(): Promise<TokenListResponse> {
    try {
      const baseUrl = getBaseUrl();
      const response = await getRequest(
        `${baseUrl}/tokens/list`,
        undefined,
        undefined
      );
      return await response.json();
    } catch (error) {
      throw new Error(
        `Failed to list tokens. \n Error: ${(error as Error).message}`
      );
    }
  }

  /**
   * Delete a specific token
   * DELETE /tokens/{token_id}
   */
  async deleteToken(
    tokenId: string,
    requestContext?: APIRequestContext
  ): Promise<DeleteTokenResponse> {
    try {
      const baseUrl = getBaseUrl();
      const response = await deleteRequest(
        `${baseUrl}/tokens/${tokenId}`,
        undefined,
        undefined,
        requestContext
      );
      return await response.json();
    } catch (error) {
      throw new Error(
        `Failed to delete token ${tokenId}. \n Error: ${(error as Error).message}`
      );
    }
  }
}
