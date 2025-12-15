# E2E Testing with Playwright (TypeScript)

This directory contains End-to-End (E2E) tests for QueryWeaver using Playwright with TypeScript. The architecture follows the same pattern as [falkordb-browser](https://github.com/FalkorDB/falkordb-browser).

## Directory Structure

```
tests/e2e/
├── config/               # Configuration files
│   ├── constants.ts     # Test constants
│   └── urls.json        # URL configurations
├── infra/               # Infrastructure layer
│   ├── ui/              # UI utilities
│   │   ├── basePage.ts      # Base page class
│   │   └── browserWrapper.ts # Browser wrapper
│   └── utils.ts         # Utility functions
├── logic/               # Business logic layer
│   ├── POM/             # Page Object Model classes
│   │   └── homePage.ts  # Home page object
│   └── api/             # API utilities
│       └── apiCalls.ts  # API call utilities
└── tests/               # Test specifications
    ├── basicFunctionality.spec.ts
    ├── apiEndpoints.spec.ts
    └── unauthenticatedFlow.spec.ts
```

This structure matches the falkordb-browser pattern with:
- **logic/POM/** - Page Object Model classes for UI interactions
- **logic/api/** - API call utilities for backend testing
- **tests/** - Test specification files
- **infra/** - Infrastructure utilities (browser wrapper, helpers)
- **config/** - Configuration files

## Prerequisites

- Node.js 20+
- Python 3.12+
- pipenv
- Docker (for FalkorDB, optional for basic tests)

## Setup

### 1. Install Dependencies

```bash
# Install Node dependencies (includes Playwright)
npm install

# Install Python dependencies
pipenv sync --dev

# Install Playwright browsers
npx playwright install chromium
```

### 2. Build Frontend

```bash
make build-dev
```

### 3. Environment Configuration

Create `.env` file:

```bash
cp .env.example .env
# Edit .env with required settings
```

Required environment variables for testing:
```env
FASTAPI_SECRET_KEY=test-secret-key
FALKORDB_HOST=localhost
FALKORDB_PORT=6379
APP_ENV=development
ENABLE_TEST_AUTH=true
```

## Running Tests

### Run All Tests

```bash
# Headless mode (default)
npm run test:e2e

# Or using npx
npx playwright test
```

### Run with Visible Browser

```bash
npm run test:e2e:headed
# Or
npx playwright test --headed
```

### Run in Debug Mode

```bash
npm run test:e2e:debug
# Or
npx playwright test --debug
```

### Run with UI Mode

```bash
npm run test:e2e:ui
# Or
npx playwright test --ui
```

### Run Specific Test File

```bash
npx playwright test tests/e2e/tests/basicFunctionality.spec.ts
```

### Run Specific Test

```bash
npx playwright test -g "should load the application successfully"
```

## Test Suites

### Basic Functionality Tests (`basicFunctionality.spec.ts`)

Tests core application functionality:
- Application loading and rendering
- File upload interface
- Responsive design at different screen sizes
- Error handling for invalid routes

### API Endpoints Tests (`apiEndpoints.spec.ts`)

Tests API endpoints directly:
- Health check endpoint
- Authentication-protected endpoints
- OAuth login endpoints (Google, GitHub)
- Error responses (404, 405)
- CORS handling
- Response times

### Unauthenticated Flow Tests (`unauthenticatedFlow.spec.ts`)

Tests the user experience for unauthenticated users:
- UI elements for unauthenticated users
- Authentication prompts
- Login button redirects to OAuth
- Restricted feature blocking

## Architecture Components

### Page Object Model (POM)

Located in `logic/POM/`, these classes encapsulate page interactions:

```typescript
// Example: HomePage
const homePage = new HomePage(page);
await homePage.navigateToHome();
await homePage.isAuthenticated();
```

### API Utilities

Located in `logic/api/`, these classes handle API interactions:

```typescript
// Example: ApiCalls
const apiCalls = new ApiCalls();
const isHealthy = await apiCalls.healthCheck(request, baseURL);
```

### Infrastructure Layer

Located in `infra/`, provides core utilities:

- **BasePage**: Base class for all page objects
- **BrowserWrapper**: Wraps browser functionality
- **utils**: Helper functions (waiting, screenshots, etc.)

## Configuration

### Playwright Configuration (`playwright.config.ts`)

Key settings:
- Test directory: `./tests/e2e/tests`
- Base URL: `http://localhost:5000`
- Retries on CI: 2
- Screenshot on failure: enabled
- Video on failure: enabled
- Web server: Automatically starts FastAPI before tests

### TypeScript Configuration (`tsconfig.json`)

Configured for Playwright with proper type definitions and module resolution.

## CI/CD Integration

### GitHub Actions

Tests run automatically via `.github/workflows/playwright.yml`:

- Runs on push/PR to main and develop branches
- Sets up Python, Node.js, and dependencies
- Starts FalkorDB service
- Runs all Playwright tests
- Uploads test reports and artifacts on failure

### Running Tests in CI

The CI workflow:
1. Installs all dependencies
2. Builds the frontend
3. Starts FalkorDB service
4. Creates test environment configuration
5. Runs Playwright tests
6. Uploads artifacts (reports, screenshots, videos)

## Test Reports

After running tests, view the HTML report:

```bash
npx playwright show-report
```

Reports include:
- Test results and timing
- Screenshots on failure
- Videos of failed tests
- Trace files for debugging

## Debugging

### View Traces

When a test fails, view the trace:

```bash
npx playwright show-trace test-results/[test-name]/trace.zip
```

### Run with Inspector

```bash
npx playwright test --debug
```

### Slow Motion

```bash
npx playwright test --headed --slow-mo=1000
```

## Best Practices

1. **Page Object Model**: Always use POM classes for page interactions
2. **Selectors**: Use data-testid attributes when possible
3. **Waits**: Use Playwright's auto-waiting, avoid hard timeouts
4. **Assertions**: Use Playwright's expect for automatic retries
5. **Test Isolation**: Each test should be independent
6. **Clean Up**: Tests automatically clean up resources

## Adding New Tests

### 1. Create Page Object (if needed)

```typescript
// tests/e2e/logic/POM/newPage.ts
import { Page, Locator } from "@playwright/test";
import BasePage from "../../infra/ui/basePage";

export default class NewPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  get myButton(): Locator {
    return this.page.locator("#my-button");
  }

  async clickButton() {
    await this.myButton.click();
  }
}
```

### 2. Create Test File

```typescript
// tests/e2e/tests/newFeature.spec.ts
import { test, expect } from "@playwright/test";
import NewPage from "../logic/POM/newPage";

test.describe("New Feature Tests", () => {
  test("should test new feature", async ({ page }) => {
    const newPage = new NewPage(page);
    await page.goto("/");
    await newPage.clickButton();
    expect(await page.title()).toBeTruthy();
  });
});
```

## Common Issues

### Port Conflicts

If port 5000 is in use:
```bash
# Kill process on port 5000
lsof -ti:5000 | xargs kill -9
```

### FalkorDB Not Running

```bash
# Start FalkorDB
docker run -d --name falkordb-test -p 6379:6379 falkordb/falkordb:latest

# Stop FalkorDB
docker stop falkordb-test && docker rm falkordb-test
```

### Browser Not Installed

```bash
npx playwright install chromium
```

## Contributing

When adding new tests:

1. Follow the existing directory structure
2. Use the Page Object Model pattern
3. Add proper TypeScript types
4. Include descriptive test names
5. Test your changes locally and ensure they pass twice
6. Verify tests pass in CI

## Resources

- [Playwright Documentation](https://playwright.dev/)
- [Playwright Test API](https://playwright.dev/docs/api/class-test)
- [FalkorDB Browser E2E Tests](https://github.com/FalkorDB/falkordb-browser/tree/main/e2e)
