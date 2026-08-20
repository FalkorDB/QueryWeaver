"""OAuth signal handlers for Google and GitHub authentication.

Lightweight handlers are stored on the FastAPI app state so route
callbacks can invoke them when processing OAuth responses.
"""

import logging
from typing import Dict, Any

from fastapi import FastAPI
from authlib.integrations.starlette_client import OAuth

from .user_management import ensure_user_in_organizations


def setup_oauth_handlers(app: FastAPI, oauth: OAuth):
    """Set up OAuth handlers for both Google and GitHub."""

    # Store oauth in app state for access in routes
    app.state.oauth = oauth

    async def handle_callback(provider: str, user_info: Dict[str, Any], api_token: str):
        """Handle Provider OAuth callback processing"""
        try:
            user_id = user_info.get("id")
            email = user_info.get("email")
            name = user_info.get("name")

            # Validate required fields
            if not user_id or not email:
                logging.error("Missing required fields from %s OAuth response", provider)
                return False

            # Check if identity exists in Organizations graph, create if new.
            # The first element is "is new identity", not a success flag, so the
            # returned info is what tells us the records were actually persisted.
            _, identity_info = await ensure_user_in_organizations(
                user_id,
                email,
                name,
                provider,
                api_token,
                user_info.get("picture"),
            )
            if identity_info is None:
                logging.error(
                    "Could not persist %s identity for %s - deferring provisioning",
                    provider,
                    email,
                )
                return False

            return True
        except Exception as exc:  # capture exception for logging, pylint: disable=broad-exception-caught
            logging.error("Error handling %s OAuth callback: %s", provider, exc)
            return False

    # Store handlers in app state for use in route callbacks
    app.state.callback_handler = handle_callback
