"""Application factory for creating Quart application instances."""

import os
import logging
import secrets
from datetime import timedelta
from quart import Quart, request, jsonify, session, redirect, url_for, abort
from quart_cors import cors
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Import OAuth setup
from api.auth.quart_oauth import init_oauth_providers

# Import routes
from api.routes.auth import auth_bp
from api.routes.graphs import graphs_bp
from api.routes.database import database_bp

load_dotenv()

from api.routes.auth import auth_bp
from api.routes.graphs import graphs_bp
from api.routes.database import database_bp

# Load environment variables from .env file
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def create_app():
    """Create and configure the Quart application."""
    app = Quart(__name__)
    
    # Load configuration from environment variables
    app.config['FLASK_SECRET_KEY'] = os.getenv("FLASK_SECRET_KEY")
    app.config['GOOGLE_CLIENT_ID'] = os.getenv("GOOGLE_CLIENT_ID")
    app.config['GOOGLE_CLIENT_SECRET'] = os.getenv("GOOGLE_CLIENT_SECRET")
    app.config['GITHUB_CLIENT_ID'] = os.getenv("GITHUB_CLIENT_ID")
    app.config['GITHUB_CLIENT_SECRET'] = os.getenv("GITHUB_CLIENT_SECRET")
    
    # Set secret key
    app.secret_key = app.config['FLASK_SECRET_KEY']
    if not app.secret_key:
        app.secret_key = secrets.token_hex(32)
        logging.warning("FLASK_SECRET_KEY not set, using generated key. Set this in production!")

    # Configure OAuth using our custom implementation
    init_oauth_providers(app)

    # Register application blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(graphs_bp)
    app.register_blueprint(database_bp)

    @app.errorhandler(Exception)
    async def handle_oauth_error(error):
        """Handle OAuth-related errors gracefully"""
        # Check if it's an OAuth-related error
        if "token" in str(error).lower() or "oauth" in str(error).lower():
            logging.warning("OAuth error occurred: %s", error)
            session.clear()
            return redirect(url_for("auth.home"))

        # If it's an HTTPException (like abort(403)), re-raise so Quart handles it properly
        if isinstance(error, HTTPException):
            return error

        # For other errors, let them bubble up
        raise error

    @app.before_request
    async def block_static_directories():
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

    @app.context_processor
    def inject_google_tag_manager():
        """Inject Google Tag Manager ID into template context."""
        return {
            'google_tag_manager_id': os.getenv("GOOGLE_TAG_MANAGER_ID")
        }

    return app
