"""Playwright configuration for E2E tests."""

import os
import subprocess
import time

# SECRET_TOKEN must be set before any test imports api.index (which triggers
# app creation and the startup SECRET_TOKEN requirement check).
os.environ.setdefault("SECRET_TOKEN", "test-secret-token")

import pytest  # pylint: disable=wrong-import-position
import requests  # pylint: disable=wrong-import-position


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "e2e: mark test as end-to-end test"
    )


@pytest.fixture(scope="session")
def fastapi_app():
    """Start the FastAPI application for testing."""
    # Ensure required environment variables are set for testing
    env_defaults = {
        'FALKORDB_HOST': 'localhost',
        'FALKORDB_PORT': '6379',
        'FASTAPI_SECRET_KEY': 'test-secret-key-for-e2e-tests',
        'GOOGLE_CLIENT_ID': 'test-google-client-id',
        'GOOGLE_CLIENT_SECRET': 'test-google-client-secret',
        'GITHUB_CLIENT_ID': 'test-github-client-id',
        'GITHUB_CLIENT_SECRET': 'test-github-client-secret',
        'SECRET_TOKEN': 'test-secret-token',
        'ENABLE_TEST_AUTH': 'true',  # Enable test auth bypass for E2E tests
    }
    for var, default in env_defaults.items():
        if not os.getenv(var):
            os.environ[var] = default

    # Get the project root directory (parent of tests directory)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)

    # Use a different port for tests to avoid conflicts
    test_port = 5001

    # Start the FastAPI app using uv, with output visible for debugging
    process = subprocess.Popen([  # pylint: disable=consider-using-with
        "uv", "run", "uvicorn", "api.index:app",
        "--host", "localhost", "--port", str(test_port)
    ], cwd=project_root)

    # Wait for the app to start
    max_retries = 30
    app_started = False
    base_url = f"http://localhost:{test_port}"

    for i in range(max_retries):
        try:
            response = requests.get(base_url, timeout=2)
            if response.status_code == 200:
                app_started = True
                break
        except requests.exceptions.RequestException:
            # Check if process is still running
            if process.poll() is not None:
                print(f"FastAPI process died early with return code: {process.returncode}")
                break
            if i % 10 == 0:  # Print progress every 10 retries
                print(f"Waiting for app to start... attempt {i+1}/{max_retries}")
            time.sleep(1)

    if not app_started:
        process.terminate()
        process.wait()
        print(f"FastAPI app failed to start after {max_retries} retries")
        raise RuntimeError("FastAPI app failed to start")

    yield base_url

    # Cleanup
    process.terminate()
    process.wait()


@pytest.fixture
def app_url(fastapi_app):  # pylint: disable=redefined-outer-name
    """Provide the base URL for the application."""
    return fastapi_app


@pytest.fixture
def page_with_base_url(page, app_url):  # pylint: disable=redefined-outer-name
    """Provide a page with app_url attribute set."""
    # Attach app_url to the page object for test code that expects it
    page.app_url = app_url
    page.goto(app_url, wait_until="domcontentloaded", timeout=60000)
    yield page


@pytest.fixture
def authenticated_page(page, app_url):  # pylint: disable=redefined-outer-name
    """Provide a page with test authentication enabled."""
    # Set test authentication cookie that the server will recognize
    # when ENABLE_TEST_AUTH=true
    page.context.add_cookies([{
        'name': 'test_auth_token',
        'value': 'test-user-token',
        'domain': 'localhost',
        'path': '/',
        'httpOnly': False,  # Allow JS access for testing
        'secure': False,    # HTTP in test environment
        'sameSite': 'Lax'
    }])

    page.app_url = app_url
    page.goto(app_url, wait_until="domcontentloaded", timeout=60000)
    yield page
