"""Organization management routes for the text2sql API."""

import logging

from flask import Blueprint, request, jsonify
from api.auth.user_management import validate_and_cache_user, token_required
from api.auth.organization_management import (
    get_user_organization_status,
    get_organization_users,
    add_user_to_organization_by_email,
    approve_pending_user,
    get_pending_users,
    extract_email_domain
)

organization_bp = Blueprint("organization", __name__, url_prefix="/api/organization")


@organization_bp.route("/status", methods=["GET"])
@token_required
def get_organization_status():
    """Get current user's organization status."""
    try:
        user_info, is_authenticated = validate_and_cache_user()
        if not is_authenticated:
            return jsonify({"error": "Unauthorized"}), 401

        user_email = user_info.get("email")
        if not user_email:
            return jsonify({"error": "User email not found"}), 400

        status = get_user_organization_status(user_email)
        if status:
            from api.auth.organization_management import get_user_role
            user_role = get_user_role(user_email)

            return jsonify({
                "has_organization": True,
                "organization": {
                    "domain": status["organization"]["domain"],
                    "name": status["organization"]["name"],
                    "created_at": status["organization"]["created_at"]
                },
                "user_role": {
                    "is_admin": status["is_admin"],
                    "is_pending": status["is_pending"],
                    "joined_at": status["joined_at"],
                    "role": user_role
                }
            }), 200
        else:
            return jsonify({
                "has_organization": False,
                "message": "User is not part of any organization"
            }), 200

    except Exception as e:
        logging.error("Error getting organization status: %s", e)
        return jsonify({"error": "Internal server error"}), 500


@organization_bp.route("/users", methods=["GET"])
@token_required
def get_organization_members():
    """Get all users in the current user's organization (admin only)."""
    try:
        user_info, is_authenticated = validate_and_cache_user()
        if not is_authenticated:
            return jsonify({"error": "Unauthorized"}), 401

        user_email = user_info.get("email")
        if not user_email:
            return jsonify({"error": "User email not found"}), 400

        # Check if user is admin
        status = get_user_organization_status(user_email)
        if not status or not status.get("is_admin"):
            return jsonify({"error": "Unauthorized: Admin access required"}), 403

        organization_domain = status["organization"]["domain"]
        users = get_organization_users(organization_domain)

        # Format response
        formatted_users = []
        for user_data in users:
            formatted_users.append({
                "email": user_data["user"]["email"],
                "first_name": user_data["user"].get("first_name", ""),
                "last_name": user_data["user"].get("last_name", ""),
                "role": user_data["user"].get("role", "user"),
                "is_admin": user_data["is_admin"],
                "is_pending": user_data["is_pending"],
                "joined_at": user_data["joined_at"]
            })

        return jsonify({
            "organization_domain": organization_domain,
            "users": formatted_users
        }), 200

    except Exception as e:
        logging.error("Error getting organization users: %s", e)
        return jsonify({"error": "Internal server error"}), 500


@organization_bp.route("/pending", methods=["GET"])
@token_required
def get_pending_organization_users():
    """Get pending users in the organization (admin only)."""
    try:
        user_info, is_authenticated = validate_and_cache_user()
        if not is_authenticated:
            return jsonify({"error": "Unauthorized"}), 401

        user_email = user_info.get("email")
        if not user_email:
            return jsonify({"error": "User email not found"}), 400

        # Check if user is admin
        status = get_user_organization_status(user_email)
        if not status or not status.get("is_admin"):
            return jsonify({"error": "Unauthorized: Admin access required"}), 403

        organization_domain = status["organization"]["domain"]
        pending_users = get_pending_users(organization_domain)

        # Format response
        formatted_pending = []
        for user_data in pending_users:
            formatted_pending.append({
                "email": user_data["user"]["email"],
                "first_name": user_data["user"].get("first_name", ""),
                "last_name": user_data["user"].get("last_name", ""),
                "invited_by": user_data["invited_by"],
                "invited_at": user_data["invited_at"]
            })

        return jsonify({
            "organization_domain": organization_domain,
            "pending_users": formatted_pending
        }), 200

    except Exception as e:
        logging.error("Error getting pending users: %s", e)
        return jsonify({"error": "Internal server error"}), 500


@organization_bp.route("/add-user", methods=["POST"])
@token_required
def add_user_to_organization():
    """Add a user to the organization by email (admin only)."""
    try:
        user_info, is_authenticated = validate_and_cache_user()
        if not is_authenticated:
            return jsonify({"error": "Unauthorized"}), 401

        admin_email = user_info.get("email")
        if not admin_email:
            return jsonify({"error": "User email not found"}), 400

        # Check if user is admin
        status = get_user_organization_status(admin_email)
        if not status or not status.get("is_admin"):
            return jsonify({"error": "Unauthorized: Admin access required"}), 403

        # Get request data
        data = request.get_json()
        if not data or "email" not in data:
            return jsonify({"error": "Email is required"}), 400

        target_email = data["email"].strip().lower()
        if not target_email:
            return jsonify({"error": "Valid email is required"}), 400

        organization_domain = status["organization"]["domain"]

        # Validate email domain matches organization
        target_domain = extract_email_domain(target_email)
        if target_domain != organization_domain:
            return jsonify({
                "error": f"Email domain {target_domain} does not match organization domain {organization_domain}"
            }), 400


        # Pass first_name and last_name if present
        first_name = data.get("first_name", "")
        last_name = data.get("last_name", "")

        success, message = add_user_to_organization_by_email(
            admin_email, target_email, organization_domain, first_name=first_name, last_name=last_name
        )

        if success:
            return jsonify({"message": message}), 200
        else:
            return jsonify({"error": message}), 400

    except Exception as e:
        logging.error("Error adding user to organization: %s", e)
        return jsonify({"error": "Internal server error"}), 500


@organization_bp.route("/approve-user", methods=["POST"])
@token_required
def approve_user_in_organization():
    """Approve a pending user in the organization (admin only)."""
    try:
        user_info, is_authenticated = validate_and_cache_user()
        if not is_authenticated:
            return jsonify({"error": "Unauthorized"}), 401

        admin_email = user_info.get("email")
        if not admin_email:
            return jsonify({"error": "User email not found"}), 400

        # Check if user is admin
        status = get_user_organization_status(admin_email)
        if not status or not status.get("is_admin"):
            return jsonify({"error": "Unauthorized: Admin access required"}), 403

        # Get request data
        data = request.get_json()
        if not data or "email" not in data:
            return jsonify({"error": "Email is required"}), 400

        target_email = data["email"].strip().lower()
        if not target_email:
            return jsonify({"error": "Valid email is required"}), 400

        organization_domain = status["organization"]["domain"]

        # Approve user
        success, message = approve_pending_user(
            admin_email, target_email, organization_domain
        )

        if success:
            return jsonify({"message": message}), 200
        else:
            return jsonify({"error": message}), 400

    except Exception as e:
        logging.error("Error approving user: %s", e)
        return jsonify({"error": "Internal server error"}), 500


@organization_bp.route("/update-role", methods=["POST"])
@token_required
def update_user_role_endpoint():
    """Update a user's role in the organization (admin only)"""
    try:
        from api.auth.user_management import validate_and_cache_user
        from api.auth.organization_management import get_user_organization_status, update_user_role

        user_info, is_authenticated = validate_and_cache_user()
        if not is_authenticated:
            return jsonify({"error": "Authentication required"}), 401

        admin_email = user_info["email"]

        # Get request data
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON data required"}), 400

        target_email = data.get("target_email")
        new_role = data.get("new_role")

        if not target_email or not new_role:
            return jsonify({"error": "target_email and new_role are required"}), 400

        # Get admin's organization status
        status = get_user_organization_status(admin_email)
        if not status:
            return jsonify({"error": "User not in any organization"}), 400

        organization_domain = status["organization"]["domain"]

        # Update user role
        success, message = update_user_role(
            admin_email, target_email, new_role, organization_domain
        )

        if success:
            return jsonify({"message": message}), 200
        else:
            return jsonify({"error": message}), 400

    except Exception as e:
        logging.error("Error updating user role: %s", e)
        return jsonify({"error": "Internal server error"}), 500


@organization_bp.route("/user-role/<email>", methods=["GET"])
@token_required
def get_user_role_endpoint(email):
    """Get a user's role"""
    try:
        from api.auth.organization_management import get_user_role

        role = get_user_role(email)
        return jsonify({"email": email, "role": role}), 200

    except Exception as e:
        logging.error("Error getting user role: %s", e)
        return jsonify({"error": "Internal server error"}), 500
