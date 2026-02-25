"""
Test that the RequestValidationError handler returns a generic 400
for the SPA catch-all route while preserving useful 422 responses
for legitimate API validation errors.
"""
import pytest
from fastapi import FastAPI, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from api.index import app


class TestValidationErrorHandler:
    """Test the global RequestValidationError handler."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return TestClient(app, raise_server_exceptions=False)

    def test_catch_all_route_returns_generic_400(self, client):
        """The SPA catch-all route should return a clean 400."""
        response = client.get("/some/random/path")
        assert response.status_code == 400
        body = response.json()
        assert body == {"detail": "Bad request"}
        assert "loc" not in str(body)
        assert "msg" not in str(body)

    def test_api_validation_error_returns_422_with_details(self):
        """API routes should still return 422 with field-level details."""
        test_app = FastAPI()

        @test_app.get("/test-typed")
        async def _typed_endpoint(count: int = Query(...)):
            return {"count": count}

        @test_app.exception_handler(RequestValidationError)
        async def _handler(
            _request, exc  # pylint: disable=unused-argument
        ):
            for error in exc.errors():
                if error.get("loc") == ("query", "_full_path"):
                    return JSONResponse(
                        status_code=400, content={"detail": "Bad request"}
                    )
            return JSONResponse(status_code=422, content={"detail": exc.errors()})

        client = TestClient(test_app, raise_server_exceptions=False)
        response = client.get("/test-typed", params={"count": "not-a-number"})
        assert response.status_code == 422
        body = response.json()
        assert isinstance(body["detail"], list)
        assert any("count" in str(err.get("loc", "")) for err in body["detail"])
