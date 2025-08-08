"""Authentication routes for the text2sql API."""

import logging
import time

import requests
from flask import Blueprint, render_template, redirect, url_for, session
from flask_dance.contrib.google import google
from flask_dance.contrib.github import github

from api.auth.user_management import validate_and_cache_user

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/")
def home():
    """Home route"""
    user_info, is_authenticated = validate_and_cache_user()

    # If not authenticated through OAuth, check for any stale session data
    if not is_authenticated and not google.authorized and not github.authorized:
        session.pop("user_info", None)

    # Check OAuth configuration
    import os
    oauth_config = {
        'google_enabled': bool(os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET")),
        'github_enabled': bool(os.getenv("GITHUB_CLIENT_ID") and os.getenv("GITHUB_CLIENT_SECRET"))
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
    from flask import request, jsonify
    import hashlib
    import os
    import sqlite3
    
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['firstName', 'lastName', 'email', 'password']
        for field in required_fields:
            if not data.get(field):
                return jsonify({"success": False, "error": f"{field} is required"}), 400
        
        first_name = data['firstName'].strip()
        last_name = data['lastName'].strip()
        email = data['email'].strip().lower()
        password = data['password']
        
        # Validate email format
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            return jsonify({"success": False, "error": "Invalid email format"}), 400
        
        # Validate password strength
        if len(password) < 8:
            return jsonify({"success": False, "error": "Password must be at least 8 characters long"}), 400
        
        # Initialize database if it doesn't exist
        db_path = os.path.join(os.path.dirname(__file__), '..', 'users.db')
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create users table if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Check if user already exists
        cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
        if cursor.fetchone():
            conn.close()
            return jsonify({"success": False, "error": "User with this email already exists"}), 400
        
        # Hash password
        salt = os.urandom(32)
        password_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
        stored_password = salt + password_hash
        
        # Insert new user
        cursor.execute('''
            INSERT INTO users (email, password_hash, first_name, last_name)
            VALUES (?, ?, ?, ?)
        ''', (email, stored_password.hex(), first_name, last_name))
        
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        
        # Add user to Organizations graph
        from api.auth.user_management import ensure_user_in_organizations
        user_name = f"{first_name} {last_name}"
        ensure_user_in_organizations(str(user_id), email, user_name, "email")
        
        return jsonify({"success": True, "message": "User created successfully"})
        
    except Exception as e:
        logging.error("Email signup error: %s", e)
        return jsonify({"success": False, "error": "Registration failed"}), 500


@auth_bp.route("/email-login", methods=["POST"])
def email_login():
    """Handle email/password user authentication."""
    from flask import request, jsonify
    import hashlib
    import sqlite3
    import os
    
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('email') or not data.get('password'):
            return jsonify({"success": False, "error": "Email and password are required"}), 400
        
        email = data['email'].strip().lower()
        password = data['password']
        
        # Connect to database
        db_path = os.path.join(os.path.dirname(__file__), '..', 'users.db')
        
        if not os.path.exists(db_path):
            return jsonify({"success": False, "error": "Invalid credentials"}), 401
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get user by email
        cursor.execute('''
            SELECT id, email, password_hash, first_name, last_name 
            FROM users WHERE email = ?
        ''', (email,))
        
        user_row = cursor.fetchone()
        conn.close()
        
        if not user_row:
            return jsonify({"success": False, "error": "Invalid credentials"}), 401
        
        user_id, user_email, stored_password_hex, first_name, last_name = user_row
        
        # Verify password
        stored_password = bytes.fromhex(stored_password_hex)
        salt = stored_password[:32]
        stored_hash = stored_password[32:]
        
        password_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
        
        if password_hash != stored_hash:
            return jsonify({"success": False, "error": "Invalid credentials"}), 401
        
        # Create session
        user_info = {
            "id": str(user_id),
            "email": user_email,
            "name": f"{first_name} {last_name}",
            "first_name": first_name,
            "last_name": last_name,
            "provider": "email"
        }
        
        session["user_info"] = user_info
        session["token_validated_at"] = time.time()
        
        # Ensure user exists in Organizations graph
        from api.auth.user_management import ensure_user_in_organizations
        ensure_user_in_organizations(str(user_id), user_email, f"{first_name} {last_name}", "email")
        
        return jsonify({"success": True, "message": "Login successful"})
        
    except Exception as e:
        logging.error("Email login error: %s", e)
        return jsonify({"success": False, "error": "Login failed"}), 500
