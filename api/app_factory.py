"""Application factory for the text2sql FastAPI app."""

import os
import secrets

from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from api.logging_config import get_logger
from api.routes.auth import auth_router, init_auth
from api.routes.graphs import graphs_router
from api.routes.database import database_router

# Load environment variables from .env file
load_dotenv()
logger = get_logger(__name__)


class SecurityMiddleware(BaseHTTPMiddleware):
    """Middleware for security checks including static file access"""

    STATIC_PREFIX = '/static/'

    async def dispatch(self, request: Request, call_next):
        # Block directory access in static files
        if request.url.path.startswith(self.STATIC_PREFIX):
            # Remove /static/ prefix to get the actual path
            filename = request.url.path[len(self.STATIC_PREFIX):]
            # Basic security check for directory traversal
            if not filename or '../' in filename or filename.endswith('/'):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Forbidden"}
                )

        response = await call_next(request)
        return response


def create_app():
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="QueryWeaver",
        description=(
            "Text2SQL with "
            "Graph-Powered Schema Understanding"
        ),
    )

    # Get secret key for sessions
    secret_key = os.getenv("FASTAPI_SECRET_KEY")
    if not secret_key:
        secret_key = secrets.token_hex(32)
        logger.warning("FASTAPI_SECRET_KEY not set, using generated key. Set this in production!")

    # Add session middleware with explicit settings to ensure OAuth state persists
    app.add_middleware(
        SessionMiddleware,
        secret_key=secret_key,
        session_cookie="qw_session",
        same_site="lax",  # allow top-level OAuth GET redirects to send cookies
        https_only=False,  # allow http on localhost in development
        max_age=60 * 60 * 24 * 14,  # 14 days - measured by seconds
    )

    # Add security middleware
    app.add_middleware(SecurityMiddleware)

    # Mount static files
    static_path = os.path.join(os.path.dirname(__file__), "../app/public")
    if os.path.exists(static_path):
        app.mount("/static", StaticFiles(directory=static_path), name="static")

    # Initialize authentication (OAuth and sessions)
    init_auth(app)

    # Include routers
    app.include_router(auth_router)
    app.include_router(graphs_router, prefix="/graphs")
    app.include_router(database_router)

    @app.exception_handler(Exception)
    async def handle_oauth_error(request: Request, exc: Exception):
        """Handle OAuth-related errors gracefully"""
        # Check if it's an OAuth-related error
        exc_text = str(exc)
        exc_text_lower = exc_text.lower()
        if "token" in exc_text_lower or "oauth" in exc_text_lower:
            logger.warning("OAuth error occurred", error=exc_text)
            request.session.clear()
            return RedirectResponse(url="/", status_code=302)

        # If it's an HTTPException, re-raise so FastAPI handles it properly
        if isinstance(exc, HTTPException):
            raise exc

        # For other errors, let them bubble up
        raise exc

    # Add template globals
    @app.middleware("http")
    async def add_template_globals(request: Request, call_next):
        request.state.google_tag_manager_id = os.getenv("GOOGLE_TAG_MANAGER_ID")
        response = await call_next(request)
        return response

    return app
