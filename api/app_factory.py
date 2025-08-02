"""Application factory for the text2sql Flask app."""

import logging
import os

from dotenv import load_dotenv
from flask import Flask, redirect, url_for, request, abort
from werkzeug.exceptions import HTTPException
from flask_dance.contrib.google import make_google_blueprint
from flask_dance.contrib.github import make_github_blueprint
from flask_dance.consumer.storage.session import SessionStorage

from api.auth.oauth_handlers import setup_oauth_handlers
from api.routes.auth import auth_bp
from api.routes.graphs import graphs_bp
from api.routes.database import database_bp

# Load environment variables from .env file
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.secret_key = os.getenv("FLASK_SECRET_KEY")
    if not app.secret_key:
        import secrets
        app.secret_key = secrets.token_hex(32)
        logging.warning("FLASK_SECRET_KEY not set, using generated key. Set this in production!")

    # Google OAuth setup
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
    google_bp = make_google_blueprint(
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scope=[
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile",
            "openid"
        ]
    )
    app.register_blueprint(google_bp, url_prefix="/login")

    # GitHub OAuth setup
    GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
    GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
    github_bp = make_github_blueprint(
        client_id=GITHUB_CLIENT_ID,
        client_secret=GITHUB_CLIENT_SECRET,
        scope="user:email",
        storage=SessionStorage()
    )
    app.register_blueprint(github_bp, url_prefix="/login")

    # Set up OAuth signal handlers
    setup_oauth_handlers(google_bp, github_bp)

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(graphs_bp)
    app.register_blueprint(database_bp)

    @app.errorhandler(Exception)
    def handle_oauth_error(error):
        """Handle OAuth-related errors gracefully"""
        # Check if it's an OAuth-related error
        if "token" in str(error).lower() or "oauth" in str(error).lower():
            logging.warning("OAuth error occurred: %s", error)
            from flask import session
            session.clear()
            return redirect(url_for("auth.home"))

        # If it's an HTTPException (like abort(403)), re-raise so Flask handles it properly
        if isinstance(error, HTTPException):
            return error

        # For other errors, let them bubble up
        raise error

    @app.before_request
    def block_static_directories():
        if request.path.startswith('/static/'):
            # Remove /static/ prefix to get the actual path
            filename = request.path[8:]  # len('/static/') = 8
            file_path = os.path.join(app.static_folder, filename)

            if os.path.isdir(file_path):
                abort(405)

    return app
