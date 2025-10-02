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
});