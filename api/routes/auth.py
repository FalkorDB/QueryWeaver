"""Authentication routes for the text2sql API."""
# pylint: disable=all

import hashlib
import hmac
import logging
import os
import re
import secrets

from pathlib import Path
from urllib.parse import urljoin

from authlib.integrations.starlette_client import OAuth

from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, FileSystemBytecodeCache, select_autoescape
from starlette.config import Config
from pydantic import BaseModel

from api.auth.browser_session import (
    clear_browser_session,
    establish_browser_session,
    is_provisioned,
    mark_provisioned,
    read_browser_session,
)
from api.auth.user_management import delete_user_token, ensure_user_in_organizations, validate_user
from api.config import ORGANIZATIONS_GRAPH
from api.core.errors import AuthBackendUnavailableError
from api.extensions import db

# Import GENERAL_PREFIX from graphs route
GENERAL_PREFIX = os.getenv("GENERAL_PREFIX")

# Router
auth_router = APIRouter(tags=["Authentication"])
TEMPLATES_DIR = str((Path(__file__).resolve().parents[1] / "../app/templates").resolve())

TEMPLATES_CACHE_DIR = "/tmp/jinja_cache"
os.makedirs(TEMPLATES_CACHE_DIR, exist_ok=True)  # ✅ ensures the folder exists

templates = Jinja2Templates(
    env=Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        bytecode_cache=FileSystemBytecodeCache(
            directory=TEMPLATES_CACHE_DIR,
            pattern="%s.cache"
        ),
        auto_reload=True,
        autoescape=select_autoescape(['html', 'xml', 'j2'])
    )
)

templates.env.globals["google_tag_manager_id"] = os.getenv("GOOGLE_TAG_MANAGER_ID")

GOOGLE_AUTH = bool(os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET"))
GITHUB_AUTH = bool(os.getenv("GITHUB_CLIENT_ID") and os.getenv("GITHUB_CLIENT_SECRET"))
EMAIL_AUTH = bool(os.getenv("EMAIL_AUTH_ENABLED", "").lower() in ["true", "1", "yes", "on"])

# ---- Authentication Configuration Helpers ----
def _is_email_auth_enabled() -> bool:
    """Check if email authentication is enabled via environment variable."""
    return EMAIL_AUTH or not (GOOGLE_AUTH or GITHUB_AUTH)

def _is_google_auth_enabled() -> bool:
    """Check if Google OAuth is enabled via environment variables."""
    return GOOGLE_AUTH

def _is_github_auth_enabled() -> bool:
    """Check if GitHub OAuth is enabled via environment variables."""
    return GITHUB_AUTH

def _get_auth_config() -> dict:
    """Get authentication configuration for templates."""
    return {
        "email_auth_enabled": _is_email_auth_enabled(),
        "google_auth_enabled": _is_google_auth_enabled(),
        "github_auth_enabled": _is_github_auth_enabled(),
    }

# Data models for email authentication
class EmailLoginRequest(BaseModel):
    """_summary_

    Args:
        BaseModel (_type_): _description_
    """
    email: str
    password: str

class EmailSignupRequest(BaseModel):
    """_summary_

    Args:
        BaseModel (_type_): _description_
    """
    firstName: str
    lastName: str
    email: str
    password: str

# ---- Password utilities ----
def _hash_password(password: str) -> str:
    """Hash a password using PBKDF2 with a random salt."""
    salt = os.urandom(32)
    password_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return (salt + password_hash).hex()

def _verify_password(password: str, stored_password_hex: str) -> bool:
    """Verify a password against its hash using constant-time comparison."""
    try:
        stored_password = bytes.fromhex(stored_password_hex)
        salt = stored_password[:32]
        stored_hash = stored_password[32:]

        password_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)

        return hmac.compare_digest(password_hash, stored_hash)
    except (ValueError, TypeError):
        return False

def _sanitize_for_log(value: str) -> str:
    """Sanitize user input for logging by removing newlines and carriage returns."""
    if not isinstance(value, str):
        try:
            value = str(value)
        except Exception:  # pylint: disable=broad-exception-caught
            # Defensive: a custom __str__ may raise. Log sanitisation must never
            # be fatal to the auth flow, so fall back to a safe placeholder.
            return '<unprintable>'
    # Strip carriage returns first, then newlines. The final ``.replace('\n', '')``
    # must be the outermost (returned) call so that CodeQL's log-injection sanitizer
    # (ReplaceLineBreaksSanitizer, which only recognises a first argument of "\n" or
    # "\r\n") treats the returned value as sanitised.
    return value.replace('\r', '').replace('\n', '')

def _validate_email(email: str) -> bool:
    """Basic email validation."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

async def _set_mail_hash(email: str, password_hash: str) -> bool:
    """Set email hash for the user in the database."""
    # Sanitized up front so the error path below can log it too.
    safe_email = _sanitize_for_log(email)
    try:
        organizations_graph = db.select_graph(ORGANIZATIONS_GRAPH)

        # Create new email identity and user
        create_query = """
        MERGE (i:Identity {
            provider_user_id: $email,
            email: $email
        })
        SET i.password_hash = $password_hash
        RETURN i
        """

        result = await organizations_graph.query(create_query, {
            "email": email,
            "password_hash": password_hash,
        })

        if result.result_set:
            return True
        else:
            logging.error("Failed to set email hash for user: %s", safe_email)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail="Internal server error"
            )

    except Exception as e:
        logging.error("Error setting email hash for user %s: %s", safe_email, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Internal server error"
        )

async def _email_account_exists(email: str) -> bool:
    """Return True if an account already exists for the given email (any provider).

    Exceptions are intentionally not swallowed so callers fail closed (treat the
    account as existing / abort the signup) rather than issuing a session token.
    """
    organizations_graph = db.select_graph(ORGANIZATIONS_GRAPH)
    # Use a UNION of two label-scoped lookups so each side hits the (label, email)
    # index and short-circuits with LIMIT 1. This avoids both a full-graph scan and
    # the Cartesian product that two chained OPTIONAL MATCH clauses would produce.
    query = """
    MATCH (u:User {email: $email}) RETURN u AS account_node LIMIT 1
    UNION
    MATCH (i:Identity {email: $email}) RETURN i AS account_node LIMIT 1
    """
    result = await organizations_graph.query(query, {"email": email})
    return bool(result.result_set)

def _is_request_secure(request: Request) -> bool:
    """Determine if the request is secure (HTTPS)."""
    
    # Check X-Forwarded-Proto first (proxy-aware)
    forwarded_proto = request.headers.get("x-forwarded-proto")
    if forwarded_proto:
        return forwarded_proto == "https"
    
    # Fallback to request URL scheme
    return request.url.scheme == "https"

async def _authenticate_email_user(email: str, password: str):
    """Authenticate an email user."""
    try:
        organizations_graph = db.select_graph(ORGANIZATIONS_GRAPH)

        # Find user by email
        query = """
        MATCH (i:Identity {provider: 'email', email: $email})-[:AUTHENTICATES]->(u:User)
        RETURN i, u
        """

        result = await organizations_graph.query(query, {"email": email})

        if not result.result_set:
            return False, "Invalid email or password"

        identity = result.result_set[0][0]
        user = result.result_set[0][1]

        # Verify password - access Node properties correctly
        stored_password_hash = identity.properties.get('password_hash')
        if not stored_password_hash or not _verify_password(password, stored_password_hash):
            return False, "Invalid email or password"

        # Update last login
        update_query = """
        MATCH (i:Identity {provider: 'email', email: $email})
        SET i.last_login = timestamp()
        """
        await organizations_graph.query(update_query, {"email": email})

        logging.info("EMAIL USER AUTHENTICATED: email=%r", _sanitize_for_log(email))
        return True, {"identity": identity, "user": user}

    except Exception as e:
        logging.error("Error authenticating email user: %s", e)
        # Not "wrong password" — we never got to check. Surfaced separately so the
        # caller can answer 503 instead of accusing the user of bad credentials.
        raise AuthBackendUnavailableError(str(e)) from e


async def _complete_login(request: Request, provider: str, user_data: dict) -> str:
    """Finish a successful login and return the API token to hand to the browser.

    Order matters: the signed session cookie *is* the browser's credential, so it
    is established regardless of whether the Organizations-graph write lands. A
    FalkorDB outage during login therefore costs the user their stored profile
    (retried later from ``/auth-status``), not their ability to log in.
    """
    email = user_data.get("email")
    if not email:
        # Every identity in the system is keyed by email; without one there is
        # nothing to log the user in as. Fail loudly instead of half-succeeding.
        logging.warning("No email address available from %s", provider)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No email address available from {provider}",
        )

    handler = getattr(request.app.state, "callback_handler", None)
    if handler is None:
        logging.error("OAuth callback handler not registered in app state")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication handler not configured",
        )

    api_token = secrets.token_urlsafe(32)  # ~43 chars, hard to guess
    provisioned = bool(await handler(provider, user_data, api_token))
    if not provisioned:
        logging.warning(
            "Logged in via %s from the session cookie alone; the user store write did not land",
            provider,
        )

    establish_browser_session(
        request,
        email=email,
        name=user_data.get("name"),
        picture=user_data.get("picture"),
        provider=provider,
        provider_user_id=user_data.get("id"),
        provisioned=provisioned,
    )
    return api_token


# ---- Email Authentication Routes ----
@auth_router.post("/signup/email")
async def email_signup(request: Request, signup_data: EmailSignupRequest) -> JSONResponse:
    """Handle email/password user registration."""
    try:
        # Check if email authentication is enabled
        if not _is_email_auth_enabled():
            return JSONResponse(
                {"success": False, "error": "Email authentication is not enabled"},
                status_code=status.HTTP_403_FORBIDDEN
            )

        # Validate required fields
        if not all([signup_data.firstName, signup_data.lastName,
                    signup_data.email, signup_data.password]):
            return JSONResponse(
                {"success": False, "error": "All fields are required"},
                status_code=status.HTTP_400_BAD_REQUEST
            )

        first_name = signup_data.firstName.strip()
        last_name = signup_data.lastName.strip()
        email = signup_data.email.strip().lower()
        password = signup_data.password

        # Validate email format
        if not _validate_email(email):
            return JSONResponse(
                {"success": False, "error": "Invalid email format"},
                status_code=status.HTTP_400_BAD_REQUEST
            )

        # Validate password strength
        if len(password) < 8:
            return JSONResponse(
                {"success": False, "error": "Password must be at least 8 characters long"},
                status_code=status.HTTP_400_BAD_REQUEST
            )

        # Reject signup when an account already exists for this email (under ANY
        # provider). Issuing a session token for an existing account here would let
        # an attacker take over that account without knowing its password
        # (CVE-2026-10130, authentication bypass via signup token issuance).
        if await _email_account_exists(email):
            logging.info("Signup attempt for existing account: %s", _sanitize_for_log(email))
            return JSONResponse(
                {"success": False, "error": "An account with this email already exists"},
                status_code=status.HTTP_409_CONFLICT
            )

        api_token = secrets.token_urlsafe(32)
        # Create organization association
        success, user_info = await ensure_user_in_organizations(email, email,
                                            f"{first_name} {last_name}", "email", api_token)

        if not (success and user_info and user_info.get("new_identity")):
            # Creation failed (e.g. DB error) or raced with a concurrent signup.
            # Never issue a token in this case; clean up any token that was linked.
            logging.error("Failed to create new user during signup: %s",
                          _sanitize_for_log(email))
            await delete_user_token(api_token)
            return JSONResponse(
                {"success": False, "error": "Registration failed"},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        logging.info("New user created: %s", _sanitize_for_log(email))

        # Hash password
        password_hash = _hash_password(password)

        # Set email hash
        await _set_mail_hash(email, password_hash)

        logging.info("User registration successful: %s", _sanitize_for_log(email))

        establish_browser_session(
            request,
            email=email,
            name=f"{first_name} {last_name}",
            provider="email",
            provider_user_id=email,
            provisioned=True,
        )

        response = JSONResponse({
            "success": True,
        }, status_code=201)
        response.set_cookie(
            key="api_token",
            value=api_token,
            httponly=True,
            secure=_is_request_secure(request)
        )
        return response

    except Exception as e:
        logging.error("Signup error: %s", e)
        return JSONResponse(
            {"success": False, "error": "Registration failed"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@auth_router.post("/login/email")
async def email_login(request: Request, login_data: EmailLoginRequest) -> JSONResponse:
    """Handle email/password user login."""
    try:
        # Check if email authentication is enabled
        if not _is_email_auth_enabled():
            return JSONResponse(
                {"success": False, "error": "Email authentication is not enabled"},
                status_code=status.HTTP_403_FORBIDDEN
            )

        # Validate required fields
        if not login_data.email or not login_data.password:
            return JSONResponse(
                {"success": False, "error": "Email and password are required"},
                status_code=status.HTTP_400_BAD_REQUEST
            )

        email = login_data.email.strip().lower()
        password = login_data.password

        # Validate email format
        if not _validate_email(email):
            return JSONResponse(
                {"success": False, "error": "Invalid email format"},
                status_code=status.HTTP_400_BAD_REQUEST
            )

        # Authenticate user
        try:
            success, result = await _authenticate_email_user(email, password)
        except AuthBackendUnavailableError:
            return JSONResponse(
                {"success": False,
                 "error": "Authentication service temporarily unavailable - please retry"},
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        if not success:
            return JSONResponse(
                {"success": False, "error": result},
                status_code=status.HTTP_401_UNAUTHORIZED
            )

        # Set session data - result is a dict when success is True
        if isinstance(result, dict):
            identity_node = result.get("identity")

            identity_props = (
                identity_node.properties
                if identity_node and hasattr(identity_node, "properties")
                else {}
            )

            user_data = {
                'id': identity_props.get("provider_user_id", email),
                'email': identity_props.get('email', email),
                'name': identity_props.get('name', ''),
                'picture': identity_props.get('picture', ''),
            }

            api_token = await _complete_login(request, 'email', user_data)
            response = JSONResponse({"success": True}, status_code=200)
            response.set_cookie(
                key="api_token",
                value=api_token,
                httponly=True,
                secure=_is_request_secure(request)
            )
            return response

        return JSONResponse(
            {"success": False, "error": "Authentication failed"},
            status_code=status.HTTP_401_UNAUTHORIZED
        )
    except Exception as e:
        logging.error("Login error: %s", e)
        return JSONResponse(
            {"success": False, "error": "Login failed"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# ---- Helpers ----
def _get_provider_client(request: Request, provider: str):
    """Get an OAuth provider client from app.state.oauth"""
    oauth = getattr(request.app.state, "oauth", None)
    if not oauth:
        raise HTTPException(status_code=500, detail="OAuth not configured")

    client = getattr(oauth, provider, None)
    if not client:
        raise HTTPException(status_code=500, detail=f"OAuth provider {provider} not configured")
    return client

def _build_callback_url(request: Request, path: str) -> str:
    """Build absolute callback URL, honoring OAUTH_BASE_URL if provided."""
    base_override = os.getenv("OAUTH_BASE_URL")
    base = base_override if base_override else str(request.base_url)
    if not base.endswith("/"):
        base += "/"
    return urljoin(base, path.lstrip("/"))

# ---- Routes ----
@auth_router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def home() -> HTMLResponse:
    """
    Serve the React SPA (Single Page Application).
    The React app handles authentication state via /auth-status endpoint.
    """
    from fastapi.responses import FileResponse
    
    # Serve the React build's index.html
    dist_path = Path(__file__).resolve().parents[1] / "../app/dist"
    index_path = dist_path / "index.html"
    
    if not index_path.exists():
        return HTMLResponse(
            content="""
            <html>
                <head><title>QueryWeaver - Build Required</title></head>
                <body style="font-family: system-ui; padding: 2rem; max-width: 800px; margin: 0 auto;">
                    <h1>🛠️ Frontend Not Built</h1>
                    <p>Please build the React frontend first:</p>
                    <pre style="background: #f5f5f5; padding: 1rem; border-radius: 4px;">cd app && npm run build</pre>
                    <p>Or run in development mode (recommended for development):</p>
                    <pre style="background: #f5f5f5; padding: 1rem; border-radius: 4px;">cd app && npm run dev</pre>
                    <p><small>The dev server will run on <a href="http://localhost:8080">http://localhost:8080</a> with hot reload.</small></p>
                </body>
            </html>
            """,
            status_code=503
        )
    
    return FileResponse(index_path)

@auth_router.get("/login/google", name="google.login", response_class=RedirectResponse)
async def login_google(request: Request) -> RedirectResponse:
    """Initiate Google OAuth login flow.

    Args:
        request (Request): The incoming request.

    Returns:
        RedirectResponse: The redirect response to the Google OAuth endpoint.
    """

    # Check if Google auth is enabled
    if not _is_google_auth_enabled():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Google authentication is not configured"
        )

    google = _get_provider_client(request, "google")
    redirect_uri = _build_callback_url(request, "login/google/authorized")

    # Helpful hint if localhost vs 127.0.0.1 mismatch is likely
    if not os.getenv("OAUTH_BASE_URL") and "127.0.0.1" in str(request.base_url):
        logging.warning(
            "OAUTH_BASE_URL not set and base URL is 127.0.0.1; "
            "if your Google OAuth app uses 'http://localhost:5000', "
            "set OAUTH_BASE_URL=http://localhost:5000 to avoid redirect_uri mismatch."
        )

    return await google.authorize_redirect(request, redirect_uri)


@auth_router.get("/login/google/authorized", response_class=RedirectResponse)
async def google_authorized(request: Request) -> RedirectResponse:
    """
    Handle Google OAuth callback and user authorization.

    Args:
        request (Request): The incoming request.

    Returns:
        RedirectResponse: The redirect response after handling the callback.
    """
    # Check if Google auth is enabled
    if not _is_google_auth_enabled():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Google authentication is not configured"
        )

    try:
        google = _get_provider_client(request, "google")
        token = await google.authorize_access_token(request)
        resp = await google.get("userinfo", token=token)
        if resp.status_code != 200:
            logging.warning("Failed to retrieve user info from Google")
            raise HTTPException(status_code=400, detail="Failed to get user info from Google")

        user_info = resp.json()

        if user_info:
            user_data = {
                'id': user_info.get('id') or user_info.get('sub'),
                'email': user_info.get('email'),
                'name': user_info.get('name'),
                'picture': user_info.get('picture'),
            }

            # Call the registered Google callback handler if it exists to store user data.
            api_token = await _complete_login(request, 'google', user_data)

            redirect = RedirectResponse(url="/", status_code=302)
            redirect.set_cookie(
                key="api_token",
                value=api_token,
                httponly=True,
                secure=_is_request_secure(request)
            )

            return redirect

        # If we reach here, user_info was falsy
        logging.warning("No user info received from Google OAuth")
        raise HTTPException(status_code=400, detail="Failed to get user info from Google")

    except Exception as e:
        logging.error("Google OAuth authentication failed: %s", str(e))  # nosemgrep
        raise HTTPException(status_code=400, detail="Authentication failed") from e


@auth_router.get("/login/google/callback", response_class=RedirectResponse)
async def google_callback_compat(request: Request) -> RedirectResponse:
    """Handle Google OAuth callback redirect for compatibility."""
    qs = f"?{request.url.query}" if request.url.query else ""
    redirect = f"/login/google/authorized{qs}"
    return RedirectResponse(url=redirect, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@auth_router.get("/login/github",  name="github.login", response_class=RedirectResponse)
async def login_github(request: Request) -> RedirectResponse:
    """Handle GitHub OAuth login redirect."""
    # Check if GitHub auth is enabled
    if not _is_github_auth_enabled():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="GitHub authentication is not configured"
        )

    github = _get_provider_client(request, "github")
    redirect_uri = _build_callback_url(request, "login/github/authorized")

    # Helpful hint if localhost vs 127.0.0.1 mismatch is likely
    if not os.getenv("OAUTH_BASE_URL") and "127.0.0.1" in str(request.base_url):
        logging.warning(
            "OAUTH_BASE_URL not set and base URL is 127.0.0.1; "
            "if your GitHub OAuth app uses 'http://localhost:5000', "
            "set OAUTH_BASE_URL=http://localhost:5000 to avoid redirect_uri mismatch."
        )

    return await github.authorize_redirect(request, redirect_uri)


@auth_router.get("/login/github/authorized", response_class=RedirectResponse)
async def github_authorized(request: Request) -> RedirectResponse:
    """Handle GitHub OAuth authorization callback."""
    # Check if GitHub auth is enabled
    if not _is_github_auth_enabled():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="GitHub authentication is not configured"
        )
    try:
        github = _get_provider_client(request, "github")
        token = await github.authorize_access_token(request)

        # Fetch GitHub user info
        resp = await github.get("user", token=token)
        if resp.status_code != 200:
            logging.error("Failed to fetch GitHub user info: %s", resp.text)  # nosemgrep
            return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

        user_info = resp.json()

        # Get user email if not public
        email = user_info.get("email")
        if not email:
            # Try to get primary email from emails endpoint
            email_resp = await github.get("user/emails", token=token)
            if email_resp.status_code == 200:
                emails = email_resp.json()
                for email_obj in emails:
                    if email_obj.get("primary"):
                        email = email_obj.get("email")
                        break

        if user_info:
            user_data = {
                'id': user_info.get('id'),
                'email': email,
                'name': user_info.get('name'),
                'picture': user_info.get('avatar_url'),
            }

            # Call the registered GitHub callback handler if it exists to store user data.
            api_token = await _complete_login(request, 'github', user_data)

            redirect = RedirectResponse(url="/", status_code=302)
            redirect.set_cookie(
                key="api_token",
                value=api_token,
                httponly=True,
                secure=_is_request_secure(request)
            )

            return redirect

        # If we reach here, user_info was falsy
        logging.warning("No user info received from GitHub OAuth")
        raise HTTPException(status_code=400, detail="Failed to get user info from Github")

    except Exception as e:
        logging.error("GitHub OAuth authentication failed: %s", str(e))  # nosemgrep
        raise HTTPException(status_code=400, detail="Authentication failed") from e


@auth_router.get("/login/github/callback", response_class=RedirectResponse)
async def github_callback_compat(request: Request) -> RedirectResponse:
    """Handle GitHub OAuth callback redirect for compatibility."""
    qs = f"?{request.url.query}" if request.url.query else ""
    redirect = f"/login/github/authorized{qs}"
    return RedirectResponse(url=redirect, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@auth_router.get("/auth-status")
async def auth_status(request: Request) -> JSONResponse:
    """Check authentication status for the React app.

    Returns:
        JSONResponse: Authentication status with user info if authenticated
    """
    try:
        user_info, is_authenticated = await validate_user(request)
    except AuthBackendUnavailableError:
        # Only reachable for an explicitly supplied API token; a browser login
        # never consults the database.
        return JSONResponse(
            content={"authenticated": False,
                     "error": "Authentication service temporarily unavailable"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    if is_authenticated and user_info:
        response = JSONResponse(
            content={
                "authenticated": True,
                "user": {
                    # Falls back to the email so the id is always a usable string
                    # for clients, even for database-backed API tokens.
                    "id": str(user_info.get("id") or user_info.get("email")),
                    "email": user_info.get("email"),
                    "name": user_info.get("name"),
                    "picture": user_info.get("picture"),
                    "provider": user_info.get("provider")
                }
            }
        )
        await _retry_pending_provisioning(request, response)
        return response

    # Not authenticated - return 200 with authenticated: false
    # This is NOT an error - unauthenticated users can still use the app
    return JSONResponse(
        content={"authenticated": False},
        status_code=200
    )


async def _retry_pending_provisioning(request: Request, response: JSONResponse) -> None:
    """Finish a login whose Organizations-graph write failed at the time.

    Logging in no longer needs FalkorDB, so a user can be signed in without a
    stored ``User``/``Identity`` record. This retries that write on the next
    status poll and is strictly best-effort: it must never change the
    authentication verdict.
    """
    if is_provisioned(request):
        return

    session_user = read_browser_session(request)
    if not session_user:
        return

    handler = getattr(request.app.state, "callback_handler", None)
    if handler is None:
        return

    api_token = secrets.token_urlsafe(32)
    user_data = {
        'id': session_user.get("id") or session_user.get("email"),
        'email': session_user.get("email"),
        'name': session_user.get("name"),
        'picture': session_user.get("picture"),
    }
    try:
        succeeded = bool(await handler(session_user.get("provider"), user_data, api_token))
    except Exception as e:  # pylint: disable=broad-exception-caught
        logging.warning("Deferred user provisioning failed: %s", e)
        return

    if succeeded:
        mark_provisioned(request)
        response.set_cookie(
            key="api_token",
            value=api_token,
            httponly=True,
            secure=_is_request_secure(request)
        )


@auth_router.get("/logout")
@auth_router.post("/logout")
async def logout(request: Request):
    """Handle user logout and delete session cookies.

    Supports both GET and POST methods for backward compatibility:
    - GET: For direct navigation (bookmarks, links, old clients)
    - POST: For programmatic logout from the app
    """
    # The browser session is the primary credential, so it must go first --
    # otherwise deleting the api_token cookie would leave the user logged in.
    clear_browser_session(request)

    # For GET requests, redirect to home page
    if request.method == "GET":
        response = RedirectResponse(url="/", status_code=302)
        api_token = request.cookies.get("api_token")
        if api_token:
            response.delete_cookie("api_token")
            await delete_user_token(api_token)
        return response

    # For POST requests, return JSON
    response = JSONResponse(content={"success": True})
    api_token = request.cookies.get("api_token")
    if api_token:
        response.delete_cookie("api_token")
        await delete_user_token(api_token)
    return response

# ---- Hook for app factory ----
def init_auth(app):
    """Initialize OAuth and sessions for the app."""

    config = Config(environ=os.environ)
    oauth = OAuth(config)

    # Only register Google OAuth if credentials are available
    if _is_google_auth_enabled():
        oauth.register(
            name="google",
            client_id=os.getenv("GOOGLE_CLIENT_ID"),
            client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            api_base_url="https://openidconnect.googleapis.com/v1/",
            client_kwargs={"scope": "openid email profile"},
        )
        logging.info("Google OAuth initialized successfully")
    else:
        logging.info("Google OAuth not configured - skipping registration")

    # Only register GitHub OAuth if credentials are available
    if _is_github_auth_enabled():
        oauth.register(
            name="github",
            client_id=os.getenv("GITHUB_CLIENT_ID"),
            client_secret=os.getenv("GITHUB_CLIENT_SECRET"),
            access_token_url="https://github.com/login/oauth/access_token",
            authorize_url="https://github.com/login/oauth/authorize",
            api_base_url="https://api.github.com/",
            client_kwargs={"scope": "user:email"},
        )
        logging.info("GitHub OAuth initialized successfully")
    else:
        logging.info("GitHub OAuth not configured - skipping registration")

    app.state.oauth = oauth
