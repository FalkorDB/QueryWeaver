import { QueryWeaverClient, APIError } from '../src';

describe('QueryWeaverClient', () => {
  let client: QueryWeaverClient;

  beforeEach(() => {
    client = new QueryWeaverClient({
      baseUrl: 'http://localhost:5000',
      apiToken: 'test-token',
    });
  });

  describe('constructor', () => {
    it('should initialize with default values', () => {
      const defaultClient = new QueryWeaverClient();
      expect(defaultClient).toBeInstanceOf(QueryWeaverClient);
    });

    it('should initialize with custom values', () => {
      expect(client).toBeInstanceOf(QueryWeaverClient);
    });
  });

  describe('url generation', () => {
    it('should generate correct URLs', () => {
      // Access private method for testing
      const urlMethod = (client as any).url.bind(client);
      expect(urlMethod('/graphs')).toBe('http://localhost:5000/graphs');
      expect(urlMethod('/graphs/test/data')).toBe('http://localhost:5000/graphs/test/data');
    });
  });

  describe('listSchemas', () => {
    it('should return an array of strings', async () => {
      // Mock fetch to return an array
      global.fetch = jest.fn(() =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(['db1', 'db2', 'db3']),
        } as Response)
      );

      const result = await client.listSchemas();
      expect(Array.isArray(result)).toBe(true);
      expect(result).toEqual(['db1', 'db2', 'db3']);
    });

    it('should return an empty array when no schemas exist', async () => {
      // Mock fetch to return an empty array
      global.fetch = jest.fn(() =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve([]),
        } as Response)
      );

      const result = await client.listSchemas();
      expect(Array.isArray(result)).toBe(true);
      expect(result).toEqual([]);
    });
  });

  describe('query with auto_confirm', () => {
    it('should auto confirm destructive operations when autoConfirm is true', async () => {
      let callCount = 0;
      
      // Mock fetch for both query and confirm calls
      global.fetch = jest.fn(() => {
        callCount++;
        if (callCount === 1) {
          // First call returns confirmation request
          let readCalled = false;
          return Promise.resolve({
            ok: true,
            status: 200,
            body: {
              getReader: () => ({
                read: () => {
                  if (readCalled) {
                    return Promise.resolve({ done: true, value: undefined });
                  }
                  readCalled = true;
                  return Promise.resolve({
                    done: false,
                    value: new TextEncoder().encode(JSON.stringify({
                      type: 'destructive_confirmation',
                      sql_query: 'DELETE FROM users',
                      message: 'This will delete data',
                      confirmation_id: 'confirm-123'
                    }))
                  });
                },
                releaseLock: () => {}
              })
            }
          });
        } else {
          // Second call returns success result
          let readCalled = false;
          return Promise.resolve({
            ok: true,
            status: 200,
            body: {
              getReader: () => ({
                read: () => {
                  if (readCalled) {
                    return Promise.resolve({ done: true, value: undefined });
                  }
                  readCalled = true;
                  return Promise.resolve({
                    done: false,
                    value: new TextEncoder().encode(JSON.stringify({
                      type: 'success',
                      result: 'Deleted 5 users'
                    }))
                  });
                },
                releaseLock: () => {}
              })
            }
          });
        }
      }) as any;

      const chatData = {
        messages: [{ role: 'user' as const, content: 'Delete all users' }]
      };

      const result = await client.query('my_schema', chatData, true);
      
      expect(callCount).toBe(2); // Should have called fetch twice
      expect(result).toHaveProperty('type', 'success');
      expect(result).toHaveProperty('result', 'Deleted 5 users');
    });

    it('should return confirmation request when autoConfirm is false', async () => {
      const data = { type: 'destructive_confirmation', sql_query: 'DELETE FROM users', message: 'This will delete data' };
      let readCalled = false;
      
      // Mock fetch to return confirmation request
      global.fetch = jest.fn(() =>
        Promise.resolve({
          ok: true,
          status: 200,
          body: {
            getReader: () => ({
              read: () => {
                if (readCalled) {
                  return Promise.resolve({ done: true, value: undefined });
                }
                readCalled = true;
                return Promise.resolve({
                  done: false,
                  value: new TextEncoder().encode(JSON.stringify(data))
                });
              },
              releaseLock: () => {}
            })
          }
        } as any)
      ) as any;

      const chatData = {
        messages: [{ role: 'user' as const, content: 'Delete all users' }]
      };

      const result = await client.query('my_schema', chatData, false);
      expect(result).toHaveProperty('type', 'destructive_confirmation');
      expect(result).toHaveProperty('sql_query', 'DELETE FROM users');
    });
  });
});