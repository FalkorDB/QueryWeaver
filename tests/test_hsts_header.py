"""
Test for HSTS header presence in responses.
"""
import pytest
from fastapi.testclient import TestClient
from api.index import app


class TestHSTSHeader:
    """Test HSTS security header."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return TestClient(app)

    def test_hsts_header_present(self, client):
        """Test that the HSTS header is present in responses."""
        # Make a request to the root endpoint
        response = client.get("/")

        # Verify HSTS header is present
        assert "strict-transport-security" in response.headers

        # Verify header value contains required directives
        hsts_header = response.headers["strict-transport-security"]
        assert "max-age=31536000" in hsts_header
        assert "includeSubDomains" in hsts_header
        assert "preload" in hsts_header

    def test_hsts_header_on_api_endpoints(self, client):
        """Test that the HSTS header is present on API endpoints."""
        # Test on graphs endpoint
        response = client.get("/graphs")

        # Verify HSTS header is present
        assert "strict-transport-security" in response.headers

        # Verify header value contains required directives
        hsts_header = response.headers["strict-transport-security"]
        assert "max-age=31536000" in hsts_header
        assert "includeSubDomains" in hsts_header
        assert "preload" in hsts_header
