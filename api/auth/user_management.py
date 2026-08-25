"""User management and authentication functions for text2sql API."""

import base64
import logging
import os
import secrets
from functools import wraps
from typing import Tuple, Optional, Dict, Any, TypedDict

from fastapi import Request, HTTPException, status
from api.auth.browser_session import establish_browser_session, read_browser_session
from api.config import ORGANIZATIONS_GRAPH
from api.core.errors import AuthBackendUnavailableError, TRANSIENT_BACKEND_ERRORS
from api.extensions import db

# Get secret key for sessions
SECRET_KEY = os.getenv("FASTAPI_SECRET_KEY")
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)
    logging.warning(
        "FASTAPI_SECRET_KEY not set, using generated key. Set this in production!"
    )


class IdentityInfo(TypedDict):
    """The identity payload returned by the Organizations-graph writes.

    A ``TypedDict`` rather than a model: these values come straight out of a
    query result and are read with ``.get()`` by every caller, so describing the
    dict is accurate where constructing a model would not be.

    Attributes:
        identity (Dict[str, Any]): Details about the identity provider and credentials.
        user (Dict[str, Any]): Information about the associated user.
        new_identity (bool): Whether this is a newly created identity.
    """
    identity: Dict[str, Any]
    user: Dict[str, Any]
    new_identity: bool


async def _get_user_info(api_token: str) -> Optional[Dict[str, Any]]:
    """
    Look up the owner of an API token in the Organizations graph.

    Returns ``None`` when the token is unknown or expired, and raises
    :class:`AuthBackendUnavailableError` when the graph itself is unreachable —
    the two cases must not collapse into one, or an outage looks like a bad
    credential.
    """
    query = """
        MATCH (i:Identity)-[:HAS_TOKEN]->(t:Token {id: $api_token})
        RETURN i.email, i.name, i.picture, (t IS NOT NULL AND timestamp() <= t.expires_at) AS token_valid
    """

    try:
        # Select the Organizations graph
        organizations_graph = db.select_graph(ORGANIZATIONS_GRAPH)

        result = await organizations_graph.query(
            query,
            {
                "api_token": api_token,
            },
        )
    except TRANSIENT_BACKEND_ERRORS as e:
        logging.error("Auth store unreachable while fetching user info: %s", e)
        raise AuthBackendUnavailableError(str(e)) from e

    if result.result_set:
        single_result = result.result_set[0]
        token_valid = single_result[3]

        if token_valid:
            return {
                "email": single_result[0],
                "name": single_result[1],
                "picture": single_result[2],
            }
        # Delete invalid/expired token from DB for cleanup
        await delete_user_token(api_token)

    return None


async def identity_exists(email: str) -> bool:
    """Whether a stored ``User`` record still backs this email.

    Raises :class:`AuthBackendUnavailableError` when the graph is unreachable,
    so callers can tell "this identity is gone" from "we could not check".
    """
    try:
        organizations_graph = db.select_graph(ORGANIZATIONS_GRAPH)
        result = await organizations_graph.query(
            "MATCH (u:User {email: $email}) RETURN count(u) > 0",
            {"email": email},
        )
    except TRANSIENT_BACKEND_ERRORS as e:
        logging.error("Auth store unreachable while checking identity: %s", e)
        raise AuthBackendUnavailableError(str(e)) from e

    return bool(result.result_set and result.result_set[0][0])


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
        organizations_graph = db.select_graph(ORGANIZATIONS_GRAPH)

        await organizations_graph.query(
            query,
            {
                "api_token": api_token,
            },
        )

    except Exception as e:  # pylint: disable=broad-exception-caught
        logging.error("Error deleting user token: %s", e)


async def ensure_user_in_organizations(  # pylint: disable=too-many-arguments, disable=too-many-positional-arguments
    provider_user_id: str,
    email: str,
    name: str,
    provider: str,
    api_token: Optional[str],
    picture: str | None = None,
) -> tuple[bool, Optional[IdentityInfo]]:
    """
    Check if identity exists in Organizations graph, create if not.
    Creates separate Identity and User nodes with proper relationships.
    Uses MERGE for atomic operations and better performance.

    Pass ``api_token=None`` to persist only the User/Identity records without
    minting a programmatic token — used when repairing an existing browser
    login that was established while the graph was unreachable.

    Returns (is_new_identity, user_info). ``user_info`` is ``None`` when the
    records could not be persisted, so callers should test that, not the flag.
    """
    # GitHub returns a JSON number here while the session payload stores it as a
    # string, so MERGE would key 12345 and "12345" to two separate Identity
    # nodes. Normalise once, at the only boundary that writes them.
    provider_user_id = str(provider_user_id) if provider_user_id is not None else provider_user_id

    # Input validation

    validation_result = _validate_user_input(provider_user_id, email, provider)
    if validation_result:
        return validation_result

    try:
        organizations_graph = db.select_graph(ORGANIZATIONS_GRAPH)
        first_name, last_name = _extract_name_parts(name)

        merge_query = _build_user_merge_query(include_token=api_token is not None)
        query_params = _build_query_params(
            provider,
            provider_user_id,
            email,
            name=name,
            picture=picture,
            first_name=first_name,
            last_name=last_name,
            api_token=api_token,
        )

        result = await organizations_graph.query(merge_query, query_params)
        return _process_user_result(result, provider, provider_user_id, email, name)

    except (AttributeError, ValueError, KeyError) as e:
        logging.error("Error managing user in Organizations graph: %s", e)
        return False, None
    except (ConnectionError, TimeoutError) as e:
        logging.error(
            "Database connection error managing user in Organizations graph: %s", e
        )
        return False, None
    except Exception as e:  # pylint: disable=broad-exception-caught
        logging.error("Unexpected error managing user in Organizations graph: %s", e)
        return False, None


async def update_identity_last_login(provider, provider_user_id):
    """Update the last login timestamp for an existing identity"""
    # Input validation
    if not provider or not provider_user_id:
        logging.error(
            "Missing required parameters: provider=%s, provider_user_id=%s",
            provider,
            provider_user_id,
        )
        return

    # Validate provider is in allowed list
    allowed_providers = ["google", "github", "email"]
    if provider not in allowed_providers:
        logging.error("Invalid provider: %s", provider)
        return

    # Match the normalisation ensure_user_in_organizations applies on write.
    provider_user_id = str(provider_user_id)

    try:
        organizations_graph = db.select_graph(ORGANIZATIONS_GRAPH)
        update_query = """
        MATCH (identity:Identity {provider: $provider, provider_user_id: $provider_user_id})
        SET identity.last_login = timestamp()
        RETURN identity
        """
        await organizations_graph.query(
            update_query, {"provider": provider, "provider_user_id": provider_user_id}
        )
        logging.info(
            "Updated last login for identity: provider=%s, provider_user_id=%s",
            provider,
            provider_user_id,
        )
    except (AttributeError, ValueError, KeyError) as e:
        logging.error(
            "Error updating last login for identity %s/%s: %s",
            provider,
            provider_user_id,
            e,
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        logging.error(
            "Unexpected error updating last login for identity %s/%s: %s",
            provider,
            provider_user_id,
            e,
        )


def get_explicit_api_token(request: Request) -> Optional[str]:
    """Extract an API token the caller passed *deliberately*.

    A ``Bearer`` header or an ``api_token`` query parameter is a programmatic
    credential: the caller means to act as that token, so it is never allowed to
    fall back to whoever happens to be logged in to this browser.
    """
    api_token = request.query_params.get("api_token")
    if api_token:
        return api_token

    auth_header = request.headers.get("authorization") or request.headers.get(
        "Authorization"
    )
    if auth_header:
        parts = auth_header.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip() or None

    return None


def get_cookie_api_token(request: Request) -> Optional[str]:
    """Extract the ambient ``api_token`` cookie, if any."""
    return request.cookies.get("api_token") or None


async def validate_user(request: Request) -> Tuple[Optional[Dict[str, Any]], bool]:
    """
    Resolve the caller's identity. Returns ``(user_info, is_authenticated)``.

    Credentials are tried in order of how explicit they are:

    1. A deliberate API token (``Bearer`` header or ``?api_token=``). It is
       database-backed, and a bad one fails outright rather than silently
       downgrading to whoever is logged in to this browser.
    2. The browser login session — a signed cookie, so it stays valid while
       FalkorDB is down. This is what keeps the login screen from reappearing
       during an outage; database-backed work still fails at query time.
    3. The legacy ``api_token`` cookie, for sessions issued before browser
       logins became self-contained.

    Raises :class:`AuthBackendUnavailableError` when a supplied API token —
    explicit or the legacy cookie — cannot be checked because the Organizations
    graph is unreachable. Collapsing that into "not authenticated" would show
    the login screen during an outage, which is the symptom this module exists
    to remove.
    """
    explicit_token = get_explicit_api_token(request)
    if explicit_token:
        db_info = await _get_user_info(explicit_token)
        return (db_info, True) if db_info else (None, False)

    session_user = read_browser_session(request)
    if session_user:
        # Deliberately no database lookup: that is the point of the signed
        # session. The cost is that it cannot be revoked server-side before it
        # expires, so the TTL bounds the exposure and rotating the signing key
        # is the kill switch. API tokens keep a revocable server-side record.
        return session_user, True

    cookie_token = get_cookie_api_token(request)
    if cookie_token:
        # Propagates AuthBackendUnavailableError so an outage reads as 503, the
        # same as the explicit-token branch above.
        db_info = await _get_user_info(cookie_token)
        if db_info:
            # Upgrade the legacy cookie to a browser session on first use, so
            # anyone already logged in when this deploys stops depending on the
            # database for their next outage instead of waiting for a re-login.
            establish_browser_session(
                request,
                email=db_info["email"],
                name=db_info.get("name"),
                picture=db_info.get("picture"),
                provider="api_token_cookie",
                provider_user_id=db_info["email"],
                provisioned=True,
            )
            return db_info, True

    return None, False


def token_required(func):
    """Decorator to protect FastAPI routes with token authentication.
    Automatically refreshes tokens if expired.
    Supports both OAuth and API token authentication.
    """

    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        # Only the authentication work belongs in this try: a failure inside the
        # route itself is not an authentication problem, and reporting it as 401
        # tells the browser to re-login over what is usually a database outage.
        try:
            user_info, is_authenticated = await validate_user(request)

            if not is_authenticated:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Unauthorized - Please log in or provide a valid API token",
                )

            # Attach user_id to request.state (like FASTAPI's g.user_id)
            # we're using the email as BASE64 encoded
            email = user_info.get("email")
            request.state.user_id = base64.b64encode(email.encode()).decode()
            request.state.user_email = email

            if not request.state.user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Unauthorized - Invalid user",
                )

        except HTTPException:
            raise
        except AuthBackendUnavailableError as e:
            # The token may well be valid — we just could not check it. Saying
            # 401 here would tell clients to re-authenticate over a transient
            # outage; 503 tells them to retry.
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service temporarily unavailable - please retry",
            ) from e
        except Exception as e:
            logging.error("Unexpected error in token_required: %s", e)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized - Authentication error",
            ) from e

        return await func(request, *args, **kwargs)

    return wrapper


def token_optional(func):
    """Decorator for routes that work with or without authentication.
    Sets request.state.user_id if authenticated, None if not.
    Does not raise 401 - allows unauthenticated access.
    """

    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        try:
            user_info, is_authenticated = await validate_user(request)

            if is_authenticated and user_info:
                # Authenticated - set user info
                email = user_info.get("email")
                request.state.user_id = base64.b64encode(email.encode()).decode()
                request.state.user_email = email
            else:
                # Not authenticated - set to None (allow demo mode)
                request.state.user_id = None
                request.state.user_email = None

            return await func(request, *args, **kwargs)

        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.exception("Unexpected error in token_optional: %s", e)
            # Don't raise 401 - allow the request to proceed
            request.state.user_id = None
            request.state.user_email = None
            return await func(request, *args, **kwargs)

    return wrapper


def _validate_user_input(provider_user_id: str, email: str, provider: str):
    """Validate input parameters for user creation/update."""
    if not provider_user_id or not email or not provider:
        logging.error(
            "Missing required parameters: provider_user_id=%s, email=%s, provider=%s",
            provider_user_id,
            email,
            provider,
        )
        return False, None

    # Validate email format (basic check)
    if "@" not in email or "." not in email:
        logging.error("Invalid email format: %s", email)
        return False, None

    # Validate provider is in allowed list
    allowed_providers = ["google", "github", "api", "email"]
    if provider not in allowed_providers:
        logging.error("Invalid provider: %s", provider)
        return False, None

    return None  # No validation errors


def _extract_name_parts(name: str) -> tuple:
    """Extract first and last name from full name."""
    name_parts = (name or "").split(" ", 1) if name else ["", ""]
    first_name = name_parts[0] if len(name_parts) > 0 else ""
    last_name = name_parts[1] if len(name_parts) > 1 else ""
    return first_name, last_name


def _build_user_merge_query(include_token: bool = True) -> str:
    """Build the Cypher query for user/identity merge operations.

    ``include_token`` drops the Token MERGE so an identity can be persisted
    without issuing a programmatic credential.
    """
    token_clause = (
        """
        // Then, create a session linked to the Identity and store the API_Token
        MERGE (token:Token {id: $api_token})
        ON CREATE SET
            token.created_at = timestamp(),
            token.expires_at = timestamp() + 86400000  // 24h expiry
        MERGE (identity)-[:HAS_TOKEN]->(token)
        """
        if include_token
        else ""
    )
    return """
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
""" + token_clause + """
        // Return results with flags to determine if this was a new user/identity
        RETURN
            identity,
            user,
            identity.created_at = identity.last_login AS is_new_identity
        """


def _build_query_params(  # pylint: disable=too-many-arguments
    provider: str,
    provider_user_id: str,
    email: str,
    *,
    name: str,
    picture: str | None = None,
    first_name: str,
    last_name: str,
    api_token: Optional[str]
) -> dict:
    """Build query parameters for the database operation."""
    return {
        "provider": provider,
        "provider_user_id": provider_user_id,
        "email": email,
        "name": name,
        "picture": picture,
        "first_name": first_name,
        "last_name": last_name,
        "api_token": api_token,
    }


def _process_user_result(
    result, provider: str, provider_user_id: str, email: str, name: str
) -> tuple[bool, Optional[IdentityInfo]]:
    """Process the database result and return appropriate response."""
    if result.result_set:
        identity: dict[str, Any] = result.result_set[0][0]
        user: dict[str, Any] = result.result_set[0][1]
        is_new_identity: bool = result.result_set[0][2]

        if is_new_identity:
            # New identity for existing user (cross-provider linking)
            logging.info(
                "NEW IDENTITY LINKED TO USER: provider=%s, "
                "provider_user_id=%s, email=%s, name=%s",
                provider,
                provider_user_id,
                email,
                name,
            )
            return True, {
                "identity": identity,
                "user": user,
                "new_identity": is_new_identity,
            }

        # Existing identity login
        logging.info("Existing identity found: provider=%s, email=%s", provider, email)
        return False, {
            "identity": identity,
            "user": user,
            "new_identity": is_new_identity,
        }

    logging.error("Failed to create/update identity and user: email=%s", email)
    return False, None
