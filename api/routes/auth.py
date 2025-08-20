"""Authentication routes for the text2sql API."""

import logging
import time

import requests
from quart import Blueprint, render_template, redirect, url_for, session, current_app, jsonify
from api.auth.quart_oauth import google, github

from api.auth.user_management import validate_and_cache_user

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/")
async def home():
    """Home route"""
    user_info, is_authenticated = validate_and_cache_user()

    # Use app context to access OAuth providers
    google_oauth = current_app.google if hasattr(current_app, 'google') else None
    github_oauth = current_app.github if hasattr(current_app, 'github') else None

    if not is_authenticated and google_oauth and github_oauth:
        if not google_oauth.authorized and not github_oauth.authorized:
            return await render_template("chat.j2", user_info=None, is_authenticated=False)

    return await render_template("chat.j2", user_info=user_info, is_authenticated=is_authenticated)


@auth_bp.route("/login")
async def login_google():
    """Handle Google OAuth login route."""
    google_oauth = current_app.google if hasattr(current_app, 'google') else None
    
    if not google_oauth or not google_oauth.authorized:
        return redirect(url_for("google.login"))

    try:
        # Get user info from Google
        user_info_data = await google_oauth.get_user_info()

        # Validate required fields
        if not user_info_data.get("id") or not user_info_data.get("email"):
            logging.error("Invalid Google user data received during login")
            session.clear()
            return redirect(url_for("google.login"))

        # Normalize user info structure
        user_info = {
            "id": str(user_info_data.get("id")),  # Ensure string type
            "name": user_info_data.get("name", ""),
            "email": user_info_data.get("email"),
            "picture": user_info_data.get("picture", ""),
            "provider": "google"
        }
        session["user_info"] = user_info
        session["token_validated_at"] = time.time()
        return redirect(url_for("auth.home"))

    except Exception as e:
        logging.error("Google login error: %s", e)
        session.clear()
        return redirect(url_for("google.login"))


@auth_bp.route("/logout")
async def logout():
    """Handle user logout and token revocation."""
    session.clear()

    # Access OAuth providers from app context
    google_oauth = current_app.google if hasattr(current_app, 'google') else None
    github_oauth = current_app.github if hasattr(current_app, 'github') else None

    # Revoke Google OAuth token if authorized
    if google_oauth and google_oauth.authorized:
        try:
            await google_oauth.get(
                "https://accounts.google.com/o/oauth2/revoke",
                params={"token": google_oauth.access_token}
            )
        except Exception as e:
            logging.warning("Error revoking Google token: %s", e)

    # Revoke GitHub OAuth token if authorized
    if github_oauth and github_oauth.authorized:
        try:
            # GitHub doesn't have a simple revoke endpoint like Google
            # The token will expire naturally or can be revoked from GitHub settings
            pass
        except Exception as e:
            logging.warning("Error with GitHub token cleanup: %s", e)

    return redirect(url_for("auth.home"))
