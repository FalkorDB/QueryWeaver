"""Authentication routes for the text2sql API."""

import hashlib
import hmac
import logging
import os
import re
import time

import requests
from flask import Blueprint, render_template, redirect, url_for, session, request, jsonify
from flask_dance.contrib.google import google
from flask_dance.contrib.github import github

from api.auth.user_management import validate_and_cache_user
from api.extensions import db

auth_bp = Blueprint("auth", __name__)


def _hash_password(password):
    """Hash a password using PBKDF2 with a random salt."""
    salt = os.urandom(32)
    password_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return (salt + password_hash).hex()


def _verify_password(password, stored_password_hex):
    """Verify a password against its hash using constant-time comparison."""
    try:
        stored_password = bytes.fromhex(stored_password_hex)
        salt = stored_password[:32]
        stored_hash = stored_password[32:]

        password_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)

        return hmac.compare_digest(password_hash, stored_hash)
    except (ValueError, TypeError):
        return False


def _validate_email(email):
    """Validate email format."""
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(email_pattern, email))


def _check_user_exists_by_email(email):
    """Check if a user with this email already exists in the Organizations graph."""
    try:
        organizations_graph = db.select_graph("Organizations")

        query = """
        MATCH (identity:Identity {email: $email})
        RETURN identity
        LIMIT 1
        """

        result = organizations_graph.query(query, {"email": email})
        return len(result.result_set) > 0
    except Exception as e:
        logging.error("Error checking user existence: %s", e)
        return False


def _create_email_user(email, password, first_name, last_name):
    """Create a new user with email/password authentication in the Organizations graph."""
    try:
        organizations_graph = db.select_graph("Organizations")

        # Hash the password
        password_hash = _hash_password(password)

        # Generate a unique provider_user_id for email users (using email as base)
        provider_user_id = f"email_{hashlib.md5(email.encode()).hexdigest()}"

        # Create identity and user in one transaction
        create_query = """
        // Create user node
        MERGE (user:User {email: $email})
        ON CREATE SET
            user.first_name = $first_name,
            user.last_name = $last_name,
            user.created_at = timestamp()
        
        // Create identity node with password hash
        CREATE (identity:Identity {
            provider: "email",
            provider_user_id: $provider_user_id,
            email: $email,
            name: $name,
            password_hash: $password_hash,
            created_at: timestamp(),
            last_login: timestamp()
        })
        
        // Link identity to user
        CREATE (identity)-[:AUTHENTICATES]->(user)
        
        RETURN identity, user
        """

        name = f"{first_name} {last_name}"
        result = organizations_graph.query(create_query, {
            "email": email,
            "provider_user_id": provider_user_id,
            "name": name,
            "password_hash": password_hash,
            "first_name": first_name,
            "last_name": last_name
        })

        if result.result_set:
            identity = result.result_set[0][0]
            user = result.result_set[0][1]
            logging.info("NEW EMAIL USER CREATED: email=%s, name=%s", email, name)
            return True, {"identity": identity, "user": user}
        else:
            logging.error("Failed to create email user: %s", email)
            return False, None

    except Exception as e:
        logging.error("Error creating email user: %s", e)
        return False, None


def _authenticate_email_user(email, password):
    """Authenticate a user with email/password."""
    try:
        organizations_graph = db.select_graph("Organizations")

        # Get user identity with password hash
        auth_query = """
        MATCH (identity:Identity {provider: "email", email: $email})-[:AUTHENTICATES]->(user:User)
        RETURN identity, user
        """

        result = organizations_graph.query(auth_query, {"email": email})

        if not result.result_set:
            return False, None

        identity = result.result_set[0][0]
        user = result.result_set[0][1]

        # Verify password
        password_hash = identity.properties.get('password_hash', '')
        if not _verify_password(password, password_hash):
            return False, None

        # Update last login
        update_query = """
        MATCH (identity:Identity {provider: "email", email: $email})
        SET identity.last_login = timestamp()
        RETURN identity
        """
        organizations_graph.query(update_query, {"email": email})
        
        logging.info("EMAIL USER AUTHENTICATED: email=%s", email)
        return True, {"identity": identity, "user": user}
        
    except Exception as e:
        logging.error("Error authenticating email user: %s", e)
        return False, None


@auth_bp.route("/")
def home():
    """Home route"""
    user_info, is_authenticated = validate_and_cache_user()

    # If not authenticated through OAuth, check for any stale session data
    if not is_authenticated and not google.authorized and not github.authorized:
        session.pop("user_info", None)

    # Check OAuth configuration
    oauth_config = {
        'google_enabled': bool(os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET")),
        'github_enabled': bool(os.getenv("GITHUB_CLIENT_ID") and os.getenv("GITHUB_CLIENT_SECRET")),
        'email_enabled': bool(os.getenv("EMAIL_AUTH_ENABLED", "").lower() in ["true", "1", "yes", "on"])
    }

    return render_template("chat.j2", 
                         is_authenticated=is_authenticated, 
                         user_info=user_info,
                         oauth_config=oauth_config)


@auth_bp.route("/login")
def login_google():
    """Handle Google OAuth login route."""
    if not google.authorized:
        return redirect(url_for("google.login"))

    try:
        resp = google.get("/oauth2/v2/userinfo")
        if resp.ok:
            google_user = resp.json()

            # Validate required fields
            if not google_user.get("id") or not google_user.get("email"):
                logging.error("Invalid Google user data received during login")
                session.clear()
                return redirect(url_for("google.login"))

            # Normalize user info structure
            user_info = {
                "id": str(google_user.get("id")),  # Ensure string type
                "name": google_user.get("name", ""),
                "email": google_user.get("email"),
                "picture": google_user.get("picture", ""),
                "provider": "google"
            }
            session["user_info"] = user_info
            session["token_validated_at"] = time.time()
            return redirect(url_for("auth.home"))

        # OAuth token might be expired, redirect to login
        session.clear()
        return redirect(url_for("google.login"))
    except (requests.RequestException, KeyError, ValueError) as e:
        logging.error("Google login error: %s", e)
        session.clear()
        return redirect(url_for("google.login"))


@auth_bp.route("/logout")
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

    return redirect(url_for("auth.home"))


@auth_bp.route("/email-signup", methods=["POST"])
def email_signup():
    """Handle email/password user registration."""
    try:
        # Check if email authentication is enabled
        if os.getenv("EMAIL_AUTH_ENABLED", "").lower() not in ["true", "1", "yes", "on"]:
            return jsonify({"success": False, "error": "Email authentication is not enabled"}), 403
        
        data = request.get_json()
        
        # Validate required fields
        if not all(data.get(field) for field in ['firstName', 'lastName', 'email', 'password']):
            return jsonify({"success": False, "error": "All fields are required"}), 400
        
        first_name = data['firstName'].strip()
        last_name = data['lastName'].strip()
        email = data['email'].strip().lower()
        password = data['password']
        
        # Validate email format
        if not _validate_email(email):
            return jsonify({"success": False, "error": "Invalid email format"}), 400
        
        # Validate password strength
        if len(password) < 8:
            return jsonify({"success": False, "error": "Password must be at least 8 characters long"}), 400
        
        # Check if user already exists
        if _check_user_exists_by_email(email):
            return jsonify({"success": False, "error": "User with this email already exists"}), 400
        
        # Create new user in FalkorDB
        success, user_data = _create_email_user(email, password, first_name, last_name)
        
        if not success:
            return jsonify({"success": False, "error": "Registration failed"}), 500
        
        logging.info("User registration successful: %s", email)
        return jsonify({"success": True, "message": "User created successfully"})
        
    except Exception as e:
        logging.error("Email signup error: %s", e)
        return jsonify({"success": False, "error": "Registration failed"}), 500


@auth_bp.route("/email-login", methods=["POST"])
def email_login():
    """Handle email/password user authentication."""
    try:
        # Check if email authentication is enabled
        if os.getenv("EMAIL_AUTH_ENABLED", "").lower() not in ["true", "1", "yes", "on"]:
            return jsonify({"success": False, "error": "Email authentication is not enabled"}), 403
        
        data = request.get_json()
        
        # Validate required fields
        if not data.get('email') or not data.get('password'):
            return jsonify({"success": False, "error": "Email and password are required"}), 400
        
        email = data['email'].strip().lower()
        password = data['password']
        
        # Authenticate user
        success, user_data = _authenticate_email_user(email, password)
        
        if not success:
            return jsonify({"success": False, "error": "Invalid credentials"}), 401
        
        # Extract user information from FalkorDB result
        identity = user_data["identity"]
        user = user_data["user"]
        
        # Create session
        user_info = {
            "id": identity.properties.get('provider_user_id', ''),
            "email": identity.properties.get('email', ''),
            "name": identity.properties.get('name', ''),
            "first_name": user.properties.get('first_name', ''),
            "last_name": user.properties.get('last_name', ''),
            "provider": "email"
        }
        
        session["user_info"] = user_info
        session["token_validated_at"] = time.time()
        
        return jsonify({"success": True, "message": "Login successful"})
        
    except Exception as e:
        logging.error("Email login error: %s", e)
        return jsonify({"success": False, "error": "Login failed"}), 500
