# Token Management Feature

This document describes the API token management feature implemented for QueryWeaver, allowing users to generate and manage API tokens for authentication.

## Overview

The token management system allows authenticated users to:

1. **Generate API tokens** - Create secure tokens for API access
2. **View token list** - See all their tokens (with only last 4 digits visible)
3. **Delete tokens** - Remove tokens they no longer need
4. **Use tokens for API authentication** - Authenticate API calls using Bearer tokens

## Architecture

### Backend Components

#### 1. Token Routes (`api/routes/tokens.py`)
- **POST `/api/tokens/generate`** - Generate a new token
- **GET `/api/tokens/list`** - List user's tokens
- **DELETE `/api/tokens/{token_id}`** - Delete a specific token

#### 2. Authentication Enhancement (`api/auth/user_management.py`)
- Enhanced `token_required` decorator to support both OAuth and API token authentication
- New `validate_api_token_user()` function for token-based authentication

#### 3. Database Schema
Tokens are stored as nodes in the Organizations graph with the following structure:
```cypher
(:Token {
    token_id: "unique_token_identifier",
    token_hash: "sha256_hash_of_token", 
    created_at: timestamp,
    last_4_digits: "1234"
})-[:HAS_TOKEN]-(:User)
```

### Frontend Components

#### 1. User Interface (`app/templates/components/`)
- **token_modal.j2** - Token management modal with generation and list views
- **user_profile.j2** - Added "API Tokens" button to user profile dropdown

#### 2. TypeScript Module (`app/ts/modules/tokens.ts`)
- Token generation and management functions
- Modal handling and user interactions
- API communication for CRUD operations

#### 3. Styling (`app/public/css/modals.css`)
- Modal styling for token management interface
- Token display and action button styles

## Security Features

### 1. Token Generation
- Uses `secrets.token_urlsafe(32)` for cryptographically secure random tokens
- Tokens are 43 characters long (URL-safe base64 encoding)

### 2. Token Storage
- Only SHA-256 hashes of tokens are stored in the database
- Original tokens are never persisted
- Each token has a unique `token_id` for identification

### 3. Token Display
- After generation, tokens are shown once in full
- In the token list, only last 4 digits are visible (e.g., "****1234")
- Copy-to-clipboard functionality for newly generated tokens

### 4. Authentication
- API calls can use `Authorization: Bearer <token>` header
- Server validates by hashing received token and matching against stored hash
- Falls back to OAuth session authentication if no valid token provided

## API Usage Examples

### 1. Generate a Token
```bash
# Must be authenticated via OAuth session
curl -X POST http://localhost:5000/api/tokens/generate \
  -H "Content-Type: application/json" \
  --cookie "session_cookie=..."
```

Response:
```json
{
  "token": "6SxwdQ3vZeEE6xCVwTmD3AbKvWZY2eR_quUCP7eewEA",
  "token_id": "G13pqOpPohhs2rnou56A2w",
  "created_at": 1706096845,
  "last_4_digits": "ewEA"
}
```

### 2. List Tokens
```bash
curl -X GET http://localhost:5000/api/tokens/list \
  -H "Authorization: Bearer 6SxwdQ3vZeEE6xCVwTmD3AbKvWZY2eR_quUCP7eewEA"
```

Response:
```json
{
  "tokens": [
    {
      "token_id": "G13pqOpPohhs2rnou56A2w",
      "created_at": 1706096845,
      "last_4_digits": "ewEA"
    }
  ]
}
```

### 3. Delete a Token
```bash
curl -X DELETE http://localhost:5000/api/tokens/G13pqOpPohhs2rnou56A2w \
  -H "Authorization: Bearer 6SxwdQ3vZeEE6xCVwTmD3AbKvWZY2eR_quUCP7eewEA"
```

### 4. Use Token for API Access
```bash
# Any protected endpoint can now use token authentication
curl -X GET http://localhost:5000/graphs \
  -H "Authorization: Bearer 6SxwdQ3vZeEE6xCVwTmD3AbKvWZY2eR_quUCP7eewEA"
```

## User Interface Flow

### 1. Accessing Token Management
1. User logs in via OAuth (Google/GitHub)
2. User clicks their profile picture in the top-right corner
3. User clicks "API Tokens" in the dropdown menu
4. Token management modal opens

### 2. Generating a Token
1. User clicks "Generate New Token" button
2. System creates secure token and stores hash in database
3. Full token is displayed once with copy button
4. Token appears in user's token list (showing only last 4 digits)

### 3. Managing Tokens
1. User sees list of all their tokens with creation dates
2. Each token shows only last 4 digits for security
3. User can delete tokens using the "Delete" button
4. Confirmation modal appears before deletion

## Database Queries

### Create Token
```cypher
MATCH (user:User {email: $user_email})
CREATE (token:Token {
    token_id: $token_id,
    token_hash: $token_hash,
    created_at: $created_at,
    last_4_digits: $last_4_digits
})
CREATE (user)-[:HAS_TOKEN]->(token)
RETURN token
```

### List User Tokens
```cypher
MATCH (user:User {email: $user_email})-[:HAS_TOKEN]->(token:Token)
RETURN token.token_id, token.created_at, token.last_4_digits
ORDER BY token.created_at DESC
```

### Validate Token
```cypher
MATCH (user:User)-[:HAS_TOKEN]->(token:Token {token_hash: $token_hash})
RETURN user.email
```

### Delete Token
```cypher
MATCH (user:User {email: $user_email})-[r:HAS_TOKEN]->(token:Token {token_id: $token_id})
DELETE r, token
```

## Testing

The implementation includes comprehensive tests:

- **Unit tests** for token generation and validation functions
- **API tests** for authentication and authorization
- **Integration tests** for token CRUD operations

Run tests:
```bash
make test-unit  # Run unit tests
pipenv run python -m pytest tests/test_tokens.py -v  # Run token-specific tests
```

## Implementation Notes

### 1. Graph Database Integration
- Leverages existing Organizations graph structure
- Tokens connect to User nodes via HAS_TOKEN relationships
- Maintains consistency with existing authentication patterns

### 2. Backward Compatibility
- OAuth authentication continues to work unchanged
- API token authentication is additive, not replacement
- Existing protected routes automatically support both auth methods

### 3. Error Handling
- Comprehensive error handling for database operations
- Proper HTTP status codes and error messages
- Graceful fallback between authentication methods

### 4. Performance Considerations
- Efficient graph queries with proper indexing
- Minimal additional overhead for token validation
- Caching considerations for user email lookups

## Future Enhancements

Potential improvements for the token system:

1. **Token Expiration** - Add configurable expiration dates
2. **Token Scopes** - Limit tokens to specific API operations
3. **Usage Analytics** - Track token usage and last access times
4. **Rate Limiting** - Implement per-token rate limiting
5. **Token Naming** - Allow users to name their tokens for easier management