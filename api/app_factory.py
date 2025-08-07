"""Application factory for the text2sql Flask app."""

import logging
import os
import secrets

from dotenv import load_dotenv
from flask import Flask, redirect, url_for, request, abort, session
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename
from flask_dance.contrib.google import make_google_blueprint
from flask_dance.contrib.github import make_github_blueprint
from flask_dance.consumer.storage.session import SessionStorage

from api.auth.oauth_handlers import setup_oauth_handlers
from api.routes.main import main_bp
from api.routes.graphs import graphs_bp
from api.routes.database import database_bp
from api.routes.organization import organization_bp

# Load environment variables from .env file
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.secret_key = os.getenv("FLASK_SECRET_KEY")
    if not app.secret_key:
        app.secret_key = secrets.token_hex(32)
        logging.warning("FLASK_SECRET_KEY not set, using generated key. Set this in production!")

    # Google OAuth setup
    google_client_id = os.getenv("GOOGLE_CLIENT_ID")
    google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    google_bp = make_google_blueprint(
        client_id=google_client_id,
        client_secret=google_client_secret,
        scope=[
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile",
            "openid"
        ]
    )
    app.register_blueprint(google_bp, url_prefix="/login")

    # GitHub OAuth setup
    github_client_id = os.getenv("GITHUB_CLIENT_ID")
    github_client_secret = os.getenv("GITHUB_CLIENT_SECRET")
    github_bp = make_github_blueprint(
        client_id=github_client_id,
        client_secret=github_client_secret,
        scope="user:email",
        storage=SessionStorage()
    )
    app.register_blueprint(github_bp, url_prefix="/login")

    # Set up OAuth signal handlers
    setup_oauth_handlers(google_bp, github_bp)

    # Register blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(graphs_bp)
    app.register_blueprint(database_bp)
    app.register_blueprint(organization_bp)

    @app.errorhandler(Exception)
    def handle_oauth_error(error):
        """Handle OAuth-related errors gracefully"""
        # Check if it's an OAuth-related error
        if "token" in str(error).lower() or "oauth" in str(error).lower():
            logging.warning("OAuth error occurred: %s", error)
            session.clear()
            return redirect(url_for("main.home"))

        # If it's an HTTPException (like abort(403)), re-raise so Flask handles it properly
        if isinstance(error, HTTPException):
            return error

        # For other errors, let them bubble up
        raise error

    @app.before_request
    def block_static_directories():
        if request.path.startswith('/static/'):
            # Remove /static/ prefix to get the actual path
            filename = secure_filename(request.path[8:])
            # Normalize and ensure the path stays within static_folder
            static_folder = os.path.abspath(app.static_folder)
            file_path = os.path.normpath(os.path.join(static_folder, filename))
            if not file_path.startswith(static_folder):
                abort(400)  # Bad request, attempted traversal
            if os.path.isdir(file_path):
                abort(405)

    return app
