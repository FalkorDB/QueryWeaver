"""User management and authentication functions for text2sql API."""

import time
from functools import wraps
from typing import Tuple, Optional, Dict, Any

from fastapi import Request, HTTPException, status
from authlib.integrations.starlette_client import OAuth

from api.extensions import db
from api.logging_config import get_logger

logger = get_logger(__name__)


def ensure_user_in_organizations(provider_user_id, email, name, provider, picture=None):
    """
    Check if identity exists in Organizations graph, create if not.
    Creates separate Identity and User nodes with proper relationships.
    Uses MERGE for atomic operations and better performance.
    Returns (is_new_user, user_info)
    """
    # Input validation
    if not provider_user_id or not email or not provider:
        logger.error(
            "Missing required parameters",
            provider_user_id=provider_user_id,
            email=email,
            provider=provider,
        )
        return False, None
        return False, None

    # Validate email format (basic check)
    if "@" not in email or "." not in email:
        logger.error("Invalid email format", email=email)
        return False, None

    # Validate provider is in allowed list
    allowed_providers = ["google", "github"]
    if provider not in allowed_providers:
        logger.error("Invalid provider", provider=provider)
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
                logger.info(
                    "NEW USER CREATED",
                    provider=provider,
                    provider_user_id=provider_user_id,
                    email=email,
                    name=name,
                )
                return True, {"identity": identity, "user": user}
            elif is_new_identity and had_other_identities:
                # New identity for existing user (cross-provider linking)
                logger.info(
                    "NEW IDENTITY LINKED TO EXISTING_USER",
                    provider=provider,
                    provider_user_id=provider_user_id,
                    email=email,
                    name=name,
                )
                return True, {"identity": identity, "user": user}
            else:
                # Existing identity login
                logger.info("Existing identity found", provider=provider, email=email)
                return False, {"identity": identity, "user": user}
        else:
            logger.error("Failed to create/update identity and user", email=email)
            return False, None

    except (AttributeError, ValueError, KeyError) as e:
        logger.error("Error managing user in Organizations graph", error=str(e))
        return False, None
    except Exception as e:
        logger.error("Unexpected error managing user in Organizations graph", error=str(e))
        return False, None


def update_identity_last_login(provider, provider_user_id):
    """Update the last login timestamp for an existing identity"""
    # Input validation
    if not provider or not provider_user_id:
        logger.error(
            "Missing required parameters",
            provider=provider,
            provider_user_id=provider_user_id,
        )
        return

    # Validate provider is in allowed list
    allowed_providers = ["google", "github"]
    if provider not in allowed_providers:
        logger.error("Invalid provider", provider=provider)
        return

    try:
        organizations_graph = db.select_graph("Organizations")
        update_query = """
        MATCH (identity:Identity {provider: $provider, provider_user_id: $provider_user_id})
        SET identity.last_login = timestamp()
        RETURN identity
        """
        organizations_graph.query(
            update_query,
            {
                "provider": provider,
                "provider_user_id": provider_user_id,
            },
        )
        logger.info(
            "Updated last login for identity",
            provider=provider,
            provider_user_id=provider_user_id,
        )
    except (AttributeError, ValueError, KeyError) as e:
        logger.error(
            "Error updating last login for identity",
            provider=provider,
            provider_user_id=provider_user_id,
            error=str(e),
        )
    except Exception as e:
        logger.error(
            "Unexpected error updating last login for identity",
            provider=provider,
            provider_user_id=provider_user_id,
            error=str(e),
        )


async def validate_and_cache_user(request: Request) -> Tuple[Optional[Dict[str, Any]], bool]:
    """
    Helper function to validate OAuth token and cache user info.
    Returns (user_info, is_authenticated).
    Supports both Google and GitHub OAuth.
    Includes refresh handling for Google.
    """
    try:
        user_info = request.session.get("user_info")
        token_validated_at = request.session.get("token_validated_at", 0)
        current_time = time.time()

        # Use cached user info if it's less than 15 minutes old
        if user_info and (current_time - token_validated_at) < 900:
            return user_info, True

        oauth: OAuth = request.app.state.oauth

        # ---- Google OAuth ----
        google_token = request.session.get("google_token")
        if google_token and hasattr(oauth, "google"):
            try:
                resp = await oauth.google.get("/oauth2/v2/userinfo", token=google_token)

                if resp.status_code == 401 and "refresh_token" in google_token:
                    # Token expired, try refreshing
                    try:
                        new_token = await oauth.google.refresh_token(
                            "https://oauth2.googleapis.com/token",
                            refresh_token=google_token["refresh_token"],
                        )
                        request.session["google_token"] = new_token
                        resp = await oauth.google.get("/oauth2/v2/userinfo", token=new_token)
                        logger.info("Google access token refreshed successfully")
                    except Exception as e:
                        logger.error("Google token refresh failed", error=str(e))
                        request.session.pop("google_token", None)
                        request.session.pop("user_info", None)
                        return None, False

                if resp.status_code == 200:
                    google_user = resp.json()
                    if not google_user.get("id") or not google_user.get("email"):
                        logger.warning("Invalid Google user data received")
                        request.session.pop("google_token", None)
                        request.session.pop("user_info", None)
                        return None, False

                    # Normalize
                    user_info = {
                        "id": str(google_user.get("id")),
                        "name": google_user.get("name", ""),
                        "email": google_user.get("email"),
                        "picture": google_user.get("picture", ""),
                        "provider": "google",
                    }
                    request.session["user_info"] = user_info
                    request.session["token_validated_at"] = current_time
                    return user_info, True
            except Exception as e:
                logger.warning("Google OAuth validation error", error=str(e))
                request.session.pop("google_token", None)
                request.session.pop("user_info", None)

        # ---- GitHub OAuth ----
        github_token = request.session.get("github_token")
        if github_token and hasattr(oauth, "github"):
            try:
                resp = await oauth.github.get("/user", token=github_token)
                if resp.status_code == 200:
                    github_user = resp.json()
                    if not github_user.get("id"):
                        logger.warning("Invalid GitHub user data received")
                        request.session.pop("github_token", None)
                        request.session.pop("user_info", None)
                        return None, False

                    # Get primary email
                    email_resp = await oauth.github.get("/user/emails", token=github_token)
                    email = None
                    if email_resp.status_code == 200:
                        for email_obj in email_resp.json():
                            if email_obj.get("primary", False):
                                email = email_obj.get("email")
                                break
                        if not email and email_resp.json():
                            email = email_resp.json()[0].get("email")

                    if not email:
                        logger.warning("No email found for GitHub user")
                        request.session.pop("github_token", None)
                        request.session.pop("user_info", None)
                        return None, False

                    user_info = {
                        "id": str(github_user.get("id")),
                        "name": github_user.get("name") or github_user.get("login", ""),
                        "email": email,
                        "picture": github_user.get("avatar_url", ""),
                        "provider": "github",
                    }
                    request.session["user_info"] = user_info
                    request.session["token_validated_at"] = current_time
                    return user_info, True
            except Exception as e:
                logger.warning("GitHub OAuth validation error", error=str(e))
                request.session.pop("github_token", None)
                request.session.pop("user_info", None)

        # No valid auth
        request.session.pop("user_info", None)
        return None, False

    except Exception as e:
        logger.error("Unexpected error in validate_and_cache_user", error=str(e))
        request.session.pop("user_info", None)
        return None, False

def token_required(func):
    """Decorator to protect FastAPI routes with token authentication.
    Automatically refreshes tokens if expired.
    """

    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        try:
            user_info, is_authenticated = await validate_and_cache_user(request)

            if not is_authenticated:
                # Second attempt after clearing session to force re-validation
                request.session.pop("user_info", None)
                user_info, is_authenticated = await validate_and_cache_user(request)

            if not is_authenticated:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Unauthorized - Please log in"
                )

            # Attach user_id to request.state (like FASTAPI's g.user_id)
            request.state.user_id = user_info.get("id")
            if not request.state.user_id:
                request.session.pop("user_info", None)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Unauthorized - Invalid user"
                )

            return await func(request, *args, **kwargs)

        except HTTPException:
            raise
        except Exception as e:
            logger.error("Unexpected error in token_required", error=str(e))
            request.session.pop("user_info", None)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized - Authentication error"
            )

    return wrapper
