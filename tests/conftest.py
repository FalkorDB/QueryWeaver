"""
Playwright configuration for E2E tests.
"""
import pytest
import subprocess
import time
import requests


@pytest.fixture(scope="session")
def flask_app():
    """Start the Flask application for testing."""
    import os

    # Get the project root directory (parent of tests directory)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)

    # Start the Flask app using pipenv
    process = subprocess.Popen([
        "pipenv", "run", "flask", "--app", "api.index", "run",
        "--host", "localhost", "--port", "5000"
    ], cwd=project_root)

    # Wait for the app to start
    max_retries = 30
    for _ in range(max_retries):
        try:
            response = requests.get("http://localhost:5000/", timeout=1)
            if response.status_code == 200:
                break
        except requests.exceptions.RequestException:
            time.sleep(1)
    else:
        process.terminate()
        raise RuntimeError("Flask app failed to start")

    yield "http://localhost:5000"

    # Cleanup
    process.terminate()
    process.wait()


@pytest.fixture
def app_url(flask_app):
    """Provide the base URL for the application."""
    return flask_app


@pytest.fixture
def page_with_base_url(page, app_url):
    """Provide a page with app_url attribute set."""
    # Attach app_url to the page object for test code that expects it
    page.app_url = app_url
    page.goto(app_url)
    yield page
