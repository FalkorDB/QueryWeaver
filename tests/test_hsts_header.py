"""
Test for security header presence in responses.
"""
import pytest
from fastapi.testclient import TestClient
from api.index import app


class TestSecurityHeaders:
    """Test security headers."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return TestClient(app)

    def test_hsts_header_present(self, client):
        """Test that the HSTS header is present in responses."""
        response = client.get("/")

        assert "strict-transport-security" in response.headers
        hsts_header = response.headers["strict-transport-security"]
        assert "max-age=31536000" in hsts_header
        assert "includeSubDomains" in hsts_header
        assert "preload" in hsts_header

    def test_hsts_header_on_api_endpoints(self, client):
        """Test that the HSTS header is present on API endpoints."""
        response = client.get("/graphs")

        assert "strict-transport-security" in response.headers
        hsts_header = response.headers["strict-transport-security"]
        assert "max-age=31536000" in hsts_header
        assert "includeSubDomains" in hsts_header
        assert "preload" in hsts_header

    def test_x_content_type_options(self, client):
        """Test that X-Content-Type-Options is set to nosniff."""
        response = client.get("/")
        assert response.headers.get("x-content-type-options") == "nosniff"

    def test_x_frame_options(self, client):
        """Test that X-Frame-Options is set to DENY."""
        response = client.get("/")
        assert response.headers.get("x-frame-options") == "DENY"

    def test_content_security_policy(self, client):
        """Test that Content-Security-Policy header is present."""
        response = client.get("/")
        csp = response.headers.get("content-security-policy")
        assert csp is not None
        assert "default-src 'self'" in csp
        assert "script-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp
        assert "object-src 'none'" in csp

    def test_referrer_policy(self, client):
        """Test that Referrer-Policy header is present."""
        response = client.get("/")
        assert response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"

    def test_permissions_policy(self, client):
        """Test that Permissions-Policy header is present."""
        response = client.get("/")
        policy = response.headers.get("permissions-policy")
        assert policy is not None
        assert "camera=()" in policy
        assert "microphone=()" in policy
        assert "geolocation=()" in policy

    def test_security_headers_on_api_endpoints(self, client):
        """Test that all security headers are present on API endpoints."""
        response = client.get("/graphs")
        assert "x-content-type-options" in response.headers
        assert "x-frame-options" in response.headers
        assert "content-security-policy" in response.headers
        assert "referrer-policy" in response.headers
        assert "permissions-policy" in response.headers
