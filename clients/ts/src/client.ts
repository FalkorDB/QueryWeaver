import { ChatData, ConfirmData, APIResponse, QueryWeaverClientOptions, APIError } from './types';

const MESSAGE_DELIMITER = '|||FALKORDB_MESSAGE_BOUNDARY|||';

/**
 * QueryWeaver HTTP API client.
 *
 * Simple wrapper around the REST API exposed by a running QueryWeaver server.
 * Supports API token authentication (Bearer) and session cookie usage.
 *
 * @example
 * ```typescript
 * // With API token authentication
 * const client = new QueryWeaverClient({
 *   baseUrl: 'http://localhost:5000',
 *   apiToken: 'your-api-token'
 * });
 *
 * // With session cookies (handled automatically by fetch)
 * const client = new QueryWeaverClient({
 *   baseUrl: 'http://localhost:5000'
 * });
 * ```
 */
export class QueryWeaverClient {
  private baseUrl: string;
  private apiToken?: string;
  private timeout: number;
  private defaultHeaders: Record<string, string>;

  /**
   * Create a new QueryWeaver client.
   *
   * @param options - Client configuration options
   * @param options.baseUrl - The base URL of the QueryWeaver server (default: 'http://localhost:5000')
   * @param options.apiToken - Optional API token for Bearer authentication
   * @param options.timeout - Request timeout in milliseconds (default: 30000)
   */
  constructor(options: QueryWeaverClientOptions = {}) {
    this.baseUrl = (options.baseUrl || 'http://localhost:5000').replace(/\/$/, '');
    this.apiToken = options.apiToken;
    this.timeout = options.timeout || 30000;

    this.defaultHeaders = {
      'Accept': 'application/json',
      'Content-Type': 'application/json',
    };

    if (this.apiToken) {
      this.defaultHeaders['Authorization'] = `Bearer ${this.apiToken}`;
    }
  }

  private url(path: string): string {
    return `${this.baseUrl}${path}`;
  }

  private async raiseForStatus(response: Response): Promise<void> {
    if (!response.ok) {
      let errorMessage: string;
      let responseData: unknown;

      try {
        responseData = await response.json();
        const data = responseData as Record<string, unknown>;
        errorMessage = (data.error as string) || (data.message as string) || `HTTP ${response.status}`;
      } catch {
        errorMessage = await response.text() || `HTTP ${response.status}`;
      }

      throw new APIError(errorMessage, response.status, responseData);
    }
  }

  /**
   * List available user schemas/databases.
   *
   * @returns A list of database/schema names.
   */
  async listSchemas(): Promise<string[]> {
    const response = await fetch(this.url('/graphs'), {
      method: 'GET',
      headers: this.defaultHeaders,
      signal: AbortSignal.timeout(this.timeout),
    });

    await this.raiseForStatus(response);
    return response.json();
  }

  /**
   * Get schema nodes/edges for a specific graph.
   */
  async getSchema(graphId: string): Promise<APIResponse> {
    const response = await fetch(this.url(`/graphs/${graphId}/data`), {
      method: 'GET',
      headers: this.defaultHeaders,
      signal: AbortSignal.timeout(this.timeout),
    });

    await this.raiseForStatus(response);
    return response.json();
  }

  /**
   * Delete a schema.
   */
  async deleteSchema(graphId: string): Promise<APIResponse> {
    const response = await fetch(this.url(`/graphs/${graphId}`), {
      method: 'DELETE',
      headers: this.defaultHeaders,
      signal: AbortSignal.timeout(this.timeout),
    });

    await this.raiseForStatus(response);
    return response.json();
  }

  /**
   * Refresh schema.
   */
  async refreshSchema(graphId: string): Promise<APIResponse> {
    const response = await fetch(this.url(`/graphs/${graphId}/refresh`), {
      method: 'POST',
      headers: this.defaultHeaders,
      signal: AbortSignal.timeout(this.timeout),
    });

    await this.raiseForStatus(response);
    return response.json();
  }

  /**
   * Connect to a database and return final result.
   */
  async connectDatabase(dbUrl: string): Promise<APIResponse> {
    const response = await fetch(this.url('/database'), {
      method: 'POST',
      headers: this.defaultHeaders,
      body: JSON.stringify({ url: dbUrl }),
      signal: AbortSignal.timeout(this.timeout),
    });

    await this.raiseForStatus(response);
    return this.consumeStreamingResponse(response);
  }

  /**
   * Run a natural language query and return final result.
   *
   * @param graphId - The database/schema ID to query
   * @param chatData - The chat data containing the query messages
   * @param autoConfirm - If true, automatically confirm destructive operations.
   *                      If false (default), returns confirmation request for user approval.
   * @returns The query result or confirmation request
   */
  async query(graphId: string, chatData: ChatData, autoConfirm: boolean = false): Promise<APIResponse> {
    const response = await fetch(this.url(`/graphs/${graphId}`), {
      method: 'POST',
      headers: this.defaultHeaders,
      body: JSON.stringify(chatData),
      signal: AbortSignal.timeout(this.timeout),
    });

    await this.raiseForStatus(response);
    const result = await this.consumeStreamingResponse(response);

    // If autoConfirm is enabled and result requires confirmation, automatically confirm
    if (autoConfirm && result.type === 'destructive_confirmation') {
      const confirmData: ConfirmData = {
        sql_query: result.sql_query as string,
        confirmation: 'YES',
        chat: chatData.messages,
      };
      return this.confirm(graphId, confirmData);
    }

    return result;
  }

  /**
   * Confirm destructive operation and return result.
   */
  async confirm(graphId: string, confirmData: ConfirmData): Promise<APIResponse> {
    const response = await fetch(this.url(`/graphs/${graphId}/confirm`), {
      method: 'POST',
      headers: this.defaultHeaders,
      body: JSON.stringify(confirmData),
      signal: AbortSignal.timeout(this.timeout),
    });

    await this.raiseForStatus(response);
    return this.consumeStreamingResponse(response);
  }

  /**
   * Consume a streaming response and return the final result.
   * Properly buffers chunks and splits on the exact MESSAGE_DELIMITER.
   */
  private async consumeStreamingResponse(response: Response): Promise<APIResponse> {
    const events: APIResponse[] = [];

    if (!response.body) {
      return {};
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
      let done = false;
      while (!done) {
        const { done: chunkDone, value } = await reader.read();
        done = chunkDone;
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        buffer += chunk;

        // Split by the delimiter and process complete messages
        const parts = buffer.split(MESSAGE_DELIMITER);

        // Keep the last part in the buffer (it may be incomplete)
        buffer = parts[parts.length - 1];

        // Process all complete messages
        for (let i = 0; i < parts.length - 1; i++) {
          const part = parts[i].trim();
          if (!part) continue;

          try {
            const event = JSON.parse(part);
            events.push(event);
          } catch {
            // If not valid JSON, store as raw text
            events.push({ raw: part });
          }
        }
      }

      // Process any remaining data in the buffer
      if (buffer.trim()) {
        try {
          const event = JSON.parse(buffer.trim());
          events.push(event);
        } catch {
          events.push({ raw: buffer.trim() });
        }
      }
    } finally {
      reader.releaseLock();
    }

    // Return the last event which typically contains the final result
    return events.length > 0 ? events[events.length - 1] : {};
  }
}