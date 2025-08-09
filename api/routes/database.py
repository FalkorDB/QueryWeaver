"""Database connection routes for the text2sql API."""
import logging
from flask import Blueprint, jsonify, request, g

from api.auth.user_management import token_required
from api.loaders.postgres_loader import PostgresLoader
from api.loaders.mysql_loader import MySQLLoader

database_bp = Blueprint("database", __name__)


@database_bp.route("/database", methods=["POST"])
@token_required
def connect_database():
    """
    Accepts a JSON payload with a database URL and attempts to connect.
    Supports both PostgreSQL and MySQL databases.
    Returns success or error message.
    """
    data = request.get_json()
    url = data.get("url") if data else None
    if not url:
        return jsonify({"success": False, "error": "No URL provided"}), 400

    # Validate URL format
    if not isinstance(url, str) or len(url.strip()) == 0:
        return jsonify({"success": False, "error": "Invalid URL format"}), 400

    try:
        success = False
        result = ""
        
        # Check for PostgreSQL URL
        if url.startswith("postgres://") or url.startswith("postgresql://"):
            try:
                # Attempt to connect/load using the PostgreSQL loader
                success, result = PostgresLoader.load(g.user_id, url)
            except (ValueError, ConnectionError) as e:
                logging.error("PostgreSQL connection error: %s", str(e))
                return jsonify({"success": False, "error": "Failed to connect to PostgreSQL database"}), 500
        
        # Check for MySQL URL
        elif url.startswith("mysql://"):
            try:
                # Attempt to connect/load using the MySQL loader
                success, result = MySQLLoader.load(g.user_id, url)
            except (ValueError, ConnectionError) as e:
                logging.error("MySQL connection error: %s", str(e))
                return jsonify({"success": False, "error": "Failed to connect to MySQL database"}), 500
        
        else:
            return jsonify({"success": False, "error": "Invalid database URL. Supported formats: postgresql:// or mysql://"}), 400

        if success:
            return jsonify({"success": True,
                            "message": "Database connected successfully"}), 200

        # Don't return detailed error messages to prevent information exposure
        logging.error("Database loader failed: %s", result)
        return jsonify({"success": False, "error": "Failed to load database schema"}), 400
        
    except (ValueError, TypeError) as e:
        logging.error("Unexpected error in database connection: %s", str(e))
        return jsonify({"success": False, "error": "Internal server error"}), 500
