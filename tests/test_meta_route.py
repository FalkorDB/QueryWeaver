"""Tests for the public /version metadata route."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.meta import meta_router, app_version


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(meta_router)
    return TestClient(app)


def test_version_returns_200_with_name_and_version():
    response = _client().get("/version")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "queryweaver"
    assert isinstance(body["version"], str)
    assert body["version"]  # non-empty


def test_version_matches_app_version():
    body = _client().get("/version").json()
    assert body["version"] == app_version()


def test_version_is_unauthenticated():
    # No session cookie or API token supplied — must still succeed.
    response = _client().get("/version")
    assert response.status_code == 200
