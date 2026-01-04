/**
 * E2E Test Configuration for URLs and Endpoints
 * 
 * Centralizes all URL configuration for E2E tests.
 * Uses environment variables with sensible defaults.
 */

export const config = {
  /**
   * Base URL for the API server
   * Override with API_BASE_URL environment variable
   */
  baseUrl: process.env.API_BASE_URL || 'http://localhost:5000',
  
  /**
   * Test user credentials
   * Override with TEST_USER_EMAIL and TEST_USER_PASSWORD environment variables
   */
  testUser: {
    email: process.env.TEST_USER_EMAIL || 'test@example.com',
    password: process.env.TEST_USER_PASSWORD || 'testpassword123',
  },

  /**
   * Second test user credentials for multi-user tests
   * Override with TEST_USER2_EMAIL and TEST_USER2_PASSWORD environment variables
   */
  testUser2: {
    email: process.env.TEST_USER2_EMAIL || 'test2@example.com',
    password: process.env.TEST_USER2_PASSWORD || 'testpassword456',
  },

  /**
   * Third test user credentials for logout tests
   * Override with TEST_USER3_EMAIL and TEST_USER3_PASSWORD environment variables
   */
  testUser3: {
    email: process.env.TEST_USER3_EMAIL || 'test3@example.com',
    password: process.env.TEST_USER3_PASSWORD || 'testpassword789',
  },

  /**
   * Test database connection URLs
   * Override with environment variables for local/CI testing
   */
  testDatabases: {
    postgres: process.env.TEST_POSTGRES_URL || 'postgresql://postgres:postgres@localhost:5432/testdb',
    mysql: process.env.TEST_MYSQL_URL || 'mysql://root:password@localhost:3306/testdb',
  },
} as const;

/**
 * Get the base URL for API calls
 */
export function getBaseUrl(): string {
  return config.baseUrl;
}

/**
 * Get test user credentials
 */
export function getTestUser() {
  return config.testUser;
}

/**
 * Get second test user credentials
 */
export function getTestUser2() {
  return config.testUser2;
}

/**
 * Get third test user credentials
 */
export function getTestUser3() {
  return config.testUser3;
}

/**
 * Get test database connection URLs
 */
export function getTestDatabases() {
  return config.testDatabases;
}
