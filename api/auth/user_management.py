"""User management and authentication functions for text2sql API."""

import base64
import logging
from math import log
import os
import secrets
from functools import wraps
from typing import Tuple, Optional, Dict, Any

from fastapi import Request, HTTPException, status
from api.extensions import db

# Get secret key for sessions
SECRET_KEY = os.getenv("FASTAPI_SECRET_KEY")
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)
    logging.warning("FASTAPI_SECRET_KEY not set, using generated key. Set this in production!")


async def _get_user_info(api_token: str) -> Optional[Dict[str, Any]]:
    """
    Get user information from the database by email.
    """
    query = """
        MATCH (i:Identity)-[:HAS_TOKEN]->(t:Token {id: $api_token})
        RETURN i.email, i.name, i.picture, (t IS NOT NULL AND timestamp() <= t.expires_at) AS token_valid
    """

    try:
        # Select the Organizations graph
        organizations_graph = db.select_graph("Organizations")

        result = await organizations_graph.query(query, {
            "api_token": api_token,
        })

        if result.result_set:
            single_result = result.result_set[0]
            token_valid = single_result[3]

            # NOTE: Invalid tokens should be cleaned up periodically
            if token_valid:
                return {
                    "email": single_result[0],
                    "name": single_result[1],
                    "picture": single_result[2]
                }

        return None
    except Exception as e:
        logging.error("Error fetching user info: %s", e)
        return None


async def delete_user_token(api_token: str):
    """
    Delete user token from the database.
    """
    query = """
    MATCH (t:Token {id:$api_token})
    DELETE t
    """
    try:
        # Select the Organizations graph
        organizations_graph = db.select_graph("Organizations")

        await organizations_graph.query(query, {
            "api_token": api_token,
        })

    except Exception as e:
        logging.error("Error deleting user token: %s", e)


async def ensure_user_in_organizations(
    provider_user_id: str, 
    email: str, 
    name: str, 
    provider: str, 
    api_token: str, 
    picture: str = None
):
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
        
        // Then, create a session linked to the Identity and store the API_Token
        MERGE (token:Token {id: $api_token})
        ON CREATE SET
            token.created_at = timestamp(),
            token.expires_at = timestamp() + 86400000  // 24h expiry
        MERGE (identity)-[:HAS_TOKEN]->(token)

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
            "last_name": last_name,
            "api_token": api_token
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
        })
        logging.info("Updated last login for identity: provider=%s, provider_user_id=%s",
                    provider, provider_user_id)
    except (AttributeError, ValueError, KeyError) as e:
        logging.error("Error updating last login for identity %s/%s: %s",
                     provider, provider_user_id, e)
    except Exception as e:
        logging.error("Unexpected error updating last login for identity %s/%s: %s",
                     provider, provider_user_id, e)


async def validate_user(request: Request) -> Tuple[Optional[Dict[str, Any]], bool]:
    """
    Helper function to validate token.
    Returns (user_info, is_authenticated).
    Includes refresh handling for Google.
    """
    try:
        # token might be in the URL if not in the cookie for API access
        api_token = request.cookies.get("api_token")
        if not api_token:
            api_token = request.query_params.get("api_token")

        if api_token:
            db_info = await _get_user_info(api_token)

            if db_info:
                return db_info, True

        return None, False

    except Exception as e:
        logging.error("Unexpected error in validate_user: %s", e)
        return None, False

def token_required(func):
    """Decorator to protect FastAPI routes with token authentication.
    Automatically refreshes tokens if expired.
    """

    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        try:
            user_info, is_authenticated = await validate_user(request)

            if not is_authenticated:
                # Second attempt after clearing session to force re-validation
                user_info, is_authenticated = await validate_user(request)

            if not is_authenticated:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Unauthorized - Please log in"
                )

            # Attach user_id to request.state (like FASTAPI's g.user_id)
            # we're using the email as BASE64 encoded
            request.state.user_id = base64.b64encode(user_info.get("email").encode()).decode()
            if not request.state.user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Unauthorized - Invalid user"
                )

            return await func(request, *args, **kwargs)

        except HTTPException:
            raise
        except Exception as e:
            logging.error("Unexpected error in token_required: %s", e)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized - Authentication error"
            )

    return wrapper
