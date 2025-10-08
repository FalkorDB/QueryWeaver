export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

export interface ChatData {
  messages: ChatMessage[];
}

export interface ConfirmData {
  sql_query: string;
  confirmation: string;
  chat: ChatMessage[];
}

export interface APIResponse {
  [key: string]: unknown;
}

export interface QueryWeaverClientOptions {
  baseUrl?: string;
  apiToken?: string;
  timeout?: number;
}

export class APIError extends Error {
  constructor(
    message: string,
    public status: number,
    public response?: unknown
  ) {
    super(message);
    this.name = 'APIError';
  }
}