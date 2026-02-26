"""
Tests for CSRF middleware (double-submit cookie pattern).
"""
import pytest
from fastapi.testclient import TestClient
from api.index import app


class TestCSRFMiddleware:
    """Test CSRF double-submit cookie middleware."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return TestClient(app)

    # ---- Cookie provisioning ----

    def test_get_sets_csrf_cookie(self, client):
        """GET responses should include a csrf_token cookie."""
        response = client.get("/auth-status")
        assert response.status_code == 200
        assert "csrf_token" in response.cookies

    def test_csrf_cookie_is_not_httponly(self, client):
        """The CSRF cookie must be readable by JavaScript (not HttpOnly)."""
        response = client.get("/auth-status")
        # TestClient exposes raw Set-Cookie headers
        set_cookie = response.headers.get("set-cookie", "")
        assert "csrf_token=" in set_cookie
        # httponly flag must NOT be present
        assert "httponly" not in set_cookie.lower()

    # ---- Safe methods bypass ----

    def test_get_does_not_require_csrf(self, client):
        """GET requests must not be blocked by CSRF checks."""
        response = client.get("/auth-status")
        assert response.status_code != 403

    def test_head_does_not_require_csrf(self, client):
        """HEAD requests must not be blocked by CSRF checks."""
        response = client.head("/auth-status")
        assert response.status_code != 403

    def test_options_does_not_require_csrf(self, client):
        """OPTIONS requests must not be blocked by CSRF checks."""
        response = client.options("/auth-status")
        assert response.status_code != 403

    # ---- Blocking without token ----

    def test_post_without_csrf_is_blocked(self, client):
        """POST without CSRF header/cookie must return 403."""
        response = client.post("/logout")
        assert response.status_code == 403
        assert response.json()["detail"] == "CSRF token missing or invalid"

    def test_post_with_wrong_csrf_is_blocked(self, client):
        """POST with mismatched CSRF tokens must return 403."""
        response = client.post(
            "/logout",
            headers={"X-CSRF-Token": "wrong-value"},
            cookies={"csrf_token": "correct-value"},
        )
        assert response.status_code == 403

    def test_csrf_rejection_sets_cookie(self, client):
        """A 403 CSRF rejection should still set the csrf_token cookie."""
        response = client.post("/logout")
        assert response.status_code == 403
        assert "csrf_token" in response.cookies

    # ---- Allowing with valid token ----

    def test_post_with_valid_csrf_passes(self, client):
        """POST with matching cookie + header must pass CSRF check."""
        # First get a token
        get_resp = client.get("/auth-status")
        csrf = get_resp.cookies["csrf_token"]

        response = client.post(
            "/logout",
            headers={"X-CSRF-Token": csrf},
            cookies={"csrf_token": csrf},
        )
        # Should not be 403 (will be 200 for logout)
        assert response.status_code != 403

    # ---- Bearer token bypass ----

    def test_bearer_auth_bypasses_csrf(self, client):
        """Requests with Bearer auth should skip CSRF (get 401, not 403)."""
        response = client.post(
            "/tokens/generate",
            headers={"Authorization": "Bearer fake_token_value"},
        )
        # 401 = auth failed (expected), NOT 403 = CSRF blocked
        assert response.status_code == 401

    # ---- Exempt paths ----

    def test_login_path_exempt(self, client):
        """Login endpoints should be exempt from CSRF checks."""
        response = client.post(
            "/login/email",
            json={"email": "test@test.com", "password": "password"},
        )
        # Should NOT be 403 CSRF error
        assert response.json().get("detail") != "CSRF token missing or invalid"

    def test_signup_path_exempt(self, client):
        """Signup endpoints should be exempt from CSRF checks."""
        response = client.post(
            "/signup/email",
            json={
                "firstName": "Test",
                "lastName": "User",
                "email": "test@test.com",
                "password": "password123",
            },
        )
        assert response.json().get("detail") != "CSRF token missing or invalid"

    # ---- DELETE and PATCH methods ----

    def test_delete_without_csrf_is_blocked(self, client):
        """DELETE without CSRF header/cookie must return 403."""
        response = client.delete("/graphs/test-graph")
        assert response.status_code == 403
        assert response.json()["detail"] == "CSRF token missing or invalid"

    def test_delete_with_valid_csrf_passes(self, client):
        """DELETE with matching cookie + header must pass CSRF check."""
        get_resp = client.get("/auth-status")
        csrf = get_resp.cookies["csrf_token"]

        response = client.delete(
            "/graphs/test-graph",
            headers={"X-CSRF-Token": csrf},
            cookies={"csrf_token": csrf},
        )
        assert response.status_code != 403

    def test_patch_without_csrf_is_blocked(self, client):
        """PATCH without CSRF header/cookie must return 403."""
        response = client.patch("/graphs/test-graph")
        assert response.status_code == 403
        assert response.json()["detail"] == "CSRF token missing or invalid"

    def test_patch_with_valid_csrf_passes(self, client):
        """PATCH with matching cookie + header must pass CSRF check."""
        get_resp = client.get("/auth-status")
        csrf = get_resp.cookies["csrf_token"]

        response = client.patch(
            "/graphs/test-graph",
            headers={"X-CSRF-Token": csrf},
            cookies={"csrf_token": csrf},
        )
        assert response.status_code != 403

    # ---- Secure flag based on scheme ----

    def test_csrf_cookie_not_secure_on_http(self, client):
        """Over plain HTTP the csrf_token cookie must NOT have the Secure flag."""
        response = client.get("/auth-status")
        set_cookie = response.headers.get("set-cookie", "")
        assert "csrf_token=" in set_cookie
        assert "; secure" not in set_cookie.lower()
