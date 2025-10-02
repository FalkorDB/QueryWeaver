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
});