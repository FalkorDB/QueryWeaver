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
    # Start the Flask app using pipenv
    process = subprocess.Popen([
        "pipenv", "run", "flask", "--app", "api.index", "run", 
        "--host", "localhost", "--port", "5000"
    ], cwd="/home/guy/workspace/text2sql")
    
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
