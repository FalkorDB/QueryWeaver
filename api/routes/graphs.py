"""Graph-related routes for the text2sql API."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError

from flask import Blueprint, jsonify, request, Response, stream_with_context, g

from api.agents import AnalysisAgent, RelevancyAgent, ResponseFormatterAgent
from api.auth.user_management import token_required
from api.extensions import db
from api.graph import find, get_db_description
from api.loaders.csv_loader import CSVLoader
from api.loaders.json_loader import JSONLoader
from api.loaders.postgres_loader import PostgresLoader
from api.loaders.mysql_loader import MySQLLoader
from api.loaders.odata_loader import ODataLoader

# Use the same delimiter as in the JavaScript
MESSAGE_DELIMITER = "|||FALKORDB_MESSAGE_BOUNDARY|||"

graphs_bp = Blueprint("graphs", __name__, url_prefix="/graphs")

def get_database_type_and_loader(db_url: str):
    """
    Determine the database type from URL and return appropriate loader class.
    
    Args:
        db_url: Database connection URL
        
    Returns:
        tuple: (database_type, loader_class)
    """
    if not db_url or db_url == "No URL available for this database.":
        return None, None

    db_url_lower = db_url.lower()

    if db_url_lower.startswith('postgresql://') or db_url_lower.startswith('postgres://'):
        return 'postgresql', PostgresLoader
    elif db_url_lower.startswith('mysql://'):
        return 'mysql', MySQLLoader
    else:
        # Default to PostgresLoader for backward compatibility
        return 'postgresql', PostgresLoader

def sanitize_query(query: str) -> str:
    """Sanitize the query to prevent injection attacks."""
    return query.replace('\n', ' ').replace('\r', ' ')[:500]

@graphs_bp.route("")
@token_required
def list_graphs():
    """
    This route is used to list all the graphs that are available in the database.
    """
    user_id = g.user_id
    user_graphs = db.list_graphs()
    # Only include graphs that start with user_id + '_', and strip the prefix
    filtered_graphs = [graph[len(f"{user_id}_"):]
                       for graph in user_graphs if graph.startswith(f"{user_id}_")]
    return jsonify(filtered_graphs)


@graphs_bp.route("", methods=["POST"])
@token_required
def load_graph():
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

    # # ✅ Handle XML Payload
    # elif content_type.startswith("application/xml") or content_type.startswith("text/xml"):
    #     xml_data = request.data
    #     graph_id = ""
    #     success, result = ODataLoader.load(graph_id, xml_data)

    # # ✅ Handle CSV Payload
    # elif content_type.startswith("text/csv"):
    #     csv_data = request.data
    #     graph_id = ""
    #     success, result = CSVLoader.load(graph_id, csv_data)

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
        return jsonify({"message": "Graph loaded successfully", "graph_id": graph_id})

    # Log detailed error but return generic message to user
    logging.error("Graph loading failed: %s", str(result)[:100])
    return jsonify({"error": "Failed to load graph data"}), 400


@graphs_bp.route("/<string:graph_id>", methods=["POST"])
@token_required
def query_graph(graph_id: str):
    """
    text2sql
    """
    # Input validation
    if not graph_id or not isinstance(graph_id, str):
        return jsonify({"error": "Invalid graph_id"}), 400

    # Sanitize graph_id to prevent injection
    graph_id = graph_id.strip()[:100]  # Limit length and strip whitespace
    if not graph_id:
        return jsonify({"error": "Invalid graph_id"}), 400

    graph_id = g.user_id + "_" + graph_id
    request_data = request.get_json()

    if not request_data:
        return jsonify({"error": "No JSON data provided"}), 400

    queries_history = request_data.get("chat")
    result_history = request_data.get("result")
    instructions = request_data.get("instructions")

    if not queries_history or not isinstance(queries_history, list):
        return jsonify({"error": "Invalid or missing chat history"}), 400

    if len(queries_history) == 0:
        return jsonify({"error": "Empty chat history"}), 400

    logging.info("User Query: %s", sanitize_query(queries_history[-1]))

    # Create a generator function for streaming
    def generate():
        agent_rel = RelevancyAgent(queries_history, result_history)
        agent_an = AnalysisAgent(queries_history, result_history)

        step = {"type": "reasoning_step",
                "message": "Step 1: Analyzing user query and generating SQL..."}
        yield json.dumps(step) + MESSAGE_DELIMITER
        # Ensure the database description is loaded
        db_description, db_url = get_db_description(graph_id)

        # Determine database type and get appropriate loader
        db_type, loader_class = get_database_type_and_loader(db_url)

        if not loader_class:
            yield json.dumps({
                "type": "error", 
                "message": "Unable to determine database type"
            }) + MESSAGE_DELIMITER
            return

        logging.info("Calling to relevancy agent with query: %s",
                     sanitize_query(queries_history[-1]))

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

            logging.info("Calling to analysis agent with query: %s",
                         sanitize_query(queries_history[-1]))

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

                destructive_ops = ['INSERT', 'UPDATE', 'DELETE', 'DROP',
                                  'CREATE', 'ALTER', 'TRUNCATE']
                if sql_type in destructive_ops:
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
                        confirmation_message += ("• Modify existing data in the "
                                                "database")
                    elif sql_type == 'DELETE':
                        confirmation_message += ("• **PERMANENTLY DELETE** data "
                                                "from the database")
                    elif sql_type == 'DROP':
                        confirmation_message += ("• **PERMANENTLY DELETE** entire "
                                                "tables or database objects")
                    elif sql_type == 'CREATE':
                        confirmation_message += ("• Create new tables or database "
                                                "objects")
                    elif sql_type == 'ALTER':
                        confirmation_message += ("• Modify the structure of existing "
                                                "tables")
                    elif sql_type == 'TRUNCATE':
                        confirmation_message += ("• **PERMANENTLY DELETE ALL DATA** "
                                                "from specified tables")
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

                    # Check if this query modifies the database schema using the appropriate loader
                    is_schema_modifying, operation_type = (
                        loader_class.is_schema_modifying_query(sql_query)
                    )

                    query_results = loader_class.execute_sql_query(answer_an["sql_query"], db_url)
                    yield json.dumps(
                        {
                            "type": "query_result",
                            "data": query_results,
                        }
                    ) + MESSAGE_DELIMITER

                    # If schema was modified, refresh the graph using the appropriate loader
                    if is_schema_modifying:
                        step = {"type": "reasoning_step",
                               "message": ("Step 3: Schema change detected - "
                                         "refreshing graph...")}
                        yield json.dumps(step) + MESSAGE_DELIMITER

                        refresh_result = loader_class.refresh_graph_schema(
                            graph_id, db_url)
                        refresh_success, refresh_message = refresh_result

                        if refresh_success:
                            refresh_msg = (f"✅ Schema change detected "
                                         f"({operation_type} operation)\n\n"
                                         f"🔄 Graph schema has been automatically "
                                         f"refreshed with the latest database "
                                         f"structure.")
                            yield json.dumps(
                                {
                                    "type": "schema_refresh",
                                    "message": refresh_msg,
                                    "refresh_status": "success"
                                }
                            ) + MESSAGE_DELIMITER
                        else:
                            failure_msg = (f"⚠️ Schema was modified but graph "
                                         f"refresh failed: {refresh_message}")
                            yield json.dumps(
                                {
                                    "type": "schema_refresh",
                                    "message": failure_msg,
                                    "refresh_status": "failed"
                                }
                            ) + MESSAGE_DELIMITER

                    # Generate user-readable response using AI
                    step_num = "4" if is_schema_modifying else "3"
                    step = {"type": "reasoning_step",
                           "message": f"Step {step_num}: Generating user-friendly response"}
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
                    logging.error("Error executing SQL query: %s", str(e))
                    yield json.dumps(
                        {"type": "error", "message": "Error executing SQL query"}
                    ) + MESSAGE_DELIMITER

    return Response(stream_with_context(generate()), content_type="application/json")


@graphs_bp.route("/<string:graph_id>/confirm", methods=["POST"])
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

                # Determine database type and get appropriate loader
                db_type, loader_class = get_database_type_and_loader(db_url)

                if not loader_class:
                    yield json.dumps({
                        "type": "error", 
                        "message": "Unable to determine database type"
                    }) + MESSAGE_DELIMITER
                    return

                step = {"type": "reasoning_step",
                       "message": "Step 2: Executing confirmed SQL query"}
                yield json.dumps(step) + MESSAGE_DELIMITER

                # Check if this query modifies the database schema using appropriate loader
                is_schema_modifying, operation_type = (
                    loader_class.is_schema_modifying_query(sql_query)
                )

                query_results = loader_class.execute_sql_query(sql_query, db_url)
                yield json.dumps(
                    {
                        "type": "query_result",
                        "data": query_results,
                    }
                ) + MESSAGE_DELIMITER

                # If schema was modified, refresh the graph
                if is_schema_modifying:
                    step = {"type": "reasoning_step",
                           "message": "Step 3: Schema change detected - refreshing graph..."}
                    yield json.dumps(step) + MESSAGE_DELIMITER

                    refresh_success, refresh_message = (
                        loader_class.refresh_graph_schema(graph_id, db_url)
                    )

                    if refresh_success:
                        yield json.dumps(
                            {
                                "type": "schema_refresh",
                                "message": (f"✅ Schema change detected ({operation_type} "
                                          "operation)\n\n🔄 Graph schema has been automatically "
                                          "refreshed with the latest database structure."),
                                "refresh_status": "success"
                            }
                        ) + MESSAGE_DELIMITER
                    else:
                        yield json.dumps(
                            {
                                "type": "schema_refresh",
                                "message": (f"⚠️ Schema was modified but graph refresh failed: "
                                          f"{refresh_message}"),
                                "refresh_status": "failed"
                            }
                        ) + MESSAGE_DELIMITER

                # Generate user-readable response using AI
                step_num = "4" if is_schema_modifying else "3"
                step = {"type": "reasoning_step",
                       "message": f"Step {step_num}: Generating user-friendly response"}
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
                logging.error("Error executing confirmed SQL query: %s", str(e))
                yield json.dumps(
                    {"type": "error", "message": "Error executing query"}
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


@graphs_bp.route("/<string:graph_id>/refresh", methods=["POST"])
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
        _, db_url = get_db_description(graph_id)

        if not db_url or db_url == "No URL available for this database.":
            return jsonify({
                "success": False,
                "error": "No database URL found for this graph"
            }), 400

        # Determine database type and get appropriate loader
        db_type, loader_class = get_database_type_and_loader(db_url)

        if not loader_class:
            return jsonify({
                "success": False,
                "error": "Unable to determine database type"
            }), 400

        # Perform schema refresh using the appropriate loader
        success, message = loader_class.refresh_graph_schema(graph_id, db_url)

        if success:
            return jsonify({
                "success": True,
                "message": f"Graph schema refreshed successfully using {db_type}"
            }), 200

        logging.error("Schema refresh failed for graph %s: %s", graph_id, message)
        return jsonify({
            "success": False,
            "error": "Failed to refresh schema"
        }), 500

    except Exception as e:
        logging.error("Error in manual schema refresh: %s", e)
        return jsonify({
            "success": False,
            "error": "Error refreshing schema"
        }), 500
