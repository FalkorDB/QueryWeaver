"""Application factory for the text2sql FastAPI app."""

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from fastmcp import FastMCP
from fastmcp.server.openapi import MCPType, RouteMap

from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from api.auth.oauth_handlers import setup_oauth_handlers
from api.auth.user_management import SECRET_KEY
from api.routes.auth import auth_router, init_auth
from api.routes.graphs import graphs_router
from api.routes.database import database_router
from api.routes.tokens import tokens_router

# Load environment variables from .env file
load_dotenv()
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class SecurityMiddleware(BaseHTTPMiddleware):  # pylint: disable=too-few-public-methods
    """Middleware for security checks including static file access"""

    STATIC_PREFIX = "/static/"

    async def dispatch(self, request: Request, call_next):
        # Block directory access in static files
        if request.url.path.startswith(self.STATIC_PREFIX):
            # Remove /static/ prefix to get the actual path
            filename = request.url.path[len(self.STATIC_PREFIX) :]
            # Basic security check for directory traversal
            if not filename or "../" in filename or filename.endswith("/"):
                return JSONResponse(status_code=403, content={"detail": "Forbidden"})

        response = await call_next(request)
        return response


def create_app():
    """Create and configure the FastAPI application."""

    # Create the FastAPI app instance just to set the o routes
    # Will be merged with MCP app later if MCP is enabled
    app = FastAPI(
        title="QueryWeaver"
    )

    # Include routers
    app.include_router(auth_router)
    app.include_router(graphs_router, prefix="/graphs")
    app.include_router(database_router)
    app.include_router(tokens_router, prefix="/tokens")



    # Control MCP endpoints via environment variable DISABLE_MCP
    # Default: MCP is enabled unless DISABLE_MCP is set to true
    disable_mcp = os.getenv("DISABLE_MCP", "false").lower() in ("1", "true", "yes")
    mcp_app = None
    if disable_mcp:
        logging.info("MCP endpoints disabled via DISABLE_MCP environment variable")
        routes=[
            *app.routes,  # Original API routes only
        ]
    else:
        mcp = FastMCP.from_fastapi(
            app=app,
            name="queryweaver",
            route_maps=[
                RouteMap(tags={"mcp_resource"}, mcp_type=MCPType.RESOURCE),
                RouteMap(
                    tags={"mcp_resource_template"},
                    mcp_type=MCPType.RESOURCE_TEMPLATE,
                ),
                RouteMap(tags={"mcp_tool"}, mcp_type=MCPType.TOOL),
                RouteMap(mcp_type=MCPType.EXCLUDE),
            ],
        )
        mcp_app = mcp.http_app(path="/mcp")

        # Combine routes from both apps
        routes = [
            *mcp_app.routes,  # MCP routes
            *app.routes,  # Original API routes
        ]

    # Combine the MCP app and original app
    app = FastAPI(
        title="QueryWeaver",
        description="Text2SQL with Graph-Powered Schema Understanding",
        openapi_tags=[
            {
                "name": "Authentication",
                "description": "User authentication and OAuth operations",
            },
            {
                "name": "Graphs & Databases",
                "description": "Database schema management and querying",
            },
            {
                "name": "Database Connection",
                "description": "Connect to external databases",
            },
            {
                "name": "API Tokens",
                "description": "Manage API tokens for authentication",
            },
        ],
        routes=routes,
        lifespan=mcp_app.lifespan if mcp_app else None,
    )

    # Add security schemes to OpenAPI after app creation
    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema

        # pylint: disable=import-outside-toplevel
        from fastapi.openapi.utils import get_openapi

        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )

        # Add security schemes
        openapi_schema["components"]["securitySchemes"] = {
            "ApiTokenAuth": {
                "type": "apiKey",
                "in": "cookie",
                "name": "api_token",
                "description": "API token for programmatic access. "
                "Generate via POST /tokens/generate after OAuth login.",
            },
            "SessionAuth": {
                "type": "apiKey",
                "in": "cookie",
                "name": "session",
                "description": "Session cookie for web browsers. "
                "Login via Google/GitHub at /login/google or /login/github.",
            },
        }

        # Add security requirements to protected endpoints
        for _, path_item in openapi_schema["paths"].items():
            for method, operation in path_item.items():
                if method in ["get", "post", "put", "delete", "patch"]:
                    # Check if endpoint has token_required (look for 401 response)
                    if "401" in operation.get("responses", {}):
                        # Use OR logic - user needs EITHER ApiTokenAuth OR
                        # SessionAuth (not both)
                        operation["security"] = [
                            {"ApiTokenAuth": []},  # Option 1: API Token
                            {"SessionAuth": []},  # Option 2: OAuth Session
                        ]

        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi

    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

    app.add_middleware(
        SessionMiddleware,
        secret_key=SECRET_KEY,
        same_site="lax",  # allow top-level OAuth GET redirects to send cookies
        https_only=False,  # True for HTTPS environments (staging/prod), False for HTTP dev
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

    setup_oauth_handlers(app, app.state.oauth)

    @app.exception_handler(Exception)
    async def handle_oauth_error(
        request: Request, exc: Exception
    ):  # pylint: disable=unused-argument
        """Handle OAuth-related errors gracefully"""
        # Check if it's an OAuth-related error
        # TODO check this scenario, pylint: disable=fixme
        if "token" in str(exc).lower() or "oauth" in str(exc).lower():
            logging.warning("OAuth error occurred: %s", exc)
            return RedirectResponse(url="/", status_code=302)

        # If it's an HTTPException, re-raise so FastAPI handles it properly
        if isinstance(exc, HTTPException):
            raise exc

        # For other errors, let them bubble up
        raise exc

    return app
