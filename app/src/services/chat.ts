import { API_CONFIG, buildApiUrl } from '@/config/api';
import type { ChatRequest, StreamMessage, ConfirmRequest } from '@/types/api';

/**
 * Chat/Query Service
 * Handles streaming chat queries to the QueryWeaver backend
 */

export class ChatService {
  /**
   * Send a chat query and receive streaming responses
   * Returns an async generator that yields StreamMessage objects
   */
  static async *streamQuery(request: ChatRequest): AsyncGenerator<StreamMessage, void, unknown> {
    try {
      // The backend expects POST /graphs/{database_id}
      const endpoint = `/graphs/${encodeURIComponent(request.database)}`;
      
      // Transform conversation history to backend format
      // Backend expects: chat: ["user msg", "ai msg", "user msg", ...]
      const chatHistory: string[] = [];
      if (request.history && request.history.length > 0) {
        for (const msg of request.history) {
          chatHistory.push(msg.content);
        }
      }
      // Add current query to the chat array
      chatHistory.push(request.query);
      
      const response = await fetch(buildApiUrl(endpoint), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          chat: chatHistory,
          // Optional fields the backend supports:
          // result: [],  // Previous results if needed
          // instructions: ""  // Additional instructions if needed
        }),
        credentials: 'include',
      });

      console.log('Chat response status:', response.status);

      if (!response.ok) {
        const errorText = await response.text();
        console.error('Chat error response:', errorText);
        
        try {
          const errorData = JSON.parse(errorText);
          const errorMessage = errorData.error || errorData.detail || errorData.message || 'Failed to send query';
          throw new Error(errorMessage);
        } catch (parseError) {
          // If JSON parsing fails, use the text directly
          throw new Error(errorText || `Request failed with status ${response.status}`);
        }
      }

      if (!response.body) {
        throw new Error('No response body');
      }

      // Read the streaming response
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      try {
        while (true) {
          const { done, value } = await reader.read();
          
          if (done) {
            console.log('Stream done. Final buffer:', buffer);
            break;
          }

          // Decode the chunk and add to buffer
          const chunk = decoder.decode(value, { stream: true });
          console.log('Received chunk:', chunk);
          buffer += chunk;

          // Split by boundary marker
          const parts = buffer.split(API_CONFIG.STREAM_BOUNDARY);
          console.log('Split into parts:', parts.length, 'parts');
          
          // Keep the last part in buffer (might be incomplete)
          buffer = parts.pop() || '';

          // Process complete messages
          for (const part of parts) {
            const trimmed = part.trim();
            if (!trimmed) continue;

            console.log('Processing message part:', trimmed);
            try {
              const message: StreamMessage = JSON.parse(trimmed);
              console.log('Parsed message:', message);
              yield message;
            } catch (e) {
              console.error('Failed to parse stream message:', trimmed, e);
              // Yield error message instead of silently failing
              yield {
                type: 'error',
                content: `Failed to parse server response: ${trimmed.substring(0, 100)}...`
              } as StreamMessage;
            }
          }
        }

        // Process any remaining buffer
        if (buffer.trim()) {
          try {
            const message: StreamMessage = JSON.parse(buffer.trim());
            yield message;
          } catch (e) {
            console.error('Failed to parse final message:', buffer, e);
            yield {
              type: 'error',
              content: `Failed to parse final server response`
            } as StreamMessage;
          }
        }
      } catch (streamError) {
        console.error('Stream reading error:', streamError);
        yield {
          type: 'error',
          content: `Stream error: ${streamError instanceof Error ? streamError.message : 'Unknown streaming error'}`
        } as StreamMessage;
      }
    } catch (error) {
      console.error('Failed to stream query:', error);
      
      // Yield error message before throwing
      yield {
        type: 'error',
        content: error instanceof Error ? error.message : 'Unknown error occurred'
      } as StreamMessage;
      
      throw error;
    }
  }

  /**
   * Confirm a destructive SQL operation and stream results
   * Used when the backend requires confirmation for INSERT/UPDATE/DELETE
   */
  static async *streamConfirmOperation(
    database: string,
    request: ConfirmRequest
  ): AsyncGenerator<StreamMessage, void, unknown> {
    try {
      // The backend expects POST /graphs/{database}/confirm
      const endpoint = `/graphs/${encodeURIComponent(database)}/confirm`;

      const response = await fetch(buildApiUrl(endpoint), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(request),
        credentials: 'include',
      });

      console.log('Confirmation response status:', response.status);

      if (!response.ok) {
        const errorText = await response.text();
        console.error('Confirmation error response:', errorText);

        try {
          const errorData = JSON.parse(errorText);
          const errorMessage = errorData.error || errorData.detail || errorData.message || 'Failed to confirm operation';
          throw new Error(errorMessage);
        } catch (parseError) {
          throw new Error(errorText || `Request failed with status ${response.status}`);
        }
      }

      if (!response.body) {
        throw new Error('No response body');
      }

      // Read the streaming response (same logic as streamQuery)
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      try {
        while (true) {
          const { done, value } = await reader.read();

          if (done) {
            console.log('Confirmation stream done. Final buffer:', buffer);
            break;
          }

          const chunk = decoder.decode(value, { stream: true });
          console.log('Received confirmation chunk:', chunk);
          buffer += chunk;

          const parts = buffer.split(API_CONFIG.STREAM_BOUNDARY);
          console.log('Split into parts:', parts.length, 'parts');

          buffer = parts.pop() || '';

          for (const part of parts) {
            const trimmed = part.trim();
            if (!trimmed) continue;

            console.log('Processing confirmation message part:', trimmed);
            try {
              const message: StreamMessage = JSON.parse(trimmed);
              console.log('Parsed confirmation message:', message);
              yield message;
            } catch (e) {
              console.error('Failed to parse confirmation stream message:', trimmed, e);
              yield {
                type: 'error',
                content: `Failed to parse server response: ${trimmed.substring(0, 100)}...`
              } as StreamMessage;
            }
          }
        }

        // Process any remaining buffer
        if (buffer.trim()) {
          try {
            const message: StreamMessage = JSON.parse(buffer.trim());
            yield message;
          } catch (e) {
            console.error('Failed to parse final confirmation message:', buffer, e);
            yield {
              type: 'error',
              content: `Failed to parse final server response`
            } as StreamMessage;
          }
        }
      } catch (streamError) {
        console.error('Confirmation stream reading error:', streamError);
        yield {
          type: 'error',
          content: `Stream error: ${streamError instanceof Error ? streamError.message : 'Unknown streaming error'}`
        } as StreamMessage;
      }
    } catch (error) {
      console.error('Failed to stream confirmation:', error);

      yield {
        type: 'error',
        content: error instanceof Error ? error.message : 'Unknown error occurred'
      } as StreamMessage;

      throw error;
    }
  }

  /**
   * Helper function to consume the stream and collect all messages
   * Useful for simpler use cases where you want all messages at once
   */
  static async executeQuery(request: ChatRequest): Promise<StreamMessage[]> {
    const messages: StreamMessage[] = [];
    
    try {
      for await (const message of ChatService.streamQuery(request)) {
        messages.push(message);
      }
      return messages;
    } catch (error) {
      console.error('Failed to execute query:', error);
      throw error;
    }
  }
}

