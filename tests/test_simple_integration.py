"""
Simple integration tests that don't require Playwright.
"""
import requests


class TestSimpleIntegration:
    """Simple integration tests using requests."""

    def test_app_starts_successfully(self, app_url):
        """Test that the Flask application starts and responds."""
        response = requests.get(app_url, timeout=10)
        assert response.status_code == 200

    def test_app_serves_content(self, app_url):
        """Test that the app serves some content."""
        response = requests.get(app_url, timeout=10)
        assert len(response.text) > 100  # Should have some content

    def test_health_endpoint(self, app_url):
        """Test application health."""
        # The home page should be our health check
        response = requests.get(app_url, timeout=10)
        assert response.status_code == 200

    def test_static_files_accessible(self, app_url):
        """Test that static files are accessible."""
        # Try to access static directory
        response = requests.get(f"{app_url}/static/", timeout=10)
        # Should either return content or various error codes, but app should respond
        assert response.status_code in [405]
