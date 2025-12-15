# E2E Testing with Playwright

This directory contains End-to-End (E2E) tests for QueryWeaver using Playwright. These tests verify the application's functionality from a user's perspective, testing the complete user workflows.

## Overview

The E2E test suite covers:

- **Basic Functionality**: Page loading, UI structure, responsive design
- **Authentication Flow**: Login/logout processes (OAuth integration)
- **File Upload**: CSV, JSON file processing and data loading
- **Chat Interface**: Query submission and response handling
- **API Endpoints**: Direct API testing and error handling

## Test Structure

```
tests/e2e/
├── pages/              # Page Object Model classes
│   ├── base_page.py   # Base page with common functionality
│   └── home_page.py   # Home/ page interactions
├── fixtures/          # Test data and utilities
│   └── test_data.py   # Sample data generators
├── test_basic_functionality.py  # Core app functionality tests
├── test_file_upload.py          # File upload feature tests
├── test_chat_functionality.py   # Chat interface tests
└── test_api_endpoints.py        # Direct API endpoint tests
```

## Quick Start

### Prerequisites

1. Python 3.12+
2. pipenv
3. Docker (for FalkorDB, optional for basic tests)

### Setup

Run the setup script:
```bash
./setup_e2e_tests.sh
```

Or manually:
```bash
# Install dependencies
pipenv sync --dev

# Install Playwright browsers
pipenv run playwright install chromium

# Copy environment file
cp .env.example .env
# Edit .env with your settings
```

### Running Tests

```bash
# Run all tests
make test

# Run only E2E tests (headless)
make test-e2e

# Run E2E tests with visible browser
make test-e2e-headed

# Run specific test file
pipenv run pytest tests/e2e/test_basic_functionality.py -v

# Run with debugging
make test-e2e-debug
```

## Test Categories

### ✅ Basic Functionality Tests
These tests run without authentication and verify:
- Application loads correctly
- UI structure is present
- Responsive design works
- Error handling for invalid routes

### ⏸️ Authentication Tests
Currently skipped (require OAuth setup):
- Google OAuth login flow
- GitHub OAuth login flow
- Session management
- Authenticated user interface

### ⏸️ File Upload Tests
Currently skipped (require authentication):
- CSV file upload and processing
- JSON file upload and processing
- Invalid file handling
- File processing feedback

### ⏸️ Chat Functionality Tests
Currently skipped (require authentication + data):
- Query submission
- Response streaming
- Multiple query handling
- Graph selection

### ✅ API Endpoint Tests
These test the API directly:
- Health checks
- Authentication-protected endpoints
- Static file serving
- Error responses

## Configuration

### Environment Variables

Key environment variables for testing:
```bash
# Required for FastAPI
FASTAPI_SECRET_KEY=your-secret-key
APP_ENV=development
FASTAPI_DEBUG=False

# Database connection (optional for basic tests)
FALKORDB_HOST=localhost
FALKORDB_PORT=6379

# OAuth (required for full E2E tests)
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GITHUB_CLIENT_ID=your-github-client-id
GITHUB_CLIENT_SECRET=your-github-client-secret
```

### Test Markers

Tests use pytest markers for organization:
- `@pytest.mark.skip()`: Tests requiring setup
- Can add custom markers like `@pytest.mark.auth` for authenticated tests

## CI/CD Integration

### GitHub Actions

The E2E tests run automatically in CI via `.github/workflows/tests.yml`:

- **Unit Tests**: Run first to catch basic issues
- **E2E Tests**: Run after unit tests pass
- **Services**: Automatically starts FalkorDB container
- **Artifacts**: Saves screenshots and reports on failure

### Running Locally with Docker

Start FalkorDB for full testing:
```bash
make docker-falkordb
make test-e2e
make docker-stop
```

## Debugging Tests

### Screenshots and Videos

Failed tests automatically capture:
- Screenshots at failure point
- Video recordings (in CI)
- Browser console logs

### Running in Debug Mode

```bash
# Run with visible browser and slow motion
make test-e2e-debug

# Run specific test with debugging
pipenv run pytest tests/e2e/test_basic_functionality.py::TestBasicFunctionality::test_home_page_loads -v --headed
```

### Common Issues

1. **Port Conflicts**: Ensure port 5000 is available
2. **Browser Installation**: Run `pipenv run playwright install chromium`
3. **FalkorDB Connection**: Check if FalkorDB is running on port 6379
4. **Environment Variables**: Verify `.env` file is configured

## Extending Tests

### Adding New Tests

1. **Create Test File**: Follow naming convention `test_*.py`
2. **Use Page Objects**: Extend existing page objects or create new ones
3. **Add Test Data**: Use fixtures in `tests/e2e/fixtures/`
4. **Mark Appropriately**: Use `@pytest.mark.skip()` for tests requiring setup

### Page Object Example

```python
from tests.e2e.pages.base_page import BasePage

class NewPage(BasePage):
    BUTTON_SELECTOR = "#my-button"

    def click_button(self):
        self.page.click(self.BUTTON_SELECTOR)
```

### Test Example

```python
def test_new_functionality(page_with_base_url):
    page_obj = NewPage(page_with_base_url)
    page_obj.navigate_to("/new-route")
    page_obj.click_button()
    assert page_obj.get_page_title() == "Expected Title"
```

## Future Improvements

- [ ] Add authentication setup for full E2E testing
- [ ] Add performance testing with Playwright
- [ ] Add visual regression testing
- [ ] Add mobile device testing
- [ ] Add accessibility testing
- [ ] Add database state verification
- [ ] Add test data management utilities

## Contributing

When adding new tests:

1. Follow the existing Page Object Model pattern
2. Add appropriate test markers
3. Update this README if adding new test categories
4. Ensure tests can run in CI environment
5. Add proper cleanup for any test data created
