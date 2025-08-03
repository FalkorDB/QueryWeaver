"""Authentication routes for the text2sql API."""

import logging

import requests
from flask import Blueprint, render_template, redirect, url_for, session
from flask_dance.contrib.google import google
from flask_dance.contrib.github import github

from api.auth.user_management import validate_and_cache_user

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def home():
    """Home route"""
    user_info, is_authenticated = validate_and_cache_user()

    # If not authenticated through OAuth, check for any stale session data
    if not is_authenticated and not google.authorized and not github.authorized:
        session.pop("user_info", None)

    return render_template("chat.j2", is_authenticated=is_authenticated, user_info=user_info)

@main_bp.route("/logout")
def logout():
    """Handle user logout and token revocation."""
    session.clear()

    # Revoke Google OAuth token if authorized
    if google.authorized:
        try:
            google.get(
                "https://accounts.google.com/o/oauth2/revoke",
                params={"token": google.access_token}
            )
        except (requests.RequestException, AttributeError) as e:
            logging.warning("Error revoking Google token: %s", e)

    # Revoke GitHub OAuth token if authorized
    if github.authorized:
        try:
            # GitHub doesn't have a simple revoke endpoint like Google
            # The token will expire naturally or can be revoked from GitHub settings
            pass
        except AttributeError as e:
            logging.warning("Error with GitHub token cleanup: %s", e)

    return redirect(url_for("main.home"))
