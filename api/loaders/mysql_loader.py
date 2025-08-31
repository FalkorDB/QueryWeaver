"""Authentication routes for the text2sql API."""

import logging
import os
import secrets
from pathlib import Path
from urllib.parse import urljoin

from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from authlib.integrations.starlette_client import OAuth
from jinja2 import Environment, FileSystemLoader, FileSystemBytecodeCache, select_autoescape
from starlette.config import Config

from api.auth.user_management import delete_user_token, validate_user

# Router
auth_router = APIRouter()
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

@auth_router.get("/chat", name="auth.chat", response_class=HTMLResponse)
async def chat(request: Request) -> HTMLResponse:
    """Explicit chat route (renders main chat UI)."""
    user_info, is_authenticated = await validate_user(request)

    if not is_authenticated or not user_info:
        is_authenticated = False
        user_info = None

    return templates.TemplateResponse(
        "chat.j2",
        {
            "request": request,
            "is_authenticated": is_authenticated,
            "user_info": user_info,
        },
    )

def _build_callback_url(request: Request, path: str) -> str:
    """Build absolute callback URL, honoring OAUTH_BASE_URL if provided."""
    base_override = os.getenv("OAUTH_BASE_URL")
    base = base_override if base_override else str(request.base_url)
    if not base.endswith("/"):
        base += "/"
    return urljoin(base, path.lstrip("/"))

# ---- Routes ----
@auth_router.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    """
    Handle the home page, rendering the landing page for unauthenticated users 
    and the chat page for authenticated users.
    """
    user_info, is_authenticated_flag = await validate_user(request)

    if is_authenticated_flag or user_info:
        return templates.TemplateResponse(
            "chat.j2",
            {
                "request": request,
                "is_authenticated": True,
                "user_info": user_info
            }
        )

    return templates.TemplateResponse(
        "landing.j2", 
        {
            "request": request, 
            "is_authenticated": False, 
            "user_info": None
        }
    )





@auth_router.get("/login", response_class=RedirectResponse)
async def login_page(_: Request) -> RedirectResponse:
    """Redirect login requests to Google OAuth login."""
    return RedirectResponse(url="/login/google", status_code=status.HTTP_302_FOUND)


@auth_router.get("/login/google", name="google.login", response_class=RedirectResponse)
async def login_google(request: Request) -> RedirectResponse:
    """Initiate Google OAuth login flow.

    Args:
        request (Request): The incoming request.

    Returns:
        RedirectResponse: The redirect response to the Google OAuth endpoint.
    """

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
    """Handle Google OAuth callback and user authorization.

    Args:
        request (Request): The incoming request.

    Returns:
        RedirectResponse: The redirect response after handling the callback.
    """

    try:
        google = _get_provider_client(request, "google")
        token = await google.authorize_access_token(request)
        user_info = token.get("userinfo")

        if user_info:

            user_data = {
                'id': user_info.get('id') or user_info.get('sub'),
                'email': user_info.get('email'),
                'name': user_info.get('name'),
                'picture': user_info.get('picture'),
            }

            # Call the registered Google callback handler if it exists to store user data.
            handler = getattr(request.app.state, "callback_handler", None)
            if handler:
                api_token = secrets.token_urlsafe(32)  # ~43 chars, hard to guess

                # call the registered handler (await if async)
                await handler('google', user_data, api_token)

                redirect = RedirectResponse(url="/chat", status_code=302)
                redirect.set_cookie(
                    key="api_token",
                    value=api_token,
                    httponly=True,
                    secure=True
                )

                return redirect

        raise HTTPException(status_code=400, detail="Failed to get user info from Google")

    except Exception as e:
        logging.error("Google OAuth authentication failed: %s", str(e))
        # pylint: disable=raise-missing-from
        raise HTTPException(status_code=400, detail=f"Authentication failed: {str(e)}")


@auth_router.get("/login/google/callback", response_class=RedirectResponse)
async def google_callback_compat(request: Request) -> RedirectResponse:
    """Handle Google OAuth callback compatibility endpoint."""
    qs = f"?{request.url.query}" if request.url.query else ""
    redirect = f"/login/google/authorized{qs}"
    return RedirectResponse(url=redirect, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@auth_router.get("/login/github",  name="github.login", response_class=RedirectResponse)
async def login_github(request: Request) -> RedirectResponse:
    """Initiate GitHub OAuth login flow."""
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
    """Handle GitHub OAuth callback authorization."""
    try:
        github = _get_provider_client(request, "github")
        token = await github.authorize_access_token(request)

        # Fetch GitHub user info
        resp = await github.get("user", token=token)
        if resp.status_code != 200:
            logging.error("Failed to fetch GitHub user info: %s", resp.text)
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
            handler = getattr(request.app.state, "callback_handler", None)
            if handler:

                api_token = secrets.token_urlsafe(32)  # ~43 chars, hard to guess

                # call the registered handler (await if async)
                await handler('github', user_data, api_token)

                redirect = RedirectResponse(url="/chat", status_code=302)
                redirect.set_cookie(
                    key="api_token",
                    value=api_token,
                    httponly=True,
                    secure=True
                )

                return redirect

        raise HTTPException(status_code=400, detail="Failed to get user info from Github")

    except Exception as e:
        logging.error("GitHub OAuth authentication failed: %s", str(e))
        # pylint: disable=raise-missing-from
        raise HTTPException(status_code=400, detail=f"Authentication failed: {str(e)}")  # pylint: disable=raise-missing-from


@auth_router.get("/login/github/callback", response_class=RedirectResponse)
async def github_callback_compat(request: Request) -> RedirectResponse:
    """Handle GitHub OAuth callback compatibility endpoint."""
    qs = f"?{request.url.query}" if request.url.query else ""
    redirect = f"/login/github/authorized{qs}"
    return RedirectResponse(url=redirect, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@auth_router.get("/logout", response_class=RedirectResponse)
async def logout(request: Request) -> RedirectResponse:
    """Handle user logout and delete session cookies."""
    resp = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

    api_token = request.cookies.get("api_token")
    if api_token:
        resp.delete_cookie("api_token")
        await delete_user_token(api_token)

    return resp

# ---- Hook for app factory ----
def init_auth(app):
    """Initialize OAuth and sessions for the app."""

    config = Config(environ=os.environ)
    oauth = OAuth(config)

    google_client_id = os.getenv("GOOGLE_CLIENT_ID")
    google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if not google_client_id or not google_client_secret:
        logging.warning("Google OAuth env vars not set; login will fail until configured.")

    oauth.register(
        name="google",
        client_id=google_client_id,
        client_secret=google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

    github_client_id = os.getenv("GITHUB_CLIENT_ID")
    github_client_secret = os.getenv("GITHUB_CLIENT_SECRET")
    if not github_client_id or not github_client_secret:
        logging.warning("GitHub OAuth env vars not set; login will fail until configured.")

    oauth.register(
        name="github",
        client_id=github_client_id,
        client_secret=github_client_secret,
        access_token_url="https://github.com/login/oauth/access_token",
        authorize_url="https://github.com/login/oauth/authorize",
        api_base_url="https://api.github.com/",
        client_kwargs={"scope": "user:email"},
    )

    app.state.oauth = oauth
