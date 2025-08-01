"""OAuth signal handlers for Google and GitHub authentication."""

import logging
import time

import requests
from flask import session
from flask_dance.consumer import oauth_authorized
from flask_dance.contrib.google import google
from flask_dance.contrib.github import github

from .user_management import ensure_user_in_organizations


def setup_oauth_handlers(google_bp, github_bp):
    """Set up OAuth signal handlers for both Google and GitHub blueprints."""
    
    @oauth_authorized.connect_via(google_bp)
    def google_logged_in(blueprint, token):  # pylint: disable=unused-argument
        """Handle Google OAuth authorization callback."""
        if not token:
            return False

        try:
            # Get user profile
            resp = google.get("/oauth2/v2/userinfo")
            if resp.ok:
                google_user = resp.json()
                user_id = google_user.get("id")
                email = google_user.get("email")
                name = google_user.get("name")

                if user_id and email:
                    # Check if identity exists in Organizations graph, create if new
                    is_new_user, _ = ensure_user_in_organizations(
                        user_id, email, name, "google", google_user.get("picture")
                    )

                    # If existing identity, just update last login
                    # (already done in ensure_user_in_organizations)

                # Normalize user info structure for session
                user_info_session = {
                    "id": user_id,
                    "name": name,
                    "email": email,
                    "picture": google_user.get("picture"),
                    "provider": "google"
                }
                session["user_info"] = user_info_session
                session["token_validated_at"] = time.time()
                return False  # Don't create default flask-dance entry in session

        except (requests.RequestException, KeyError, ValueError, AttributeError) as e:
            logging.error("Google OAuth signal error: %s", e)

        return False

    @oauth_authorized.connect_via(github_bp)
    def github_logged_in(blueprint, token):  # pylint: disable=unused-argument
        """Handle GitHub OAuth authorization callback."""
        if not token:
            return False

        try:
            # Get user profile
            resp = github.get("/user")
            if resp.ok:
                github_user = resp.json()

                # Get user email (GitHub may require separate call for email)
                email_resp = github.get("/user/emails")
                email = None
                if email_resp.ok:
                    emails = email_resp.json()
                    # Find primary email
                    for email_obj in emails:
                        if email_obj.get("primary", False):
                            email = email_obj.get("email")
                            break
                    # If no primary email found, use the first one
                    if not email and emails:
                        email = emails[0].get("email")

                user_id = str(github_user.get("id"))
                name = github_user.get("name") or github_user.get("login")

                if user_id and email:
                    # Check if identity exists in Organizations graph, create if new
                    is_new_user, _ = ensure_user_in_organizations(
                        user_id, email, name, "github", github_user.get("avatar_url")
                    )

                    # If existing identity, just update last login
                    # (already done in ensure_user_in_organizations)

                # Normalize user info structure for session
                user_info_session = {
                    "id": user_id,
                    "name": name,
                    "email": email,
                    "picture": github_user.get("avatar_url"),
                    "provider": "github"
                }
                session["user_info"] = user_info_session
                session["token_validated_at"] = time.time()
                return False  # Don't create default flask-dance entry in session

        except (requests.RequestException, KeyError, ValueError, AttributeError) as e:
            logging.error("GitHub OAuth signal error: %s", e)

        return False
