"""Authentication routes for the text2sql API."""

import os
import time
from pathlib import Path
from urllib.parse import urljoin

import httpx
from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from authlib.common.errors import AuthlibBaseError
from starlette.config import Config

from api.logging_config import get_logger
from api.auth.user_management import validate_and_cache_user

# Router
auth_router = APIRouter()
TEMPLATES_DIR = str((Path(__file__).resolve().parents[1] / "../app/templates").resolve())
templates = Jinja2Templates(directory=TEMPLATES_DIR)
logger = get_logger(__name__)

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

def _clear_auth_session(session: dict):
    """Remove only auth-related keys from session instead of clearing everything."""
    for key in [
        "user_info",
        "google_token",
        "github_token",
        "token_validated_at",
        "oauth_google_auth",
    ]:
        session.pop(key, None)

@auth_router.get("/chat", name="auth.chat", response_class=HTMLResponse)
async def chat(request: Request) -> HTMLResponse:
    """Explicit chat route (renders main chat UI)."""
    user_info, is_authenticated = await validate_and_cache_user(request)
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
    user_info, is_authenticated_flag = await validate_and_cache_user(request)

    if not is_authenticated_flag:
        _clear_auth_session(request.session)

    if not is_authenticated_flag:
        return templates.TemplateResponse(
            "landing.j2", 
            {
                "request": request, 
                "is_authenticated": False, 
                "user_info": None
            }
        )

    return templates.TemplateResponse(
        "chat.j2",
        {
            "request": request,
            "is_authenticated": is_authenticated_flag,
            "user_info": user_info,
        },
    )


@auth_router.get("/login", response_class=RedirectResponse)
async def login_page(_: Request) -> RedirectResponse:
    return RedirectResponse(url="/login/google", status_code=status.HTTP_302_FOUND)


@auth_router.get("/login/google", name="google.login", response_class=RedirectResponse)
async def login_google(request: Request) -> RedirectResponse:
    google = _get_provider_client(request, "google")
    redirect_uri = _build_callback_url(request, "login/google/authorized")

    # Helpful hint if localhost vs 127.0.0.1 mismatch is likely
    if not os.getenv("OAUTH_BASE_URL") and "127.0.0.1" in str(request.base_url):
        logger.warning(
            "OAUTH_BASE_URL not set and base URL is 127.0.0.1; set OAUTH_BASE_URL to"
            " avoid redirect mismatch."
        )

    return await google.authorize_redirect(request, redirect_uri)


@auth_router.get("/login/google/authorized", response_class=RedirectResponse)
async def google_authorized(request: Request) -> RedirectResponse:
    try:
        google = _get_provider_client(request, "google")
        token = await google.authorize_access_token(request)

        # Always fetch userinfo explicitly
        resp = await google.get("https://www.googleapis.com/oauth2/v2/userinfo", token=token)
        if resp.status_code != 200:
            logger.error("Failed to fetch Google user info", body=resp.text)
            _clear_auth_session(request.session)
            return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

        user_info = resp.json()
        if not user_info.get("email"):
            logger.error("Invalid Google user data received")
            _clear_auth_session(request.session)
            return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

        # Normalize
        request.session["user_info"] = {
            "id": str(user_info.get("id") or user_info.get("sub")),
            "name": user_info.get("name", ""),
            "email": user_info.get("email"),
            "picture": user_info.get("picture", ""),
            "provider": "google",
        }
        request.session["google_token"] = token
        request.session["token_validated_at"] = time.time()

        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

    except AuthlibBaseError as e:
        logger.error("Google OAuth error", error=str(e))
        _clear_auth_session(request.session)
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)


@auth_router.get("/login/google/callback", response_class=RedirectResponse)
async def google_callback_compat(request: Request) -> RedirectResponse:
    qs = f"?{request.url.query}" if request.url.query else ""
    redirect = f"/login/google/authorized{qs}"
    return RedirectResponse(url=redirect, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@auth_router.get("/login/github",  name="github.login", response_class=RedirectResponse)
async def login_github(request: Request) -> RedirectResponse:
    github = _get_provider_client(request, "github")
    redirect_uri = _build_callback_url(request, "login/github/authorized")

    # Helpful hint if localhost vs 127.0.0.1 mismatch is likely
    if not os.getenv("OAUTH_BASE_URL") and "127.0.0.1" in str(request.base_url):
        logger.warning(
            "OAUTH_BASE_URL not set and base URL is 127.0.0.1; "
            "if your GitHub OAuth app uses 'http://localhost:5000', "
            "set OAUTH_BASE_URL=http://localhost:5000 to avoid redirect_uri mismatch."
        )

    return await github.authorize_redirect(request, redirect_uri)


@auth_router.get("/login/github/authorized", response_class=RedirectResponse)
async def github_authorized(request: Request) -> RedirectResponse:
    try:
        github = _get_provider_client(request, "github")
        token = await github.authorize_access_token(request)

        # Fetch GitHub user info
        resp = await github.get("https://api.github.com/user", token=token)
        if resp.status_code != 200:
            logger.error("Failed to fetch GitHub user info", body=resp.text)
            _clear_auth_session(request.session)
            return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

        user_info = resp.json()
        # Get user email if not public
        email = user_info.get("email")
        if not email:
            # Try to get primary email from emails endpoint
            email_resp = await github.get("https://api.github.com/user/emails", token=token)
            if email_resp.status_code == 200:
                emails = email_resp.json()
                for email_obj in emails:
                    if email_obj.get("primary"):
                        email = email_obj.get("email")
                        break

        if not user_info.get("id") or not email:
            logger.error("Invalid GitHub user data received")
            _clear_auth_session(request.session)
            return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

        # Normalize user info structure
        request.session["user_info"] = {
            "id": str(user_info.get("id")),
            "name": user_info.get("name") or user_info.get("login", ""),
            "email": email,
            "picture": user_info.get("avatar_url", ""),
            "provider": "github",
        }
        request.session["github_token"] = token
        request.session["token_validated_at"] = time.time()

        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

    except AuthlibBaseError as e:
        logger.error("GitHub OAuth error", error=str(e))
        _clear_auth_session(request.session)
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)


@auth_router.get("/login/github/callback", response_class=RedirectResponse)
async def github_callback_compat(request: Request) -> RedirectResponse:
    qs = f"?{request.url.query}" if request.url.query else ""
    redirect = f"/login/github/authorized{qs}"
    return RedirectResponse(url=redirect, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@auth_router.get("/logout", response_class=RedirectResponse)
async def logout(request: Request) -> RedirectResponse:
    """Handle user logout and revoke tokens for Google (actively) and GitHub (locally)."""
    google_token = request.session.get("google_token")
    github_token = request.session.get("github_token")

    # ---- Revoke Google tokens ----
    if google_token:
        tokens_to_revoke = []
        if access_token := google_token.get("access_token"):
            tokens_to_revoke.append(access_token)
        if refresh_token := google_token.get("refresh_token"):
            tokens_to_revoke.append(refresh_token)

        if tokens_to_revoke:
            try:
                async with httpx.AsyncClient() as client:
                    for token in tokens_to_revoke:
                        resp = await client.post(
                            "https://oauth2.googleapis.com/revoke",
                            params={"token": token},
                            headers={"content-type": "application/x-www-form-urlencoded"},
                        )
                        if resp.status_code != 200:
                            logger.warning(
                                "Google token revoke failed",
                                status=resp.status_code,
                                body=resp.text,
                            )
                        else:
                            logger.info("Successfully revoked Google token")
            except Exception as e:
                logger.error("Error revoking Google tokens", error=str(e))

    # ---- Handle GitHub tokens ----
    if github_token:
        logger.info("GitHub token found, clearing from session (no remote revoke available).")
        # GitHub logout is local only unless we call the App management API

    # ---- Clear session auth keys ----
    for key in ["user_info", "google_token", "github_token", "token_validated_at"]:
        request.session.pop(key, None)

    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

# ---- Hook for app factory ----
def init_auth(app):
    """Initialize OAuth and sessions for the app."""
    config = Config(".env")
    from authlib.integrations.starlette_client import OAuth
    oauth = OAuth(config)

    google_client_id = os.getenv("GOOGLE_CLIENT_ID")
    google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if not google_client_id or not google_client_secret:
        logger.warning("Google OAuth env vars not set; login will fail until configured.")

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
        logger.warning("GitHub OAuth env vars not set; login will fail until configured.")

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
