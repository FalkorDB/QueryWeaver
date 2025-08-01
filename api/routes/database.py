"""Database connection routes for the text2sql API."""

from flask import Blueprint, jsonify, request, g

from api.auth.user_management import token_required
from api.loaders.postgres_loader import PostgresLoader

database_bp = Blueprint("database", __name__)


@database_bp.route("/database", methods=["POST"])
@token_required
def connect_database():
    """
    Accepts a JSON payload with a Postgres URL and attempts to connect.
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
        # Check for Postgres URL
        if url.startswith("postgres://") or url.startswith("postgresql://"):
            try:
                # Attempt to connect/load using the loader
                success, result = PostgresLoader.load(g.user_id, url)
                if success:
                    return jsonify({"success": True, "message": result}), 200

                return jsonify({"success": False, "error": result}), 400
            except (ValueError, ConnectionError) as e:
                return jsonify({"success": False, "error": str(e)}), 500

        return jsonify({"success": False, "error": "Invalid Postgres URL"}), 400
    except (ValueError, TypeError) as e:
        return jsonify({"success": False, "error": str(e)}), 500
