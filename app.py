"""
This module contains the application factory function.
"""

from flask import Flask
from text2sql.config import Config
# from text2sql.extensions import db  # Import extensions
from text2sql.routes import init_routes  # Import routes

def create_app(config_class=Config):
    """Application factory function"""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    # db.init_app(app)
    # migrate.init_app(app, db)

    # Register routes
    init_routes(app)

    return app
