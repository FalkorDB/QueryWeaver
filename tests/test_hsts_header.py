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
    "img-src": [
        "'self'",
        "data:",
        "https://*.googleusercontent.com",
        "https://avatars.githubusercontent.com",
    ],
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
    "img-src": [
        "'self'",
        "data:",
        "https://cdn.jsdelivr.net",
        "https://fastapi.tiangolo.com",
    ],
    "font-src": ["'self'", "https://fonts.gstatic.com", "data:"],
    "connect-src": ["'self'"],
    "worker-src": ["'self'", "blob:"],
    "frame-ancestors": ["'none'"],
    "object-src": ["'none'"],
    "base-uri": ["'self'"],
}

# Every header SecurityMiddleware is contracted to set, so a response that
# skips the middleware cannot pass by asserting only a subset.
COMMON_SECURITY_HEADERS = (
    "strict-transport-security",
    "x-content-type-options",
    "x-frame-options",
    "referrer-policy",
    "permissions-policy",
    "content-security-policy",
)


@pytest.mark.unit
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

    def test_csp_allows_the_avatars_the_spa_renders(self, client):
        """Test that img-src covers the identity providers' avatar hosts.

        /auth-status passes the provider's picture URL through verbatim and
        the SPA renders it in <AvatarImage>, so a self-only img-src silently
        degrades every logged-in avatar to the initials fallback.
        """
        response = client.get("/")
        directives = parse_csp(response.headers["content-security-policy"])
        assert "https://*.googleusercontent.com" in directives["img-src"]
        assert "https://avatars.githubusercontent.com" in directives["img-src"]

    def test_csp_docs_allows_cdn(self, client):
        """Test that /docs gets the permissive CSP needed for CDN assets."""
        response = client.get("/docs")
        csp = response.headers.get("content-security-policy")
        assert csp is not None
        assert parse_csp(csp) == EXPECTED_DOCS_CSP

    @pytest.mark.parametrize(
        "path", ["/docs-preview", "/redoc-x", "/openapi-foo", "/docsanything"]
    )
    def test_docs_csp_is_not_handed_to_lookalike_paths(self, client, path):
        """Test that only the exact docs endpoints get the permissive CSP.

        The SPA catch-all serves index.html for any unmatched path, so a
        prefix match would let an attacker pick a URL that turns on
        'unsafe-inline', 'unsafe-eval' and two CDN script sources.
        """
        response = client.get(path)
        assert parse_csp(response.headers["content-security-policy"]) == (
            EXPECTED_DEFAULT_CSP
        )

    def test_security_headers_on_forbidden_static(self, client):
        """Test that early-return 403 responses also include security headers."""
        response = client.get("/static/")
        assert response.status_code == 403
        for header in COMMON_SECURITY_HEADERS:
            assert header in response.headers, header

    def test_security_headers_on_csrf_rejection(self, client):
        """Test that CSRFMiddleware's own 403 still carries the headers.

        CSRFMiddleware returns before call_next, so SecurityMiddleware only
        covers it while it is registered as the outer layer.  This body is
        attacker-reachable JSON, which makes the nosniff header matter.
        """
        response = client.post("/tokens/generate")
        assert response.status_code == 403
        assert response.json()["detail"] == "CSRF token missing or invalid"
        for header in COMMON_SECURITY_HEADERS:
            assert header in response.headers, header
