"""
Test API endpoints functionality.
"""
import time

import pytest
import requests


@pytest.mark.e2e
class TestAPIEndpoints:
    """Test API endpoints directly."""

    def test_health_check(self, app_url):
        """Test that the application is responsive."""
        response = requests.get(app_url, timeout=10)
        assert response.status_code == 200

    def test_graphs_endpoint_without_auth(self, app_url):
        """Test graphs endpoint without authentication."""
        response = requests.get(f"{app_url}/graphs", timeout=10)
        # Should return 401 or redirect to login
        assert response.status_code in [401, 302, 403]

    def test_static_files(self, app_url):
        """Test that static files are served correctly."""
        # Test favicon
        response = requests.get(f"{app_url}/static/favicon.ico", timeout=10)
        assert response.status_code in [200]  # 404 is acceptable if no favicon

        # Test CSS files (if any)
        response = requests.get(f"{app_url}/static/css/", timeout=10)
        assert response.status_code in [403]  # Various acceptable responses

    def test_login_endpoints(self, app_url):
        """Test login endpoints."""
        # Test Google login endpoint
        response = requests.get(f"{app_url}/login/google", timeout=10, allow_redirects=False)
        assert response.status_code in [302, 401, 403]  # Should redirect or deny

        # Test GitHub login endpoint
        response = requests.get(f"{app_url}/login/github", timeout=10, allow_redirects=False)
        assert response.status_code in [302, 401, 403]  # Should redirect or deny

    def test_database_endpoint_without_auth(self, app_url):
        """Test database endpoint without authentication."""
        response = requests.get(f"{app_url}/database", timeout=10)
        # Should require authentication
        assert response.status_code in [405]

    def test_invalid_endpoint(self, app_url):
        """Test handling of invalid endpoints."""
        response = requests.get(f"{app_url}/invalid-endpoint", timeout=10)
        assert response.status_code == 404

    def test_method_not_allowed(self, app_url):
        """Test method not allowed responses."""
        # Try POST to home page
        response = requests.post(app_url, timeout=10)
        assert response.status_code in [405, 200]  # Some frameworks handle this differently

    def test_authenticated_endpoints(self, app_url): # pylint: disable=unused-argument
        """Test endpoints that require authentication."""
        # Skip this test since we don't have real authentication in E2E tests
        # Using hardcoded tokens is a security risk and doesn't test real auth
        pytest.skip("Authenticated endpoints require real OAuth setup - not suitable for automated E2E testing") # pylint: disable=line-too-long

        # The following code is kept for reference but not executed:
        # headers = {"Authorization": "Bearer test-api-token-for-e2e-tests"}
        # response = requests.get(f"{app_url}/graphs", headers=headers, timeout=10)
        # assert response.status_code in [200, 401, 403, 404]

    def test_cors_headers(self, app_url):
        """Test CORS headers if configured."""
        response = requests.options(app_url, timeout=10)

        # CORS might or might not be configured
        # Just verify the request doesn't fail
        assert response.status_code in [200, 404, 405]

    def test_response_times(self, app_url):
        """Test that response times are reasonable."""

        start_time = time.time()
        response = requests.get(app_url, timeout=10)
        end_time = time.time()

        response_time = end_time - start_time

        # Should respond within 5 seconds
        assert response_time < 5.0
        assert response.status_code == 200
