"""This module contains the routes for the text2sql API."""

import json
import logging
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from functools import wraps

from dotenv import load_dotenv
from flask import Blueprint, Flask, Response, jsonify, render_template, request, stream_with_context, g
from flask import session, redirect, url_for
from flask_dance.contrib.google import make_google_blueprint, google
from flask_dance.contrib.github import make_github_blueprint, github
from flask_dance.consumer.storage.session import SessionStorage
from flask_dance.consumer import oauth_authorized

from api.agents import AnalysisAgent, RelevancyAgent, ResponseFormatterAgent
from api.constants import EXAMPLES
from api.extensions import db
from api.graph import find, get_db_description
from api.loaders.csv_loader import CSVLoader
from api.loaders.json_loader import JSONLoader
from api.loaders.postgres_loader import PostgresLoader
from api.loaders.odata_loader import ODataLoader

# Load environment variables from .env file
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Use the same delimiter as in the JavaScript
MESSAGE_DELIMITER = "|||FALKORDB_MESSAGE_BOUNDARY|||"

main = Blueprint("main", __name__)

def validate_and_cache_user():
    """
    Helper function to validate OAuth token and cache user info.
    Returns (user_info, is_authenticated) tuple.
    Supports both Google and GitHub OAuth.
    """
    # Check for cached user info from either provider
    user_info = session.get("user_info")
    token_validated_at = session.get("token_validated_at", 0)
    current_time = time.time()

    # Use cached user info if it's less than 15 minutes old
    if user_info and (current_time - token_validated_at) < 900:  # 15 minutes
        return user_info, True

    # Check Google OAuth first
    if google.authorized:
        try:
            resp = google.get("/oauth2/v2/userinfo")
            if resp.ok:
                google_user = resp.json()
                # Normalize user info structure
                user_info = {
                    "id": google_user.get("id"),
                    "name": google_user.get("name"),
                    "email": google_user.get("email"),
                    "picture": google_user.get("picture"),
                    "provider": "google"
                }
                session["user_info"] = user_info
                session["token_validated_at"] = current_time
                return user_info, True
        except Exception as e:
            logging.warning(f"Google OAuth validation error: {e}")

    # Check GitHub OAuth
    if github.authorized:
        try:
            # Get user profile
            resp = github.get("/user")
            if resp.ok:
                github_user = resp.json()
                
                # Get user email (GitHub may require separate call for email)
                email_resp = github.get("/user/emails")
                email = None
                if email_resp.ok:
                    emails = email_resp.json()
                    # Find primary email
                    for email_obj in emails:
                        if email_obj.get("primary", False):
                            email = email_obj.get("email")
                            break
                    # If no primary email found, use the first one
                    if not email and emails:
                        email = emails[0].get("email")
                
                # Normalize user info structure
                user_info = {
                    "id": str(github_user.get("id")),  # Convert to string for consistency
                    "name": github_user.get("name") or github_user.get("login"),
                    "email": email,
                    "picture": github_user.get("avatar_url"),
                    "provider": "github"
                }
                session["user_info"] = user_info
                session["token_validated_at"] = current_time
                return user_info, True
        except Exception as e:
            logging.warning(f"GitHub OAuth validation error: {e}")

    # If no valid authentication found, clear session
    session.clear()
    return None, False


def token_required(f):
    """Decorator to protect routes with token authentication"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_info, is_authenticated = validate_and_cache_user()

        if not is_authenticated:
            return jsonify(message="Unauthorized - Please log in"), 401

        g.user_id = user_info.get("id")
        if not g.user_id:
            session.clear()
            return jsonify(message="Unauthorized - Invalid user"), 401

        return f(*args, **kwargs)

    return decorated_function


app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "supersekrit")

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

# GitHub OAuth signal handler

@oauth_authorized.connect_via(github_bp)
def github_logged_in(blueprint, token):
    if not token:
        return False

    try:
        # Get user profile
        resp = github.get("/user")
        if resp.ok:
            github_user = resp.json()

            # Get user email (GitHub may require separate call for email)
            email_resp = github.get("/user/emails")
            email = None
            if email_resp.ok:
                emails = email_resp.json()
                # Find primary email
                for email_obj in emails:
                    if email_obj.get("primary", False):
                        email = email_obj.get("email")
                        break
                # If no primary email found, use the first one
                if not email and emails:
                    email = emails[0].get("email")

            # Normalize user info structure
            user_info = {
                "id": str(github_user.get("id")),  # Convert to string for consistency
                "name": github_user.get("name") or github_user.get("login"),
                "email": email,
                "picture": github_user.get("avatar_url"),
                "provider": "github"
            }
            session["user_info"] = user_info
            session["token_validated_at"] = time.time()
            return False  # Don't create default flask-dance entry in session

    except Exception as e:
        logging.error(f"GitHub OAuth signal error: {e}")

    return False


@app.errorhandler(Exception)
def handle_oauth_error(error):
    """Handle OAuth-related errors gracefully"""
    # Check if it's an OAuth-related error
    if "token" in str(error).lower() or "oauth" in str(error).lower():
        logging.warning(f"OAuth error occurred: {error}")
        session.clear()
        return redirect(url_for("home"))

    # For other errors, let them bubble up
    raise error


@app.route("/")
def home():
    """Home route"""
    user_info, is_authenticated = validate_and_cache_user()

    # If not authenticated through OAuth, check for any stale session data
    if not is_authenticated and not google.authorized and not github.authorized:
        session.pop("user_info", None)

    return render_template("chat.j2", is_authenticated=is_authenticated, user_info=user_info)


@app.route("/graphs")
@token_required
def graphs():
    """
    This route is used to list all the graphs that are available in the database.
    """
    user_id = g.user_id
    user_graphs = db.list_graphs()
    # Only include graphs that start with user_id + '_', and strip the prefix
    filtered_graphs = [graph[len(f"{user_id}_"):]
                       for graph in user_graphs if graph.startswith(f"{user_id}_")]
    return jsonify(filtered_graphs)


@app.route("/graphs", methods=["POST"])
@token_required
def load():
    """
    This route is used to load the graph data into the database.
    It expects either:
    - A JSON payload (application/json)
    - A File upload (multipart/form-data)
    - An XML payload (application/xml or text/xml)
    """
    content_type = request.content_type
    success, result = False, "Invalid content type"
    graph_id = ""

    # ✅ Handle JSON Payload
    if content_type.startswith("application/json"):
        data = request.get_json()
        if not data or "database" not in data:
            return jsonify({"error": "Invalid JSON data"}), 400

        graph_id = g.user_id + "_" + data["database"]
        success, result = JSONLoader.load(graph_id, data)

    # ✅ Handle XML Payload
    elif content_type.startswith("application/xml") or content_type.startswith("text/xml"):
        xml_data = request.data
        graph_id = ""
        success, result = ODataLoader.load(graph_id, xml_data)

    # ✅ Handle CSV Payload
    elif content_type.startswith("text/csv"):
        csv_data = request.data
        graph_id = ""
        success, result = CSVLoader.load(graph_id, csv_data)

    # ✅ Handle File Upload (FormData with JSON/XML)
    elif content_type.startswith("multipart/form-data"):
        if "file" not in request.files:
            return jsonify({"error": "No file uploaded"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "Empty file"}), 400

        # ✅ Check if file is JSON
        if file.filename.endswith(".json"):
            try:
                data = json.load(file)
                graph_id = g.user_id + "_" + data.get("database", "")
                success, result = JSONLoader.load(graph_id, data)
            except json.JSONDecodeError:
                return jsonify({"error": "Invalid JSON file"}), 400

        # ✅ Check if file is XML
        elif file.filename.endswith(".xml"):
            xml_data = file.read().decode("utf-8")  # Convert bytes to string
            graph_id = g.user_id + "_" + file.filename.replace(".xml", "")
            success, result = ODataLoader.load(graph_id, xml_data)

        # ✅ Check if file is csv
        elif file.filename.endswith(".csv"):
            csv_data = file.read().decode("utf-8")  # Convert bytes to string
            graph_id = g.user_id + "_" + file.filename.replace(".csv", "")
            success, result = CSVLoader.load(graph_id, csv_data)

        else:
            return jsonify({"error": "Unsupported file type"}), 415
    else:
        return jsonify({"error": "Unsupported Content-Type"}), 415

    # ✅ Return the final response
    if success:
        return jsonify({"message": result, "graph_id": graph_id})

    return jsonify({"error": result}), 400


@app.route("/graphs/<string:graph_id>", methods=["POST"])
@token_required
def query(graph_id: str):
    """
    text2sql
    """
    graph_id =  g.user_id + "_" + graph_id.strip()
    request_data = request.get_json()
    queries_history = request_data.get("chat")
    result_history = request_data.get("result")
    instructions = request_data.get("instructions")
    if not queries_history:
        return jsonify({"error": "Invalid or missing JSON data"}), 400

    logging.info("User Query: %s", queries_history[-1])

    # Create a generator function for streaming
    def generate():
        agent_rel = RelevancyAgent(queries_history, result_history)
        agent_an = AnalysisAgent(queries_history, result_history)

        step = {"type": "reasoning_step", "message": "Step 1: Analyzing user query and generating SQL..."}
        yield json.dumps(step) + MESSAGE_DELIMITER
        db_description, db_url = get_db_description(graph_id)  # Ensure the database description is loaded

        logging.info("Calling to relvancy agent with query: %s", queries_history[-1])
        answer_rel = agent_rel.get_answer(queries_history[-1], db_description)
        if answer_rel["status"] != "On-topic":
            step = {
                "type": "followup_questions",
                "message": "Off topic question: " + answer_rel["reason"],
            }
            logging.info("SQL Fail reason: %s", answer_rel["reason"])
            yield json.dumps(step) + MESSAGE_DELIMITER
        else:
            # Use a thread pool to enforce timeout
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(find, graph_id, queries_history, db_description)
                try:
                    _, result, _ = future.result(timeout=120)
                except FuturesTimeoutError:
                    yield json.dumps(
                        {
                            "type": "error",
                            "message": ("Timeout error while finding tables relevant to "
                                       "your request."),
                        }
                    ) + MESSAGE_DELIMITER
                    return
                except Exception as e:
                    logging.info("Error in find function: %s", e)
                    yield json.dumps(
                        {"type": "error", "message": "Error in find function"}
                    ) + MESSAGE_DELIMITER
                    return

            logging.info("Calling to analysis agent with query: %s", queries_history[-1])
            answer_an = agent_an.get_analysis(
                queries_history[-1], result, db_description, instructions
            )

            logging.info("SQL Result: %s", answer_an['sql_query'])
            yield json.dumps(
                {
                    "type": "final_result",
                    "data": answer_an["sql_query"],
                    "conf": answer_an["confidence"],
                    "miss": answer_an["missing_information"],
                    "amb": answer_an["ambiguities"],
                    "exp": answer_an["explanation"],
                    "is_valid": answer_an["is_sql_translatable"],
                }
            ) + MESSAGE_DELIMITER

            # If the SQL query is valid, execute it using the postgress database db_url
            if answer_an["is_sql_translatable"]:
                # Check if this is a destructive operation that requires confirmation
                sql_query = answer_an["sql_query"]
                sql_type = sql_query.strip().split()[0].upper() if sql_query else ""

                if sql_type in ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER', 'TRUNCATE']:
                    # This is a destructive operation - ask for user confirmation
                    confirmation_message = f"""⚠️ DESTRUCTIVE OPERATION DETECTED ⚠️

The generated SQL query will perform a **{sql_type}** operation:

SQL:
{sql_query}

What this will do:
"""
                    if sql_type == 'INSERT':
                        confirmation_message += "• Add new data to the database"
                    elif sql_type == 'UPDATE':
                        confirmation_message += "• Modify existing data in the database"
                    elif sql_type == 'DELETE':
                        confirmation_message += "• **PERMANENTLY DELETE** data from the database"
                    elif sql_type == 'DROP':
                        confirmation_message += "• **PERMANENTLY DELETE** entire tables or database objects"
                    elif sql_type == 'CREATE':
                        confirmation_message += "• Create new tables or database objects"
                    elif sql_type == 'ALTER':
                        confirmation_message += "• Modify the structure of existing tables"
                    elif sql_type == 'TRUNCATE':
                        confirmation_message += "• **PERMANENTLY DELETE ALL DATA** from specified tables"

                    confirmation_message += """
                    
⚠️ WARNING: This operation will make changes to your database and may be irreversible.
"""
                    
                    yield json.dumps(
                        {
                            "type": "destructive_confirmation",
                            "message": confirmation_message,
                            "sql_query": sql_query,
                            "operation_type": sql_type
                        }
                    ) + MESSAGE_DELIMITER
                    return  # Stop here and wait for user confirmation
                
                try:
                    step = {"type": "reasoning_step", "message": "Step 2: Executing SQL query"}
                    yield json.dumps(step) + MESSAGE_DELIMITER

                    # Check if this query modifies the database schema
                    is_schema_modifying, operation_type = PostgresLoader.is_schema_modifying_query(sql_query)

                    query_results = PostgresLoader.execute_sql_query(answer_an["sql_query"], db_url)
                    yield json.dumps(
                        {
                            "type": "query_result",
                            "data": query_results,
                        }
                    ) + MESSAGE_DELIMITER

                    # If schema was modified, refresh the graph
                    if is_schema_modifying:
                        step = {"type": "reasoning_step", "message": "Step 3: Schema change detected - refreshing graph..."}
                        yield json.dumps(step) + MESSAGE_DELIMITER

                        refresh_success, refresh_message = PostgresLoader.refresh_graph_schema(graph_id, db_url)
                        
                        if refresh_success:
                            yield json.dumps(
                                {
                                    "type": "schema_refresh",
                                    "message": f"✅ Schema change detected ({operation_type} operation)\n\n🔄 Graph schema has been automatically refreshed with the latest database structure.",
                                    "refresh_status": "success"
                                }
                            ) + MESSAGE_DELIMITER
                        else:
                            yield json.dumps(
                                {
                                    "type": "schema_refresh",
                                    "message": f"⚠️ Schema was modified but graph refresh failed: {refresh_message}",
                                    "refresh_status": "failed"
                                }
                            ) + MESSAGE_DELIMITER

                    # Generate user-readable response using AI
                    step_num = "4" if is_schema_modifying else "3"
                    step = {"type": "reasoning_step", "message": f"Step {step_num}: Generating user-friendly response"}
                    yield json.dumps(step) + MESSAGE_DELIMITER

                    response_agent = ResponseFormatterAgent()
                    user_readable_response = response_agent.format_response(
                        user_query=queries_history[-1],
                        sql_query=answer_an["sql_query"],
                        query_results=query_results,
                        db_description=db_description
                    )

                    yield json.dumps(
                        {
                            "type": "ai_response",
                            "message": user_readable_response,
                        }
                    ) + MESSAGE_DELIMITER

                except Exception as e:
                    logging.error("Error executing SQL query: %s", e)
                    yield json.dumps(
                        {"type": "error", "message": str(e)}
                    ) + MESSAGE_DELIMITER

    return Response(stream_with_context(generate()), content_type="application/json")


@app.route("/graphs/<string:graph_id>/confirm", methods=["POST"])
@token_required
def confirm_destructive_operation(graph_id: str):
    """
    Handle user confirmation for destructive SQL operations
    """
    graph_id = g.user_id + "_" + graph_id.strip()
    request_data = request.get_json()
    confirmation = request_data.get("confirmation", "").strip().upper()
    sql_query = request_data.get("sql_query", "")
    queries_history = request_data.get("chat", [])

    if not sql_query:
        return jsonify({"error": "No SQL query provided"}), 400

    # Create a generator function for streaming the confirmation response
    def generate_confirmation():
        if confirmation == "CONFIRM":
            try:
                db_description, db_url = get_db_description(graph_id)

                step = {"type": "reasoning_step", "message": "Step 2: Executing confirmed SQL query"}
                yield json.dumps(step) + MESSAGE_DELIMITER

                # Check if this query modifies the database schema
                is_schema_modifying, operation_type = PostgresLoader.is_schema_modifying_query(sql_query)

                query_results = PostgresLoader.execute_sql_query(sql_query, db_url)
                yield json.dumps(
                    {
                        "type": "query_result",
                        "data": query_results,
                    }
                ) + MESSAGE_DELIMITER

                # If schema was modified, refresh the graph
                if is_schema_modifying:
                    step = {"type": "reasoning_step", "message": "Step 3: Schema change detected - refreshing graph..."}
                    yield json.dumps(step) + MESSAGE_DELIMITER

                    refresh_success, refresh_message = PostgresLoader.refresh_graph_schema(graph_id, db_url)
                    
                    if refresh_success:
                        yield json.dumps(
                            {
                                "type": "schema_refresh",
                                "message": f"✅ Schema change detected ({operation_type} operation)\n\n🔄 Graph schema has been automatically refreshed with the latest database structure.",
                                "refresh_status": "success"
                            }
                        ) + MESSAGE_DELIMITER
                    else:
                        yield json.dumps(
                            {
                                "type": "schema_refresh",
                                "message": f"⚠️ Schema was modified but graph refresh failed: {refresh_message}",
                                "refresh_status": "failed"
                            }
                        ) + MESSAGE_DELIMITER

                # Generate user-readable response using AI
                step_num = "4" if is_schema_modifying else "3"
                step = {"type": "reasoning_step", "message": f"Step {step_num}: Generating user-friendly response"}
                yield json.dumps(step) + MESSAGE_DELIMITER

                response_agent = ResponseFormatterAgent()
                user_readable_response = response_agent.format_response(
                    user_query=queries_history[-1] if queries_history else "Destructive operation",
                    sql_query=sql_query,
                    query_results=query_results,
                    db_description=db_description
                )

                yield json.dumps(
                    {
                        "type": "ai_response",
                        "message": user_readable_response,
                    }
                ) + MESSAGE_DELIMITER

            except Exception as e:
                logging.error("Error executing confirmed SQL query: %s", e)
                yield json.dumps(
                    {"type": "error", "message": f"Error executing query: {str(e)}"}
                ) + MESSAGE_DELIMITER
        else:
            # User cancelled or provided invalid confirmation
            yield json.dumps(
                {
                    "type": "operation_cancelled",
                    "message": "Operation cancelled. The destructive SQL query was not executed."
                }
            ) + MESSAGE_DELIMITER

    return Response(stream_with_context(generate_confirmation()), content_type="application/json")

@app.route("/login")
def login_google():
    if not google.authorized:
        return redirect(url_for("google.login"))

    try:
        resp = google.get("/oauth2/v2/userinfo")
        if resp.ok:
            google_user = resp.json()
            # Normalize user info structure
            user_info = {
                "id": google_user.get("id"),
                "name": google_user.get("name"),
                "email": google_user.get("email"),
                "picture": google_user.get("picture"),
                "provider": "google"
            }
            session["user_info"] = user_info
            session["token_validated_at"] = time.time()
            return redirect(url_for("home"))
        else:
            # OAuth token might be expired, redirect to login
            session.clear()
            return redirect(url_for("google.login"))
    except Exception as e:
        logging.error("Google login error: %s", e)
        session.clear()
        return redirect(url_for("google.login"))




@app.route("/logout")
def logout():
    session.clear()

    # Revoke Google OAuth token if authorized
    if google.authorized:
        try:
            google.get(
                "https://accounts.google.com/o/oauth2/revoke",
                params={"token": google.access_token}
            )
        except Exception as e:
            logging.warning("Error revoking Google token: %s", e)

    # Revoke GitHub OAuth token if authorized
    if github.authorized:
        try:
            # GitHub doesn't have a simple revoke endpoint like Google
            # The token will expire naturally or can be revoked from GitHub settings
            pass
        except Exception as e:
            logging.warning("Error with GitHub token cleanup: %s", e)

    return redirect(url_for("home"))

@app.route("/graphs/<string:graph_id>/refresh", methods=["POST"])
@token_required
def refresh_graph_schema(graph_id: str):
    """
    Manually refresh the graph schema from the database.
    This endpoint allows users to manually trigger a schema refresh
    if they suspect the graph is out of sync with the database.
    """
    graph_id = g.user_id + "_" + graph_id.strip()
    
    try:
        # Get database connection details
        db_description, db_url = get_db_description(graph_id)
        
        if not db_url or db_url == "No URL available for this database.":
            return jsonify({
                "success": False, 
                "error": "No database URL found for this graph"
            }), 400

        # Perform schema refresh
        success, message = PostgresLoader.refresh_graph_schema(graph_id, db_url)

        if success:
            return jsonify({
                "success": True,
                "message": f"Graph schema refreshed successfully. {message}"
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": f"Failed to refresh schema: {message}"
            }), 500

    except Exception as e:
        logging.error("Error in manual schema refresh: %s", e)
        return jsonify({
            "success": False,
            "error": f"Error refreshing schema: {str(e)}"
        }), 500

@app.route("/database", methods=["POST"])
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
    try:
        # Check for Postgres URL
        if url.startswith("postgres://") or url.startswith("postgresql://"):
            try:
                # Attempt to connect/load using the loader
                success, result = PostgresLoader.load(g.user_id, url)
                if success:
                    return jsonify({"success": True, "message": result}), 200
                else:
                    return jsonify({"success": False, "error": result}), 400
            except Exception as e:
                return jsonify({"success": False, "error": str(e)}), 500
        else:
            return jsonify({"success": False, "error": "Invalid Postgres URL"}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.register_blueprint(main)
    app.run(debug=True)
