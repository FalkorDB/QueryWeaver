"""An unreachable backend must read as transient at the HTTP boundary too.

The point of separating the browser login from FalkorDB is that an outage stops
looking like a broken login. That only holds end to end if the routes which do
genuinely need the graph answer "retry" -- a 503 -- rather than a 500 ("we are
broken") or, worst of all, a 401 ("you are logged out"), which sends a perfectly
valid session back to the sign-in screen.
"""

import socket

import redis.exceptions

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

import pytest

from api.core.errors import AuthBackendUnavailableError, TRANSIENT_BACKEND_ERRORS

pytestmark = [pytest.mark.unit]


def _app_with_handlers():
    """Register the same handlers ``create_app`` does, without booting the app."""
    app = FastAPI()

    async def transient(request: Request, exc: Exception):  # pylint: disable=unused-argument
        return JSONResponse(
            {"detail": "Service temporarily unavailable - please retry"}, status_code=503
        )

    async def auth_unavailable(request: Request, exc: Exception):  # pylint: disable=unused-argument
        return JSONResponse(
            {"detail": "Authentication service temporarily unavailable - please retry"},
            status_code=503,
        )

    app.add_exception_handler(AuthBackendUnavailableError, auth_unavailable)
    for transient_error in TRANSIENT_BACKEND_ERRORS:
        app.add_exception_handler(transient_error, transient)

    return app


@pytest.mark.parametrize(
    "error",
    [
        redis.exceptions.ConnectionError("Error 111 connecting to falkordb:6379"),
        redis.exceptions.TimeoutError("timed out"),
        redis.exceptions.BusyLoadingError("loading the dataset in memory"),
        ConnectionRefusedError("nothing listening"),
        socket.gaierror("temporary failure in name resolution"),
    ],
)
def test_transient_backend_faults_are_503(error):
    app = _app_with_handlers()

    @app.get("/boom")
    async def boom():  # pylint: disable=unused-variable
        raise error

    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/boom").status_code == 503


def test_auth_backend_unavailable_is_503():
    app = _app_with_handlers()

    @app.get("/boom")
    async def boom():  # pylint: disable=unused-variable
        raise AuthBackendUnavailableError("down")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")

    assert response.status_code == 503
    assert "Authentication service" in response.json()["detail"]


def test_a_deterministic_fault_is_not_reported_as_transient():
    # A Cypher or schema error will fail identically on every retry. Calling it
    # a 503 tells clients to hammer something that can never succeed.
    app = _app_with_handlers()

    @app.get("/boom")
    async def boom():  # pylint: disable=unused-variable
        raise redis.exceptions.ResponseError("Invalid input 'X': expected a query")

    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/boom").status_code == 500


def test_the_shared_tuple_excludes_deterministic_errors():
    assert not isinstance(
        redis.exceptions.ResponseError("nope"), TRANSIENT_BACKEND_ERRORS
    )
    # BusyLoadingError subclasses redis ConnectionError, so it is covered without
    # being listed: a loading instance is exactly the retry-me case.
    assert isinstance(
        redis.exceptions.BusyLoadingError("loading"), TRANSIENT_BACKEND_ERRORS
    )


@pytest.mark.parametrize(
    "error",
    [
        FileNotFoundError("missing template"),
        PermissionError("cannot read the key file"),
        IsADirectoryError("that is a directory"),
    ],
)
def test_local_os_faults_are_bugs_not_outages(error):
    # These are OSError subclasses too. Listing OSError itself would dress a
    # missing file or a bad permission up as "try again later" and hide it.
    assert not isinstance(error, TRANSIENT_BACKEND_ERRORS)

    app = _app_with_handlers()

    @app.get("/boom")
    async def boom():  # pylint: disable=unused-variable
        raise error

    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/boom").status_code == 500
