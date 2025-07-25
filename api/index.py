"""This module contains the routes for the text2sql API."""

import json
import logging
import os
import random
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from functools import wraps

from dotenv import load_dotenv
from flask import Blueprint, Flask, Response, jsonify, render_template, request, stream_with_context, g
from flask import session, redirect, url_for
from flask_dance.contrib.google import make_google_blueprint, google

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

SECRET_TOKEN = os.getenv("SECRET_TOKEN")
SECRET_TOKEN_ERP = os.getenv("SECRET_TOKEN_ERP")


def token_required(f):
    """Decorator to protect routes with token authentication"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_info = session.get("google_user")
        if user_info:
            g.user_id = user_info.get("id")
        else:
            return jsonify(message="Unauthorized"), 401
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


@app.route("/")
def home():
    """Home route"""
    is_authenticated = "google_oauth_token" in session
    if is_authenticated:
        resp = google.get("/oauth2/v2/userinfo")
        if resp.ok:
            user_info = resp.json()
            session["google_user"] = user_info
    return render_template("chat.j2", is_authenticated=is_authenticated)


@app.route("/graphs")
@token_required  # Apply token authentication decorator
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
@token_required  # Apply token authentication decorator
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
@token_required  # Apply token authentication decorator
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

        step = {"type": "reasoning_step", "message": "Step 1: Analyzing the user query"}
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

            step = {"type": "reasoning_step", "message": "Step 2: Generating SQL query"}
            yield json.dumps(step) + MESSAGE_DELIMITER
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
                try:
                    step = {"type": "reasoning_step", "message": "Step 3: Executing SQL query"}
                    yield json.dumps(step) + MESSAGE_DELIMITER

                    query_results = PostgresLoader.execute_sql_query(answer_an["sql_query"], db_url)
                    yield json.dumps(
                        {
                            "type": "query_result",
                            "data": query_results,
                        }
                    ) + MESSAGE_DELIMITER

                    # Generate user-readable response using AI
                    step = {"type": "reasoning_step", "message": "Step 4: Generating user-friendly response"}
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


@app.route("/suggestions")
@token_required  # Apply token authentication decorator
def suggestions():
    """
    This route returns 3 random suggestions from the examples data for the chat interface.
    It takes graph_id as a query parameter and returns examples specific to that graph.
    If no examples exist for the graph, returns an empty list.
    """
    try:
        # Get graph_id from query parameters
        graph_id = request.args.get("graph_id", "")

        if not graph_id:
            return jsonify([]), 400

        # Check if graph has specific examples
        if graph_id in EXAMPLES:
            graph_examples = EXAMPLES[graph_id]
            # Return up to 3 examples, or all if less than 3
            suggestion_questions = random.sample(graph_examples, min(3, len(graph_examples)))
            return jsonify(suggestion_questions)

        # If graph doesn't exist in EXAMPLES, return empty list
        return jsonify([])

    except Exception as e:
        logging.error("Error fetching suggestions: %s", e)
        return jsonify([]), 500

@app.route("/login")
def login_google():
    if not google.authorized:
        return redirect(url_for("google.login"))
    resp = google.get("/oauth2/v2/userinfo")
    if resp.ok:
        user_info = resp.json()
        session["google_user"] = user_info
        # You can set your own token/session logic here
        return redirect(url_for("home"))
    return "Could not fetch your information from Google.", 400


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/database", methods=["POST"])
@token_required  # Apply token authentication decorator
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
