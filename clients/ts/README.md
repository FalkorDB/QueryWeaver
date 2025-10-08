# QueryWeaver TypeScript Client

A TypeScript client for interacting with the QueryWeaver HTTP API.

## Installation

```bash
npm install queryweaver-client
```

## Usage

```typescript
import { QueryWeaverClient } from 'queryweaver-client';

const client = new QueryWeaverClient({
  baseUrl: 'http://localhost:5000',
  apiToken: 'your-api-token', // optional
});

// List available schemas
const schemas = await client.listSchemas();
console.log(schemas);

// Get schema details
const schema = await client.getSchema('my-schema');
console.log(schema);

// Connect to a database
const result = await client.connectDatabase('postgresql://user:pass@host/db');
console.log(result);

// Run a natural language query
const chatData = {
  messages: [
    { role: 'user', content: 'Show me all users with age > 25' }
  ]
};
const queryResult = await client.query('my-schema', chatData);
console.log(queryResult);

// Handle destructive operations (if confirmation is required)
if (queryResult.type === 'destructive_confirmation') {
  console.log(queryResult.message); // Show warning to user

  const confirmData = {
    sql_query: queryResult.sql_query,
    confirmation: 'YES',
    chat: chatData.messages
  };

  const finalResult = await client.confirm('my-schema', confirmData);
  console.log(finalResult);
}
```

## API Reference

### QueryWeaverClient

#### Constructor Options

```typescript
interface QueryWeaverClientOptions {
  baseUrl?: string;    // Default: 'http://localhost:5000'
  apiToken?: string;   // Optional API token for authentication
  timeout?: number;    // Request timeout in milliseconds (default: 30000)
}
```

#### Methods

- `listSchemas(): Promise<string[]>` - List available schemas/databases
- `getSchema(graphId: string): Promise<APIResponse>` - Get schema details
- `deleteSchema(graphId: string): Promise<APIResponse>` - Delete a schema
- `refreshSchema(graphId: string): Promise<APIResponse>` - Refresh schema
- `connectDatabase(dbUrl: string): Promise<APIResponse>` - Connect to database
- `query(graphId: string, chatData: ChatData, autoConfirm?: boolean): Promise<APIResponse>` - Run natural language query (optional `autoConfirm` to automatically confirm destructive operations)
- `confirm(graphId: string, confirmData: ConfirmData): Promise<APIResponse>` - Confirm destructive operation

## Authentication

The client supports API token authentication via Bearer tokens:

```typescript
const client = new QueryWeaverClient({
  apiToken: 'your-token-here'
});
```

## Error Handling

The client throws `APIError` for HTTP errors:

```typescript
import { QueryWeaverClient, APIError } from 'queryweaver-client';

try {
  const result = await client.listSchemas();
} catch (error) {
  if (error instanceof APIError) {
    console.log(`HTTP ${error.status}: ${error.message}`);
  }
}
```

## Development

```bash
# Install dependencies
npm install

# Run tests
npm test

# Build the project
npm run build

# Run linter
npm run lint
```

## License

MIT