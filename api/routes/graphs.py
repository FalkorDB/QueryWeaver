"""Graph-related routes for the text2sql API."""

import json
import logging
from quart import Blueprint, jsonify, request, Response, g

from api.agents import AnalysisAgent, RelevancyAgent, ResponseFormatterAgent
from api.auth.user_management import token_required
from api.extensions import db
from api.graph import find, get_db_description
from api.loaders.csv_loader import CSVLoader
from api.loaders.json_loader import JSONLoader
from api.loaders.postgres_loader import PostgresLoader
from api.loaders.mysql_loader import MySQLLoader
from api.loaders.odata_loader import ODataLoader

MESSAGE_DELIMITER = "|||FALKORDB_MESSAGE_BOUNDARY|||"

graphs_bp = Blueprint("graphs", __name__, url_prefix="/graphs")


def get_database_type_and_loader(db_url: str):
    """
    Determine the database type and return the appropriate loader class.
    
    Args:
        db_url: Database URL string
        
    Returns:
        Tuple of (db_type, loader_class)
    """
    if not db_url:
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
async def list_graphs():
    user_id = g.user_id
    user_graphs = await db.list_graphs()

    filtered_graphs = [
        graph[len(f"{user_id}_"):]
        for graph in user_graphs if graph.startswith(f"{user_id}_")
    ]
    return jsonify(filtered_graphs)


@graphs_bp.route("", methods=["POST"]) 
@token_required
async def load_graph():
    content_type = request.content_type
    success, result = False, "Invalid content type"
    graph_id = ""

    if content_type.startswith("application/json"):
        data = await request.get_json()
        if not data or "database" not in data:
            return jsonify({"error": "Invalid JSON data"}), 400
        graph_id = g.user_id + "_" + data["database"]
        success, result = await JSONLoader.load(graph_id, data)

    elif content_type.startswith("multipart/form-data"):
        files = await request.files
        if "file" not in files:
            return jsonify({"error": "No file uploaded"}), 400

        file = files["file"]
        if file.filename == "":
            return jsonify({"error": "Empty file"}), 400

        if file.filename.endswith(".json"):
            try:
                data = json.load(file)
                graph_id = g.user_id + "_" + data.get("database", "")
                success, result = await JSONLoader.load(graph_id, data)
            except json.JSONDecodeError:
                return jsonify({"error": "Invalid JSON file"}), 400
        elif file.filename.endswith(".xml"):
            xml_data = file.read().decode("utf-8")
            graph_id = g.user_id + "_" + file.filename.replace(".xml", "")
            success, result = await ODataLoader.load(graph_id, xml_data)
        elif file.filename.endswith(".csv"):
            csv_data = file.read().decode("utf-8")
            graph_id = g.user_id + "_" + file.filename.replace(".csv", "")
            success, result = await CSVLoader.load(graph_id, csv_data)
        else:
            return jsonify({"error": "Unsupported file type"}), 415
    else:
        return jsonify({"error": "Unsupported Content-Type"}), 415

    if success:
        return jsonify({"message": "Graph loaded successfully", "graph_id": graph_id})

    logging.error("Graph loading failed: %s", str(result)[:100])
    return jsonify({"error": "Failed to load graph data"}), 400


@graphs_bp.route("/<string:graph_id>", methods=["POST"]) 
@token_required
async def query_graph(graph_id: str):
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
    request_data = await request.get_json()
    if not request_data:
        return jsonify({"error": "No JSON data provided"}), 400

    queries_history = request_data.get("chat")
    result_history = request_data.get("result")
    instructions = request_data.get("instructions")

    if not queries_history or not isinstance(queries_history, list) or len(queries_history) == 0:
        return jsonify({"error": "Invalid or empty chat history"}), 400

    logging.info("User Query: %s", sanitize_query(queries_history[-1]))

    async def generate():
        agent_rel = RelevancyAgent(queries_history, result_history)
        agent_an = AnalysisAgent(queries_history, result_history)

        yield json.dumps({
            "type": "reasoning_step",
            "message": "Step 1: Analyzing user query and generating SQL..."
        }) + MESSAGE_DELIMITER

        db_description, db_url = await get_db_description(graph_id)
        db_type, loader_class = get_database_type_and_loader(db_url)

        if not loader_class:
            yield json.dumps({"type": "error", "message": "Unable to determine database type"}) + MESSAGE_DELIMITER
            return

        answer_rel = agent_rel.get_answer(queries_history[-1], db_description)
        if answer_rel["status"] != "On-topic":
            yield json.dumps({
                "type": "followup_questions",
                "message": "Off topic question: " + answer_rel["reason"]
            }) + MESSAGE_DELIMITER
            return

        # Call async find
        result = await find(graph_id, queries_history, db_description)

        answer_an = agent_an.get_analysis(queries_history[-1], result, db_description, instructions)
        logging.info("SQL Result: %s", answer_an['sql_query'])
        
        yield json.dumps({
            "type": "final_result",
            "data": answer_an["sql_query"],
            "conf": answer_an["confidence"],
            "miss": answer_an["missing_information"],
            "amb": answer_an["ambiguities"],
            "exp": answer_an["explanation"],
            "is_valid": answer_an["is_sql_translatable"],
        }) + MESSAGE_DELIMITER

        if answer_an["is_sql_translatable"]:
            # Check if this is a destructive operation that requires confirmation
            sql_query = answer_an["sql_query"]
            sql_type = sql_query.strip().split()[0].upper() if sql_query else ""
            destructive_ops = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER', 'TRUNCATE']
            
            if sql_type in destructive_ops:
                # This is a destructive operation - ask for user confirmation
                confirmation_message = f"""⚠️ DESTRUCTIVE OPERATION DETECTED ⚠️

The generated SQL query will perform a **{sql_type}** operation:

SQL:
{sql_query}

What this will do:"""
                
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

⚠️ WARNING: This operation will make changes to your database and may be irreversible."""
                
                yield json.dumps({
                    "type": "destructive_confirmation",
                    "message": confirmation_message,
                    "sql_query": sql_query,
                    "operation_type": sql_type
                }) + MESSAGE_DELIMITER
                return  # Stop here and wait for user confirmation

            try:
                step = {"type": "reasoning_step", "message": "Step 2: Executing SQL query"}
                yield json.dumps(step) + MESSAGE_DELIMITER
                
                # Check if this query modifies the database schema using the appropriate loader
                is_schema_modifying, operation_type = loader_class.is_schema_modifying_query(sql_query)
                
                query_results = loader_class.execute_sql_query(answer_an["sql_query"], db_url)
                yield json.dumps({
                    "type": "query_result",
                    "data": query_results,
                }) + MESSAGE_DELIMITER

                # If schema was modified, refresh the graph using the appropriate loader
                if is_schema_modifying:
                    step = {"type": "reasoning_step",
                           "message": "Step 3: Schema change detected - refreshing graph..."}
                    yield json.dumps(step) + MESSAGE_DELIMITER
                    
                    refresh_result = loader_class.refresh_graph_schema(graph_id, db_url)
                    refresh_success, refresh_message = refresh_result
                    
                    if refresh_success:
                        refresh_msg = (f"✅ Schema change detected ({operation_type} operation)\n\n"
                                     f"🔄 Graph schema has been automatically refreshed with the latest database structure.")
                        yield json.dumps({
                            "type": "schema_refresh",
                            "message": refresh_msg,
                            "refresh_status": "success"
                        }) + MESSAGE_DELIMITER
                    else:
                        failure_msg = f"⚠️ Schema was modified but graph refresh failed: {refresh_message}"
                        yield json.dumps({
                            "type": "schema_refresh",
                            "message": failure_msg,
                            "refresh_status": "failed"
                        }) + MESSAGE_DELIMITER

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
                yield json.dumps({
                    "type": "ai_response",
                    "message": user_readable_response,
                }) + MESSAGE_DELIMITER
                
            except Exception as e:
                logging.error("Error executing SQL query: %s", str(e))
                yield json.dumps({
                    "type": "error", 
                    "message": "Error executing SQL query"
                }) + MESSAGE_DELIMITER

    # Return the async generator directly as a streaming response
    return Response(generate(), content_type="application/json")


@graphs_bp.route("/<string:graph_id>/confirm", methods=["POST"]) 
@token_required
async def confirm_destructive_operation(graph_id: str):
    """
    Handle user confirmation for destructive SQL operations
    """
    graph_id = g.user_id + "_" + graph_id.strip()
    request_data = await request.get_json()
    confirmation = request_data.get("confirmation", "").strip().upper()
    sql_query = request_data.get("sql_query", "")
    queries_history = request_data.get("chat", [])

    if not sql_query:
        return jsonify({"error": "No SQL query provided"}), 400

    # Create a generator function for streaming the confirmation response
    async def generate_confirmation():
        if confirmation == "CONFIRM":
            try:
                db_description, db_url = await get_db_description(graph_id)
                
                # Determine database type and get appropriate loader
                db_type, loader_class = get_database_type_and_loader(db_url)
                
                if not loader_class:
                    yield json.dumps({
                        "type": "error",
                        "message": "Unable to determine database type"
                    }) + MESSAGE_DELIMITER
                    return

                step = {"type": "reasoning_step", "message": "Step 2: Executing confirmed SQL query"}
                yield json.dumps(step) + MESSAGE_DELIMITER

                # Check if this query modifies the database schema using the appropriate loader
                is_schema_modifying, operation_type = loader_class.is_schema_modifying_query(sql_query)
                
                query_results = loader_class.execute_sql_query(sql_query, db_url)
                yield json.dumps({
                    "type": "query_result",
                    "data": query_results,
                }) + MESSAGE_DELIMITER

                # If schema was modified, refresh the graph
                if is_schema_modifying:
                    step = {"type": "reasoning_step",
                           "message": "Step 3: Schema change detected - refreshing graph..."}
                    yield json.dumps(step) + MESSAGE_DELIMITER
                    
                    refresh_success, refresh_message = loader_class.refresh_graph_schema(graph_id, db_url)
                    
                    if refresh_success:
                        yield json.dumps({
                            "type": "schema_refresh",
                            "message": (f"✅ Schema change detected ({operation_type} operation)\n\n"
                                      f"🔄 Graph schema has been automatically refreshed with the latest database structure."),
                            "refresh_status": "success"
                        }) + MESSAGE_DELIMITER
                    else:
                        yield json.dumps({
                            "type": "schema_refresh",
                            "message": f"⚠️ Schema was modified but graph refresh failed: {refresh_message}",
                            "refresh_status": "failed"
                        }) + MESSAGE_DELIMITER

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
                yield json.dumps({
                    "type": "ai_response",
                    "message": user_readable_response,
                }) + MESSAGE_DELIMITER
                
            except Exception as e:
                logging.error("Error executing confirmed SQL query: %s", str(e))
                yield json.dumps({
                    "type": "error", 
                    "message": "Error executing query"
                }) + MESSAGE_DELIMITER
        else:
            # User cancelled or provided invalid confirmation
            yield json.dumps({
                "type": "operation_cancelled",
                "message": "Operation cancelled. The destructive SQL query was not executed."
            }) + MESSAGE_DELIMITER

    return Response(generate_confirmation(), content_type="application/json")


@graphs_bp.route("/<string:graph_id>/refresh", methods=["POST"]) 
@token_required
async def refresh_graph_schema(graph_id: str):
    """
    Manually refresh the graph schema from the database.
    This endpoint allows users to manually trigger a schema refresh
    if they suspect the graph is out of sync with the database.
    """
    graph_id = g.user_id + "_" + graph_id.strip()
    
    try:
        # Get database connection details
        _, db_url = await get_db_description(graph_id)
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
