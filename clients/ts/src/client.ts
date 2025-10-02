import { ChatData, ConfirmData, APIResponse, QueryWeaverClientOptions, APIError } from './types';

/**
 * QueryWeaver HTTP API client.
 *
 * Simple wrapper around the REST API exposed by a running QueryWeaver server.
 * Supports API token authentication (Bearer) and session cookie usage.
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
   */
  async listSchemas(): Promise<APIResponse> {
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
   */
  async query(graphId: string, chatData: ChatData): Promise<APIResponse> {
    const response = await fetch(this.url(`/graphs/${graphId}`), {
      method: 'POST',
      headers: this.defaultHeaders,
      body: JSON.stringify(chatData),
      signal: AbortSignal.timeout(this.timeout),
    });

    await this.raiseForStatus(response);
    return this.consumeStreamingResponse(response);
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
   */
  private async consumeStreamingResponse(response: Response): Promise<APIResponse> {
    const events: APIResponse[] = [];

    if (!response.body) {
      return {};
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    try {
      let done = false;
      while (!done) {
        const { done: chunkDone, value } = await reader.read();
        done = chunkDone;
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        if (!chunk.trim()) continue;

        // Split by potential delimiters (||| or newlines)
        const parts = chunk.split('|||');
        for (const part of parts) {
          const trimmedPart = part.trim();
          if (!trimmedPart) continue;

          try {
            const event = JSON.parse(trimmedPart);
            events.push(event);
          } catch {
            // If not valid JSON, store as raw text
            events.push({ raw: trimmedPart });
          }
        }
      }
    } finally {
      reader.releaseLock();
    }

    // Return the last event which typically contains the final result
    return events.length > 0 ? events[events.length - 1] : {};
  }
}