"""User management and authentication functions for text2sql API."""

import asyncio
import logging
import time
from functools import wraps

import requests
from quart import g, session, jsonify

from api.extensions import db


class User:
    """User class for OAuth authentication."""
    
    def __init__(self, email, name, picture=None, provider=None):
        self.email = email
        self.name = name
        self.picture = picture or ""
        self.provider = provider or "unknown"
    
    def to_dict(self):
        """Convert user to dictionary for session storage."""
        return {
            'email': self.email,
            'name': self.name,
            'picture': self.picture,
            'provider': self.provider
        }


async def ensure_user_in_organizations(provider_user_id, email, name, provider, picture=None):
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

        result = await organizations_graph.query(merge_query, {
            "provider": provider,
            "provider_user_id": provider_user_id,
            "email": email,
            "name": name,
            "picture": picture,
            "first_name": first_name,
            "last_name": last_name
        }, timeout=30)

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
            elif is_new_identity and had_other_identities:
                # New identity for existing user (cross-provider linking)
                logging.info("NEW IDENTITY LINKED TO EXISTING USER: provider=%s, "
                           "provider_user_id=%s, email=%s, name=%s",
                           provider, provider_user_id, email, name)
                return True, {"identity": identity, "user": user}
            else:
                # Existing identity login
                logging.info("Existing identity found: provider=%s, email=%s", provider, email)
                return False, {"identity": identity, "user": user}
        else:
            logging.error("Failed to create/update identity and user: email=%s", email)
            return False, None

    except (AttributeError, ValueError, KeyError) as e:
        logging.error("Error managing user in Organizations graph: %s", e)
        return False, None
    except Exception as e:
        logging.error("Unexpected error managing user in Organizations graph: %s", e)
        return False, None


async def update_identity_last_login(provider, provider_user_id):
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
        await organizations_graph.query(update_query, {
            "provider": provider,
            "provider_user_id": provider_user_id
        }, timeout=30)
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
    Validate and return cached user information from session.
    For the Quart/Authlib implementation, we rely on session data
    set during OAuth callbacks.
    
    Returns:
        tuple: (user_info dict or None, is_authenticated bool)
    """
    user_info = session.get("user_info")
    token_validated_at = session.get("token_validated_at", 0)
    
    if not user_info:
        return None, False
        
    current_time = time.time()
    
    # Use cached user info if it's less than 15 minutes old
    if user_info and (current_time - token_validated_at) < 900:  # 15 minutes
        return user_info, True
    
    # If token is older than 15 minutes, consider it expired for security
    # In a production app, you might want to refresh the token instead
    session.clear()
    return None, False


def token_required(f):
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        try:
            user_info, is_authenticated = validate_and_cache_user()

            if not is_authenticated:
                return jsonify({"message": "Unauthorized - Please log in"}), 401

            g.user_id = user_info.get("id")
            if not g.user_id:
                return jsonify({"message": "Unauthorized - Invalid user"}), 401

        except Exception as e:
            return jsonify({"message": str(e)}), 401

        result = f(*args, **kwargs)
        if asyncio.iscoroutine(result):
            return await result
        return result

    return decorated_function