"""User management and authentication functions for text2sql API."""

import logging
import time
from functools import wraps

import requests
from flask import g, session, jsonify
from flask_dance.contrib.google import google
from flask_dance.contrib.github import github

from api.extensions import db


def ensure_user_in_organizations(provider_user_id, email, name, provider, picture=None):
    """
    Check if identity exists in Organizations graph, create if not.
    Creates separate Identity and User nodes with proper relationships.
    Uses MERGE for atomic operations and better performance.
    Returns (is_new_user, user_info)
    """
    # Input validation
    if not provider_user_id or not email or not provider:
        logging.error("Missing required parameters: provider_user_id=%s, email=%s, provider=%s",
                     provider_user_id, email, provider)
        return False, None

    # Validate email format (basic check)
    if "@" not in email or "." not in email:
        logging.error("Invalid email format: %s", email)
        return False, None

    # Validate provider is in allowed list
    allowed_providers = ["google", "github"]
    if provider not in allowed_providers:
        logging.error("Invalid provider: %s", provider)
        return False, None

    try:
        # Select the Organizations graph
        organizations_graph = db.select_graph("Organizations")

        # Extract first and last name
        name_parts = (name or "").split(" ", 1) if name else ["", ""]
        first_name = name_parts[0] if len(name_parts) > 0 else ""
        last_name = name_parts[1] if len(name_parts) > 1 else ""

        # Use MERGE to handle all scenarios in a single atomic operation
        merge_query = """
        // First, ensure user exists (merge by email)
        MERGE (user:User {email: $email})
        ON CREATE SET
            user.first_name = $first_name,
            user.last_name = $last_name,
            user.created_at = timestamp()

        // Then, merge identity and link to user
        MERGE (identity:Identity {provider: $provider, provider_user_id: $provider_user_id})
        ON CREATE SET
            identity.email = $email,
            identity.name = $name,
            identity.picture = $picture,
            identity.created_at = timestamp(),
            identity.last_login = timestamp()
        ON MATCH SET
            identity.email = $email,
            identity.name = $name,
            identity.picture = $picture,
            identity.last_login = timestamp()

        // Ensure relationship exists
        MERGE (identity)-[:AUTHENTICATES]->(user)

        // Return results with flags to determine if this was a new user/identity
        RETURN
            identity,
            user,
            identity.created_at = identity.last_login AS is_new_identity,
            EXISTS((user)<-[:AUTHENTICATES]-(:Identity)) AS had_other_identities
        """

        result = organizations_graph.query(merge_query, {
            "provider": provider,
            "provider_user_id": provider_user_id,
            "email": email,
            "name": name,
            "picture": picture,
            "first_name": first_name,
            "last_name": last_name
        })

        if result.result_set:
            identity = result.result_set[0][0]
            user = result.result_set[0][1]
            is_new_identity = result.result_set[0][2]
            had_other_identities = result.result_set[0][3]

            # Determine the type of operation for logging
            if is_new_identity and not had_other_identities:
                # Brand new user (first identity)
                logging.info("NEW USER CREATED: provider=%s, provider_user_id=%s, "
                           "email=%s, name=%s", provider, provider_user_id, email, name)
                return True, {"identity": identity, "user": user}
            if is_new_identity and had_other_identities:
                # New identity for existing user (cross-provider linking)
                logging.info("NEW IDENTITY LINKED TO EXISTING USER: provider=%s, "
                           "provider_user_id=%s, email=%s, name=%s",
                           provider, provider_user_id, email, name)
                return True, {"identity": identity, "user": user}
            # Existing identity login
            logging.info("Existing identity found: provider=%s, email=%s", provider, email)
            return False, {"identity": identity, "user": user}
        logging.error("Failed to create/update identity and user: email=%s", email)
            return False, None

    except (AttributeError, ValueError, KeyError) as e:
        logging.error("Error managing user in Organizations graph: %s", e)
        return False, None
    except Exception as e:
        logging.error("Unexpected error managing user in Organizations graph: %s", e)
        return False, None


def update_identity_last_login(provider, provider_user_id):
    """Update the last login timestamp for an existing identity"""
    # Input validation
    if not provider or not provider_user_id:
        logging.error("Missing required parameters: provider=%s, provider_user_id=%s",
                     provider, provider_user_id)
        return

    # Validate provider is in allowed list
    allowed_providers = ["google", "github"]
    if provider not in allowed_providers:
        logging.error("Invalid provider: %s", provider)
        return

    try:
        organizations_graph = db.select_graph("Organizations")
        update_query = """
        MATCH (identity:Identity {provider: $provider, provider_user_id: $provider_user_id})
        SET identity.last_login = timestamp()
        RETURN identity
        """
        organizations_graph.query(update_query, {
            "provider": provider,
            "provider_user_id": provider_user_id
        })
        logging.info("Updated last login for identity: provider=%s, provider_user_id=%s",
                    provider, provider_user_id)
    except (AttributeError, ValueError, KeyError) as e:
        logging.error("Error updating last login for identity %s/%s: %s",
                     provider, provider_user_id, e)
    except Exception as e:
        logging.error("Unexpected error updating last login for identity %s/%s: %s",
                     provider, provider_user_id, e)


def validate_and_cache_user():
    """
    Helper function to validate OAuth token and cache user info.
    Returns (user_info, is_authenticated) tuple.
    Supports both Google and GitHub OAuth.
    """
    try:
        # Check for cached user info from either provider
        user_info = session.get("user_info")
        token_validated_at = session.get("token_validated_at", 0)
        current_time = time.time()

        # Use cached user info if it's less than 15 minutes old
        if user_info and (current_time - token_validated_at) < 900:  # 15 minutes
            return user_info, True

        # Check Google OAuth first
        if google.authorized:
            try:
                resp = google.get("/oauth2/v2/userinfo")
                if resp.ok:
                    google_user = resp.json()
                    # Validate required fields
                    if not google_user.get("id") or not google_user.get("email"):
                        logging.warning("Invalid Google user data received")
                        session.clear()
                        return None, False

                    # Normalize user info structure
                    user_info = {
                        "id": str(google_user.get("id")),  # Ensure string type
                        "name": google_user.get("name", ""),
                        "email": google_user.get("email"),
                        "picture": google_user.get("picture", ""),
                        "provider": "google"
                    }
                    session["user_info"] = user_info
                    session["token_validated_at"] = current_time
                    return user_info, True
            except (requests.RequestException, KeyError, ValueError) as e:
                logging.warning("Google OAuth validation error: %s", e)
                session.clear()

        # Check GitHub OAuth
        if github.authorized:
            try:
                # Get user profile
                resp = github.get("/user")
                if resp.ok:
                    github_user = resp.json()

                    # Validate required fields
                    if not github_user.get("id"):
                        logging.warning("Invalid GitHub user data received")
                        session.clear()
                        return None, False

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

                    if not email:
                        logging.warning("No email found for GitHub user")
                        session.clear()
                        return None, False

                    # Normalize user info structure
                    user_info = {
                        "id": str(github_user.get("id")),  # Convert to string for consistency
                        "name": github_user.get("name") or github_user.get("login", ""),
                        "email": email,
                        "picture": github_user.get("avatar_url", ""),
                        "provider": "github"
                    }
                    session["user_info"] = user_info
                    session["token_validated_at"] = current_time
                    return user_info, True
            except (requests.RequestException, KeyError, ValueError) as e:
                logging.warning("GitHub OAuth validation error: %s", e)
                session.clear()

        # If no valid authentication found, clear session
        session.clear()
        return None, False

    except Exception as e:
        logging.error("Unexpected error in validate_and_cache_user: %s", e)
        session.clear()
        return None, False


def token_required(f):
    """Decorator to protect routes with token authentication"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            user_info, is_authenticated = validate_and_cache_user()

            if not is_authenticated:
                return jsonify(message="Unauthorized - Please log in"), 401

            g.user_id = user_info.get("id")
            if not g.user_id:
                session.clear()
                return jsonify(message="Unauthorized - Invalid user"), 401

            return f(*args, **kwargs)
        except Exception as e:
            logging.error("Unexpected error in token_required: %s", e)
            session.clear()
            return jsonify(message="Unauthorized - Authentication error"), 401

    return decorated_function
