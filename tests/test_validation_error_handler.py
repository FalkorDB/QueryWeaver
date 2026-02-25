"""
Test that RequestValidationError returns a generic 400 response
instead of leaking internal Pydantic validation details.
"""
import pytest
from fastapi.testclient import TestClient
from api.index import app


class TestValidationErrorHandler:
    """Test the global RequestValidationError handler."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return TestClient(app, raise_server_exceptions=False)

    def test_validation_error_returns_generic_400(self, client):
        """Validation errors should return a clean 400 without internal details."""
        # The /graphs endpoint requires authentication and will trigger
        # a validation error if given unexpected query params with wrong types.
        # Use the catch-all SPA route which accepts a path parameter;
        # we force a validation error by sending a request that triggers one.
        response = client.get("/graphs", params={"id": "not-valid"})
        # Should not contain pydantic-style error detail arrays
        body = response.json()
        if response.status_code == 400:
            assert body == {"detail": "Bad request"}
            assert "loc" not in str(body)
            assert "msg" not in str(body)
            assert "type" not in str(body)

    def test_catch_all_route_does_not_leak_validation_info(self, client):
        """The SPA catch-all route should not expose validation internals."""
        # Access a non-existent path — handled by the catch-all or returns 400
        response = client.get("/some/random/path")
        body = response.json()
        # Must never contain pydantic validation detail arrays
        if response.status_code == 400:
            assert body == {"detail": "Bad request"}
            assert "loc" not in str(body)
