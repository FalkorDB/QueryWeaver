"""OAuth signal handlers for Google and GitHub authentication.

Lightweight handlers are stored on the FastAPI app state so route
callbacks can invoke them when processing OAuth responses.
"""

from typing import Dict, Any

from fastapi import FastAPI, Request
from authlib.integrations.starlette_client import OAuth

from api.logging_config import get_logger
from .user_management import ensure_user_in_organizations

logger = get_logger(__name__)


def setup_oauth_handlers(app: FastAPI, oauth: OAuth):
    """Set up OAuth handlers for both Google and GitHub."""

    # Store oauth in app state for access in routes
    app.state.oauth = oauth

    async def handle_google_callback(_request: Request,
                                     _token: Dict[str, Any],
                                     user_info: Dict[str, Any]):
        """Handle Google OAuth callback processing"""
        try:
            user_id = user_info.get("id")
            email = user_info.get("email")
            name = user_info.get("name")

            # Validate required fields
            if not user_id or not email:
                logger.error("Missing required fields from Google OAuth response")
                return False

            # Check if identity exists in Organizations graph, create if new
            _, _ = ensure_user_in_organizations(
                user_id,
                email,
                name,
                "google",
                user_info.get("picture"),
            )

            return True
        except Exception as exc:  # capture exception for logging
            logger.error("Error handling Google OAuth callback", error=str(exc))
            return False

    async def handle_github_callback(_request: Request,
                                     _token: Dict[str, Any],
                                     user_info: Dict[str, Any]):
        """Handle GitHub OAuth callback processing"""
        try:
            user_id = user_info.get("id")
            email = user_info.get("email")
            name = user_info.get("name") or user_info.get("login")

            # Validate required fields
            if not user_id or not email:
                logger.error("Missing required fields from GitHub OAuth response")
                return False

            # Check if identity exists in Organizations graph, create if new
            _, _ = ensure_user_in_organizations(
                user_id,
                email,
                name,
                "github",
                user_info.get("picture"),
            )

            return True
        except Exception as exc:  # capture exception for logging
            logger.error("Error handling GitHub OAuth callback", error=str(exc))
            return False

    # Store handlers in app state for use in route callbacks
    app.state.google_callback_handler = handle_google_callback
    app.state.github_callback_handler = handle_github_callback
