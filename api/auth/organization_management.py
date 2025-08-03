"""Organization management functions for text2sql API."""

import logging
from typing import Tuple, Optional, Dict, Any

from api.extensions import db


def extract_email_domain(email: str) -> str:
    """Extract domain from email address."""
    if not email or "@" not in email:
        return ""
    return email.split("@")[-1].lower()


def check_or_create_organization(user_email: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Check if organization exists for email domain, create if not.
    Returns (is_new_organization, organization_info)
    """
    domain = extract_email_domain(user_email)
    if not domain:
        logging.error("Invalid email domain for user: %s", user_email)
        return False, None

    try:
        organizations_graph = db.select_graph("Organizations")

        # Check if organization exists for this domain
        check_query = """
        MATCH (org:Organization {domain: $domain})
        RETURN org
        """

        result = organizations_graph.query(check_query, {"domain": domain})

        if result.result_set:
            # Organization exists
            organization = result.result_set[0][0]
            logging.info("Found existing organization for domain: %s", domain)
            return False, organization
        else:
            # Create new organization with first user as admin
            create_query = """
            CREATE (org:Organization {
                domain: $domain,
                name: $organization_name,
                created_at: timestamp(),
                admin_email: $admin_email
            })
            RETURN org
            """

            # Generate organization name from domain (e.g., example.com -> Example)
            organization_name = domain.split('.')[0].capitalize()

            result = organizations_graph.query(create_query, {
                "domain": domain,
                "organization_name": organization_name,
                "admin_email": user_email
            })

            if result.result_set:
                organization = result.result_set[0][0]
                logging.info("Created new organization for domain: %s", domain)
                return True, organization
            else:
                logging.error("Failed to create organization for domain: %s", domain)
                return False, None

    except Exception as e:
        logging.error("Error managing organization for domain %s: %s", domain, e)
        return False, None


def link_user_to_organization(user_email: str, organization_domain: str, is_admin: bool = False, is_pending: bool = False) -> bool:
    """
    Link a user to an organization.
    
    Args:
        user_email: The user's email
        organization_domain: The organization's domain
        is_admin: Whether the user should be an admin
        is_pending: Whether the user needs admin approval
    
    Returns:
        bool: Success status
    """
    try:
        organizations_graph = db.select_graph("Organizations")

        # Create the relationship between user and organization
        link_query = """
        MATCH (user:User {email: $user_email})
        MATCH (org:Organization {domain: $domain})
        MERGE (user)-[r:BELONGS_TO]->(org)
        SET r.is_admin = $is_admin,
            r.is_pending = $is_pending,
            r.joined_at = timestamp()
        RETURN user, org, r
        """

        result = organizations_graph.query(link_query, {
            "user_email": user_email,
            "domain": organization_domain,
            "is_admin": is_admin,
            "is_pending": is_pending
        })

        if result.result_set:
            logging.info("Linked user %s to organization %s (admin: %s, pending: %s)", 
                        user_email, organization_domain, is_admin, is_pending)
            return True
        else:
            logging.error("Failed to link user %s to organization %s", user_email, organization_domain)
            return False

    except Exception as e:
        logging.error("Error linking user %s to organization %s: %s", user_email, organization_domain, e)
        return False


def get_user_organization_status(user_email: str) -> Optional[Dict[str, Any]]:
    """
    Get user's organization status and details.
    
    Returns:
        Dict with organization info, user role, and pending status, or None if no organization
    """
    try:
        organizations_graph = db.select_graph("Organizations")

        query = """
        MATCH (user:User {email: $user_email})-[r:BELONGS_TO]->(org:Organization)
        RETURN org, r.is_admin as is_admin, r.is_pending as is_pending, r.joined_at as joined_at
        """

        result = organizations_graph.query(query, {"user_email": user_email})

        if result.result_set:
            org_data = result.result_set[0][0]
            is_admin = result.result_set[0][1]
            is_pending = result.result_set[0][2]
            joined_at = result.result_set[0][3]
            
            # Convert Node object to dictionary
            org_dict = {}
            if hasattr(org_data, 'properties'):
                org_dict = org_data.properties
            elif hasattr(org_data, '__dict__'):
                org_dict = {k: v for k, v in org_data.__dict__.items() if not k.startswith('_')}
            else:
                # Fallback for different Node implementations
                org_dict = dict(org_data) if org_data else {}

            return {
                "organization": org_dict,
                "is_admin": is_admin,
                "is_pending": is_pending,
                "joined_at": joined_at
            }
        else:
            return None
            
    except Exception as e:
        logging.error("Error getting organization status for user %s: %s", user_email, e)
        return None


def get_organization_users(organization_domain: str) -> list:
    """
    Get all users in an organization.
    
    Returns:
        List of user dictionaries with their roles and status
    """
    try:
        organizations_graph = db.select_graph("Organizations")

        query = """
        MATCH (user:User)-[r:BELONGS_TO]->(org:Organization {domain: $domain})
        RETURN user, r.is_admin as is_admin, r.is_pending as is_pending, r.joined_at as joined_at
        ORDER BY r.is_admin DESC, user.email ASC
        """

        result = organizations_graph.query(query, {"domain": organization_domain})

        users = []
        for row in result.result_set:
            user_data = row[0]
            is_admin = row[1]
            is_pending = row[2]
            joined_at = row[3]
            
            # Convert Node object to dictionary
            user_dict = {}
            if hasattr(user_data, 'properties'):
                user_dict = user_data.properties
            elif hasattr(user_data, '__dict__'):
                user_dict = {k: v for k, v in user_data.__dict__.items() if not k.startswith('_')}
            else:
                # Fallback for different Node implementations
                user_dict = dict(user_data) if user_data else {}

            users.append({
                "user": user_dict,
                "is_admin": is_admin,
                "is_pending": is_pending,
                "joined_at": joined_at
            })

        return users

    except Exception as e:
        logging.error("Error getting users for organization %s: %s", organization_domain, e)
        return []


def add_user_to_organization_by_email(admin_email: str, target_email: str, organization_domain: str) -> Tuple[bool, str]:
    """
    Add a user to organization by email (admin function).
    Creates a pending user entry that will be activated when they log in.
    
    Args:
        admin_email: The admin user's email
        target_email: The email of user to add
        organization_domain: The organization domain
    
    Returns:
        Tuple[bool, str]: (success, message)
    """
    try:
        # Validate admin permissions
        admin_status = get_user_organization_status(admin_email)
        if not admin_status or not admin_status.get("is_admin"):
            return False, "Unauthorized: Only organization admins can add users"

        if admin_status["organization"]["domain"] != organization_domain:
            return False, "Unauthorized: Admin can only add users to their own organization"

        # Validate target email domain matches organization
        target_domain = extract_email_domain(target_email)
        if target_domain != organization_domain:
            return False, f"Email domain {target_domain} does not match organization domain {organization_domain}"

        organizations_graph = db.select_graph("Organizations")

        # Create or update user with pending organization relationship
        query = """
        MATCH (org:Organization {domain: $domain})
        MERGE (user:User {email: $target_email})
        ON CREATE SET user.created_at = timestamp(), user.role = 'user'
        MERGE (user)-[r:BELONGS_TO]->(org)
        SET r.is_admin = false,
            r.is_pending = true,
            r.invited_by = $admin_email,
            r.invited_at = timestamp()
        RETURN user, r
        """

        result = organizations_graph.query(query, {
            "domain": organization_domain,
            "target_email": target_email,
            "admin_email": admin_email
        })

        if result.result_set:
            logging.info("Admin %s added user %s to organization %s (pending)", 
                        admin_email, target_email, organization_domain)
            return True, f"User {target_email} has been added to organization and will be activated when they log in"
        else:
            return False, "Failed to add user to organization"

    except Exception as e:
        logging.error("Error adding user %s to organization %s by admin %s: %s", 
                     target_email, organization_domain, admin_email, e)
        return False, f"Error adding user: {str(e)}"


def approve_pending_user(admin_email: str, target_email: str, organization_domain: str) -> Tuple[bool, str]:
    """
    Approve a pending user in the organization.
    
    Args:
        admin_email: The admin user's email
        target_email: The email of user to approve
        organization_domain: The organization domain
    
    Returns:
        Tuple[bool, str]: (success, message)
    """
    try:
        # Validate admin permissions
        admin_status = get_user_organization_status(admin_email)
        if not admin_status or not admin_status.get("is_admin"):
            return False, "Unauthorized: Only organization admins can approve users"

        if admin_status["organization"]["domain"] != organization_domain:
            return False, "Unauthorized: Admin can only approve users in their own organization"

        organizations_graph = db.select_graph("Organizations")

        # Update user's pending status
        query = """
        MATCH (user:User {email: $target_email})-[r:BELONGS_TO]->(org:Organization {domain: $domain})
        WHERE r.is_pending = true
        SET r.is_pending = false,
            r.approved_by = $admin_email,
            r.approved_at = timestamp()
        RETURN user, r
        """

        result = organizations_graph.query(query, {
            "target_email": target_email,
            "domain": organization_domain,
            "admin_email": admin_email
        })

        if result.result_set:
            # Also ensure the user has the correct default role
            update_user_role_direct(target_email, "user")
            logging.info("Admin %s approved user %s in organization %s", 
                        admin_email, target_email, organization_domain)
            return True, f"User {target_email} has been approved"
        else:
            return False, "User not found or not pending approval"

    except Exception as e:
        logging.error("Error approving user %s in organization %s by admin %s: %s", 
                     target_email, organization_domain, admin_email, e)
        return False, f"Error approving user: {str(e)}"


def get_pending_users(organization_domain: str) -> list:
    """
    Get all pending users for an organization.
    
    Returns:
        List of pending user dictionaries
    """
    try:
        organizations_graph = db.select_graph("Organizations")

        query = """
        MATCH (user:User)-[r:BELONGS_TO]->(org:Organization {domain: $domain})
        WHERE r.is_pending = true
        RETURN user, r.invited_by as invited_by, r.invited_at as invited_at
        ORDER BY r.invited_at DESC
        """

        result = organizations_graph.query(query, {"domain": organization_domain})

        pending_users = []
        for row in result.result_set:
            user_data = row[0]
            invited_by = row[1]
            invited_at = row[2]
            
            # Convert Node object to dictionary
            user_dict = {}
            if hasattr(user_data, 'properties'):
                user_dict = user_data.properties
            elif hasattr(user_data, '__dict__'):
                user_dict = {k: v for k, v in user_data.__dict__.items() if not k.startswith('_')}
            else:
                # Fallback for different Node implementations
                user_dict = dict(user_data) if user_data else {}

            pending_users.append({
                "user": user_dict,
                "invited_by": invited_by,
                "invited_at": invited_at
            })

        return pending_users

    except Exception as e:
        logging.error("Error getting pending users for organization %s: %s", organization_domain, e)
        return []


def update_user_role(admin_email: str, target_email: str, new_role: str, organization_domain: str) -> Tuple[bool, str]:
    """
    Update a user's role (admin function).
    
    Args:
        admin_email: The admin user's email
        target_email: The email of user whose role to update
        new_role: The new role to assign (e.g., 'user', 'admin', 'analyst', 'viewer')
        organization_domain: The organization domain
    
    Returns:
        Tuple[bool, str]: (success, message)
    """
    try:
        # Validate admin permissions
        admin_status = get_user_organization_status(admin_email)
        if not admin_status or not admin_status.get("is_admin"):
            return False, "Unauthorized: Only organization admins can update user roles"

        if admin_status["organization"]["domain"] != organization_domain:
            return False, "Unauthorized: Admin can only update roles in their own organization"

        # Validate role value
        allowed_roles = ['user', 'admin', 'analyst', 'viewer', 'manager']
        if new_role not in allowed_roles:
            return False, f"Invalid role '{new_role}'. Allowed roles: {', '.join(allowed_roles)}"

        organizations_graph = db.select_graph("Organizations")

        # Update user's role
        query = """
        MATCH (user:User {email: $target_email})-[r:BELONGS_TO]->(org:Organization {domain: $domain})
        WHERE r.is_pending = false
        SET user.role = $new_role,
            user.role_updated_by = $admin_email,
            user.role_updated_at = timestamp()
        RETURN user
        """

        result = organizations_graph.query(query, {
            "target_email": target_email,
            "domain": organization_domain,
            "new_role": new_role,
            "admin_email": admin_email
        })

        if result.result_set:
            logging.info("Admin %s updated role of user %s to %s in organization %s", 
                        admin_email, target_email, new_role, organization_domain)
            return True, f"User {target_email} role updated to {new_role}"
        else:
            return False, "User not found or not a member of the organization"

    except Exception as e:
        logging.error("Error updating role for user %s in organization %s by admin %s: %s", 
                     target_email, organization_domain, admin_email, e)
        return False, f"Error updating user role: {str(e)}"


def get_user_role(user_email: str) -> str:
    """
    Get a user's role.
    
    Args:
        user_email: The user's email
    
    Returns:
        str: The user's role, or 'user' as default
    """
    try:
        organizations_graph = db.select_graph("Organizations")

        query = """
        MATCH (user:User {email: $email})
        RETURN user.role as role
        """

        result = organizations_graph.query(query, {"email": user_email})

        if result.result_set and result.result_set[0][0]:
            return result.result_set[0][0]
        else:
            return 'user'  # Default role

    except Exception as e:
        logging.error("Error getting role for user %s: %s", user_email, e)
        return 'user'  # Default role on error


def update_user_role_direct(user_email: str, new_role: str) -> bool:
    """
    Update a user's role directly (internal function, no auth checks).
    Used for system operations like making first user admin.
    
    Args:
        user_email: The user's email
        new_role: The new role to assign
    
    Returns:
        bool: Success status
    """
    try:
        # Validate role value
        allowed_roles = ['user', 'admin', 'analyst', 'viewer', 'manager']
        if new_role not in allowed_roles:
            logging.error("Invalid role '%s' for user %s", new_role, user_email)
            return False

        organizations_graph = db.select_graph("Organizations")

        # Update user's role directly
        query = """
        MATCH (user:User {email: $email})
        SET user.role = $new_role,
            user.role_updated_at = timestamp()
        RETURN user
        """

        result = organizations_graph.query(query, {
            "email": user_email,
            "new_role": new_role
        })

        if result.result_set:
            logging.info("Updated role of user %s to %s", user_email, new_role)
            return True
        else:
            logging.warning("User %s not found when updating role to %s", user_email, new_role)
            return False

    except Exception as e:
        logging.error("Error updating role for user %s to %s: %s", user_email, new_role, e)
        return False
