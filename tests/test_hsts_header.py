"""
Test for security header presence in responses.
"""
import pytest
from fastapi.testclient import TestClient
from api.index import app


def parse_csp(csp: str) -> dict[str, list[str]]:
    """Split a Content-Security-Policy header into {directive: [sources]}."""
    directives = {}
    for part in csp.split(";"):
        tokens = part.split()
        if tokens:
            directives[tokens[0]] = tokens[1:]
    return directives


# Expected source lists are spelled out in full rather than substring-matched,
# so widening a directive has to be a deliberate change in both files.
EXPECTED_DEFAULT_CSP = {
    "default-src": ["'self'"],
    "script-src": ["'self'"],
    "style-src": ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],
    "img-src": ["'self'", "data:"],
    "font-src": ["'self'", "https://fonts.gstatic.com"],
    "connect-src": ["'self'", "https://api.github.com"],
    "frame-ancestors": ["'none'"],
    "object-src": ["'none'"],
    "base-uri": ["'self'"],
}

EXPECTED_DOCS_CSP = {
    "default-src": ["'self'"],
    "script-src": [
        "'self'",
        "'unsafe-inline'",
        "'unsafe-eval'",
        "https://cdn.jsdelivr.net",
        "https://unpkg.com",
    ],
    "style-src": [
        "'self'",
        "'unsafe-inline'",
        "https://cdn.jsdelivr.net",
        "https://fonts.googleapis.com",
    ],
    "img-src": ["'self'", "data:", "https://cdn.jsdelivr.net"],
    "font-src": ["'self'", "https://fonts.gstatic.com", "data:"],
    "connect-src": ["'self'"],
    "frame-ancestors": ["'none'"],
    "object-src": ["'none'"],
    "base-uri": ["'self'"],
}


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
        """Test that the SPA CSP matches the expected source lists exactly."""
        response = client.get("/")
        csp = response.headers.get("content-security-policy")
        assert csp is not None
        assert parse_csp(csp) == EXPECTED_DEFAULT_CSP

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
        assert "payment=()" in policy

    def test_security_headers_on_api_endpoints(self, client):
        """Test that all security headers are present on API endpoints."""
        response = client.get("/graphs")
        assert "x-content-type-options" in response.headers
        assert "x-frame-options" in response.headers
        assert "content-security-policy" in response.headers
        assert "referrer-policy" in response.headers
        assert "permissions-policy" in response.headers

    def test_csp_allows_live_cross_origin_fetches(self, client):
        """Test that the CSP permits every origin the SPA actually calls.

        The SPA reads GitHub star counts from api.github.com and pulls
        Google Fonts from an @import in app/src/index.css. Dev serves no CSP
        header, so a missing source here only breaks production.
        """
        response = client.get("/")
        directives = parse_csp(response.headers["content-security-policy"])
        assert directives["connect-src"] == ["'self'", "https://api.github.com"]
        assert directives["style-src"] == [
            "'self'",
            "'unsafe-inline'",
            "https://fonts.googleapis.com",
        ]
        assert directives["font-src"] == ["'self'", "https://fonts.gstatic.com"]

    def test_csp_docs_allows_cdn(self, client):
        """Test that /docs gets the permissive CSP needed for CDN assets."""
        response = client.get("/docs")
        csp = response.headers.get("content-security-policy")
        assert csp is not None
        assert parse_csp(csp) == EXPECTED_DOCS_CSP

    def test_security_headers_on_forbidden_static(self, client):
        """Test that early-return 403 responses also include security headers."""
        response = client.get("/static/")
        assert response.status_code == 403
        assert "strict-transport-security" in response.headers
        assert "x-content-type-options" in response.headers
        assert "content-security-policy" in response.headers
