"""Application factory for the text2sql FastAPI app."""

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi_mcp import FastApiMCP
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from api.auth.oauth_handlers import setup_oauth_handlers
from api.auth.user_management import SECRET_KEY
from api.routes.auth import auth_router, init_auth
from api.routes.graphs import graphs_router
from api.routes.database import database_router
from api.routes.tokens import tokens_router

# Load environment variables from .env file
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class SecurityMiddleware(BaseHTTPMiddleware):  # pylint: disable=too-few-public-methods
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

    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

    # Add session middleware with explicit settings to ensure OAuth state persists
    # Detect if we're running on HTTPS (staging/production) vs HTTP (development)
    app_env = os.getenv("APP_ENV", "").lower()
    if app_env in ("production", "staging"):
        is_https = True
    else:
        is_https = False

    app.add_middleware(
        SessionMiddleware,
        secret_key=SECRET_KEY,
        session_cookie="qw_session",
        same_site="lax",  # allow top-level OAuth GET redirects to send cookies
        https_only=is_https,  # True for HTTPS environments (staging/prod), False for HTTP dev
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
    app.include_router(tokens_router, prefix="/api/tokens")

    # app.include_router(mcp_router, prefix="/mcp")
    setup_oauth_handlers(app, app.state.oauth)

    # Control MCP endpoints via environment variable DISABLE_MCP
    # Default: MCP is enabled unless DISABLE_MCP is set to true
    disable_mcp = os.getenv("DISABLE_MCP", "false").lower() in ("1", "true", "yes")
    if disable_mcp:
        logging.info("MCP endpoints disabled via DISABLE_MCP environment variable")
    else:
        mcp = FastApiMCP(app,
                         name="queryweaver",
                         description="QueryWeaver MCP API, provides Text2SQL capabilities",
                         include_operations=["list_databases",
                                             "connect_database",
                                             "database_schema",
                                             "query_database"]
                         )

        mcp.mount_http()

    @app.exception_handler(Exception)
    async def handle_oauth_error(_request: Request, exc: Exception):
        """Handle OAuth-related errors gracefully"""
        # Check if it's an OAuth-related error
        # NOTE: This catches basic token/oauth errors - needs refinement for production
        if "token" in str(exc).lower() or "oauth" in str(exc).lower():
            logging.warning("OAuth error occurred: %s", exc)
            return RedirectResponse(url="/", status_code=302)

        # If it's an HTTPException, re-raise so FastAPI handles it properly
        if isinstance(exc, HTTPException):
            raise exc

        # For other errors, let them bubble up
        raise exc

    return app
