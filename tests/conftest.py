"""Playwright configuration for E2E tests."""

import os
import subprocess
import time

import pytest
import requests


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "e2e: mark test as end-to-end test"
    )


@pytest.fixture(scope="session")
def fastapi_app():
    """Start the FastAPI application for testing."""
    
    # Ensure required environment variables are set for testing
    if not os.getenv('FALKORDB_HOST'):
        os.environ['FALKORDB_HOST'] = 'localhost'
    if not os.getenv('FALKORDB_PORT'):
        os.environ['FALKORDB_PORT'] = '6379'
    if not os.getenv('FASTAPI_SECRET_KEY'):
        os.environ['FASTAPI_SECRET_KEY'] = 'test-secret-key-for-e2e-tests'
    
    # Set up mock OAuth credentials for testing
    if not os.getenv('GOOGLE_CLIENT_ID'):
        os.environ['GOOGLE_CLIENT_ID'] = 'test-google-client-id'
    if not os.getenv('GOOGLE_CLIENT_SECRET'):
        os.environ['GOOGLE_CLIENT_SECRET'] = 'test-google-client-secret'
    if not os.getenv('GITHUB_CLIENT_ID'):
        os.environ['GITHUB_CLIENT_ID'] = 'test-github-client-id'
    if not os.getenv('GITHUB_CLIENT_SECRET'):
        os.environ['GITHUB_CLIENT_SECRET'] = 'test-github-client-secret'

    # Get the project root directory (parent of tests directory)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    
    # Use a different port for tests to avoid conflicts
    test_port = 5001

    # Start the FastAPI app using pipenv, with output visible for debugging
    process = subprocess.Popen([
        "pipenv", "run", "uvicorn", "api.index:app",
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
        except requests.exceptions.RequestException as e:
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
def app_url(fastapi_app):
    """Provide the base URL for the application."""
    return fastapi_app


@pytest.fixture
def page_with_base_url(page, app_url):
    """Provide a page with app_url attribute set."""
    # Attach app_url to the page object for test code that expects it
    page.app_url = app_url
    page.goto(app_url)
    yield page


@pytest.fixture
def authenticated_page(page, app_url):
    """Provide a page with mock authentication for testing authenticated features."""
    # Set a mock authentication cookie
    page.context.add_cookies([{
        'name': 'api_token',
        'value': 'test-api-token-for-e2e-tests',
        'domain': 'localhost',
        'path': '/',
        'httpOnly': True
    }])
    
    page.app_url = app_url
    page.goto(app_url)
    yield page
