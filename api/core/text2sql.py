"""Graph-related routes for the text2sql API."""

import asyncio
import json
import logging
import os
import time

from pydantic import BaseModel
from redis import ResponseError

from api.core.errors import GraphNotFoundError, InternalError, InvalidArgumentError
from api.core.schema_loader import load_database
from api.agents import AnalysisAgent, RelevancyAgent, ResponseFormatterAgent, FollowUpAgent
from api.config import Config
from api.extensions import db
from api.graph import find, get_db_description
from api.loaders.postgres_loader import PostgresLoader
from api.loaders.mysql_loader import MySQLLoader
from api.memory.graphiti_tool import MemoryTool
from api.sql_utils import SQLIdentifierQuoter, DatabaseSpecificQuoter

# Use the same delimiter as in the JavaScript
MESSAGE_DELIMITER = "|||FALKORDB_MESSAGE_BOUNDARY|||"

GENERAL_PREFIX = os.getenv("GENERAL_PREFIX")

class GraphData(BaseModel):
    """Graph data model.

    Args:
        BaseModel (_type_): _description_
    """
    database: str


class ChatRequest(BaseModel):
    """Chat request model.

    Args:
        BaseModel (_type_): _description_
    """
    chat: list[str]
    result: list[str] | None = None
    instructions: str | None = None


class ConfirmRequest(BaseModel):
    """Confirmation request model.

    Args:
        BaseModel (_type_): _description_
    """
    sql_query: str
    confirmation: str = ""
    chat: list = []


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
    if db_url_lower.startswith('mysql://'):
        return 'mysql', MySQLLoader

    # Default to PostgresLoader for backward compatibility
    return 'postgresql', PostgresLoader

def sanitize_query(query: str) -> str:
    """Sanitize the query to prevent injection attacks."""
    return query.replace('\n', ' ').replace('\r', ' ')[:500]

def sanitize_log_input(value: str) -> str:
    """
    Sanitize input for safe logging—remove newlines, 
    carriage returns, tabs, and wrap in repr().
    """
    if not isinstance(value, str):
        value = str(value)

    return value.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')

def _graph_name(user_id: str, graph_id:str) -> str:

    graph_id = graph_id.strip()[:200]
    if not graph_id:
        raise GraphNotFoundError("Invalid graph_id, must be less than 200 characters.")

    if GENERAL_PREFIX and graph_id.startswith(GENERAL_PREFIX):
        return graph_id

    return f"{user_id}_{graph_id}"

async def get_schema(user_id: str, graph_id: str):  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    """Return all nodes and edges for the specified database schema (namespaced to the user).

    This endpoint returns a JSON object with two keys: `nodes` and `edges`.
    Nodes contain a minimal set of properties (id, name, labels, props).
    Edges contain source and target node names (or internal ids), type and props.
    
        args:
            graph_id (str): The ID of the graph to query (the database name).
    """
    namespaced = _graph_name(user_id, graph_id)
    try:
        graph = db.select_graph(namespaced)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logging.error("Failed to select graph %s: %s", sanitize_log_input(namespaced), e)
        raise GraphNotFoundError("Graph not found or database error") from e

    # Build table nodes with columns and table-to-table links (foreign keys)
    tables_query = """
    MATCH (t:Table)
    OPTIONAL MATCH (c:Column)-[:BELONGS_TO]->(t)
    RETURN t.name AS table, collect(DISTINCT {name: c.name, type: c.type}) AS columns
    """

    links_query = """
    MATCH (src_col:Column)-[:BELONGS_TO]->(src_table:Table),
          (tgt_col:Column)-[:BELONGS_TO]->(tgt_table:Table),
          (src_col)-[:REFERENCES]->(tgt_col)
    RETURN DISTINCT src_table.name AS source, tgt_table.name AS target
    """

    try:
        tables_res = (await graph.query(tables_query)).result_set
        links_res = (await graph.query(links_query)).result_set
    except Exception as e:  # pylint: disable=broad-exception-caught
        logging.error("Error querying graph data for %s: %s", sanitize_log_input(namespaced), e)
        raise InternalError("Failed to read graph data") from e

    nodes = []
    for row in tables_res:
        try:
            table_name, columns = row
        except Exception:  # pylint: disable=broad-exception-caught
            continue
        # Normalize columns: ensure a list of dicts with name/type
        if not isinstance(columns, list):
            columns = [] if columns is None else [columns]

        normalized = []
        for col in columns:
            try:
                # col may be a mapping-like object or a simple value
                if not col:
                    continue
                # Some drivers may return a tuple or list for the collected map
                if isinstance(col, (list, tuple)) and len(col) >= 2:
                    # try to interpret as (name, type)
                    name = col[0]
                    ctype = col[1] if len(col) > 1 else None
                elif isinstance(col, dict):
                    name = col.get('name') or col.get('columnName')
                    ctype = col.get('type') or col.get('dataType')
                else:
                    name = str(col)
                    ctype = None

                if not name:
                    continue

                normalized.append({"name": name, "type": ctype})
            except Exception:  # pylint: disable=broad-exception-caught
                continue

        nodes.append({
            "id": table_name,
            "name": table_name,
            "columns": normalized,
        })

    links = []
    seen = set()
    for row in links_res:
        try:
            source, target = row
        except Exception:  # pylint: disable=broad-exception-caught
            continue
        key = (source, target)
        if key in seen:
            continue
        seen.add(key)
        links.append({"source": source, "target": target})

    return {"nodes": nodes, "links": links}

async def query_database(user_id: str, graph_id: str, chat_data: ChatRequest):  # pylint: disable=too-many-statements
    """
    Query the Database with the given graph_id and chat_data.
    
        Args:
            graph_id (str): The ID of the graph to query.
            chat_data (ChatRequest): The chat data containing user queries and context.
    """
    graph_id = _graph_name(user_id, graph_id)

    queries_history = chat_data.chat if hasattr(chat_data, 'chat') else None
    result_history = chat_data.result if hasattr(chat_data, 'result') else None
    instructions = chat_data.instructions if hasattr(chat_data, 'instructions') else None

    if not queries_history or not isinstance(queries_history, list):
        raise InvalidArgumentError("Invalid or missing chat history")

    if len(queries_history) == 0:
        raise InvalidArgumentError("Empty chat history")

    # Truncate history to keep only the last N questions maximum (configured in Config)
    if len(queries_history) > Config.SHORT_MEMORY_LENGTH:
        queries_history = queries_history[-Config.SHORT_MEMORY_LENGTH:]
        # Keep corresponding results (one less than queries since current query has no result yet)
        if result_history and len(result_history) > 0:
            max_results = Config.SHORT_MEMORY_LENGTH - 1
            if max_results > 0:
                result_history = result_history[-max_results:]
            else:
                result_history = []

    logging.info("User Query: %s", sanitize_query(queries_history[-1]))

    memory_tool_task = asyncio.create_task(MemoryTool.create(user_id, graph_id))

    # Create a generator function for streaming
    async def generate():  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
        # Start overall timing
        overall_start = time.perf_counter()
        logging.info("Starting query processing pipeline for query: %s",
                     sanitize_query(queries_history[-1]))  # nosemgrep

        agent_rel = RelevancyAgent(queries_history, result_history)
        agent_an = AnalysisAgent(queries_history, result_history)
        follow_up_agent = FollowUpAgent(queries_history, result_history)

        step = {"type": "reasoning_step",
                "final_response": False,
                "message": "Step 1: Analyzing user query and generating SQL..."}
        yield json.dumps(step) + MESSAGE_DELIMITER
        # Ensure the database description is loaded
        db_description, db_url = await get_db_description(graph_id)

        # Determine database type and get appropriate loader
        _, loader_class = get_database_type_and_loader(db_url)

        if not loader_class:
            overall_elapsed = time.perf_counter() - overall_start
            logging.info("Query processing failed (no loader) - Total time: %.2f seconds",
                         overall_elapsed)
            yield json.dumps({
                "type": "error",
                "final_response": True,
                "message": "Unable to determine database type"
            }) + MESSAGE_DELIMITER
            return

        # Start both tasks concurrently
        find_task = asyncio.create_task(find(graph_id, queries_history, db_description))

        relevancy_task = asyncio.create_task(agent_rel.get_answer(
            queries_history[-1], db_description
        ))

        logging.info("Starting relevancy check and graph analysis concurrently")

        # Wait for relevancy check first
        answer_rel = await relevancy_task

        if answer_rel["status"] != "On-topic": # pylint: disable=too-many-nested-blocks
            # Cancel the find task since query is off-topic
            find_task.cancel()
            try:
                await find_task
            except asyncio.CancelledError:
                logging.info("Find task cancelled due to off-topic query")

            step = {
                "type": "followup_questions",
                "final_response": True,
                "message": "Off topic question: " + answer_rel["reason"],
            }
            logging.info("SQL Fail reason: %s", answer_rel["reason"])  # nosemgrep
            yield json.dumps(step) + MESSAGE_DELIMITER
            # Total time for off-topic query
            overall_elapsed = time.perf_counter() - overall_start
            logging.info("Query processing completed (off-topic) - Total time: %.2f seconds",
                         overall_elapsed)
        else:
            # Query is on-topic, wait for find results
            result = await find_task

            logging.info("Calling to analysis agent with query: %s",
                         sanitize_query(queries_history[-1]))  # nosemgrep
            memory_tool = await memory_tool_task
            memory_context = await memory_tool.search_memories(
                query=queries_history[-1]
            )

            logging.info("Starting SQL generation with analysis agent")
            answer_an = agent_an.get_analysis(
                queries_history[-1], result, db_description, instructions, memory_context
            )

            # Initialize response variables
            user_readable_response = ""
            follow_up_result = ""
            execution_error = False

            # Auto-quote table names with special characters (like dashes)
            original_sql = answer_an['sql_query']
            if original_sql:
                # Extract known table names from the result schema
                known_tables = {table[0] for table in result} if result else set()

                # Determine database type and get appropriate quote character
                db_type, _ = get_database_type_and_loader(db_url)
                quote_char = DatabaseSpecificQuoter.get_quote_char(
                    db_type or 'postgresql'
                )

                # Auto-quote identifiers with special characters
                sanitized_sql, was_modified = (
                    SQLIdentifierQuoter.auto_quote_identifiers(
                        original_sql, known_tables, quote_char
                    )
                )

                if was_modified:
                    msg = (
                        "SQL query auto-sanitized: quoted table names with "
                        "special characters"
                    )
                    logging.info(msg)
                    answer_an['sql_query'] = sanitized_sql

            logging.info("Generated SQL query: %s", answer_an['sql_query'])  # nosemgrep
            yield json.dumps(
                {
                    "type": "sql_query",
                    "data": answer_an["sql_query"],
                    "conf": answer_an["confidence"],
                    "miss": answer_an["missing_information"],
                    "amb": answer_an["ambiguities"],
                    "exp": answer_an["explanation"],
                    "is_valid": answer_an["is_sql_translatable"],
                    "final_response": False,
                }
            ) + MESSAGE_DELIMITER

            # If the SQL query is valid, execute it using the postgres database db_url
            if answer_an["is_sql_translatable"]:
                # Check if this is a destructive operation that requires confirmation
                sql_query = answer_an["sql_query"]
                sql_type = sql_query.strip().split()[0].upper() if sql_query else ""

                destructive_ops = ['INSERT', 'UPDATE', 'DELETE', 'DROP',
                                  'CREATE', 'ALTER', 'TRUNCATE']
                is_destructive = sql_type in destructive_ops
                general_graph = graph_id.startswith(GENERAL_PREFIX) if GENERAL_PREFIX else False
                if is_destructive and not general_graph:
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
                            "operation_type": sql_type,
                            "final_response": False,
                        }
                    ) + MESSAGE_DELIMITER
                    # Log end-to-end time for destructive operation that requires confirmation
                    overall_elapsed = time.perf_counter() - overall_start
                    logging.info(
                        "Query processing halted for confirmation - Total time: %.2f seconds",
                        overall_elapsed
                    )
                    return  # Stop here and wait for user confirmation

                try:
                    if is_destructive and general_graph:
                        yield json.dumps(
                            {
                                "type": "error", 
                                "final_response": True, 
                                "message": "Destructive operation not allowed on demo graphs"
                            }) + MESSAGE_DELIMITER
                    else:
                        step = {"type": "reasoning_step",
                                "final_response": False,
                                "message": "Step 2: Executing SQL query"}
                        yield json.dumps(step) + MESSAGE_DELIMITER

                        # Check if this query modifies the database schema
                        # using the appropriate loader
                        is_schema_modifying, operation_type = (
                            loader_class.is_schema_modifying_query(sql_query)
                        )

                        query_results = loader_class.execute_sql_query(
                            answer_an["sql_query"],
                            db_url
                        )
                        if len(query_results) != 0:
                            yield json.dumps(
                                {
                                    "type": "query_result",
                                    "data": query_results,
                                    "final_response": False
                                }
                            ) + MESSAGE_DELIMITER

                        # If schema was modified, refresh the graph using the appropriate loader
                        if is_schema_modifying:
                            step = {"type": "reasoning_step",
                                    "final_response": False,
                                    "message": ("Step 3: Schema change detected - "
                                                "refreshing graph...")}
                            yield json.dumps(step) + MESSAGE_DELIMITER

                            refresh_result = await loader_class.refresh_graph_schema(
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
                                        "final_response": False,
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
                                        "final_response": False,
                                        "message": failure_msg,
                                        "refresh_status": "failed"
                                    }
                                ) + MESSAGE_DELIMITER

                        # Generate user-readable response using AI
                        step_num = "4" if is_schema_modifying else "3"
                        step = {"type": "reasoning_step",
                                "final_response": False,
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
                                "final_response": True,
                                "message": user_readable_response,
                            }
                        ) + MESSAGE_DELIMITER

                        # Log overall completion time
                        overall_elapsed = time.perf_counter() - overall_start
                        logging.info(
                            "Query processing completed successfully - Total time: %.2f seconds",
                            overall_elapsed
                        )

                except Exception as e:  # pylint: disable=broad-exception-caught
                    execution_error = str(e)
                    overall_elapsed = time.perf_counter() - overall_start
                    logging.error("Error executing SQL query: %s", str(e))  # nosemgrep
                    logging.info(
                        "Query processing failed during execution - Total time: %.2f seconds",
                        overall_elapsed
                    )
                    yield json.dumps({
                        "type": "error", 
                        "final_response": True, 
                        "message": "Error executing SQL query"
                    }) + MESSAGE_DELIMITER
            else:
                execution_error = "Missing information"
                # SQL query is not valid/translatable - generate follow-up questions
                follow_up_result = follow_up_agent.generate_follow_up_question(
                    user_question=queries_history[-1],
                    analysis_result=answer_an
                )

                # Send follow-up questions to help the user
                yield json.dumps({
                    "type": "followup_questions",
                    "final_response": True,
                    "message": follow_up_result,
                    "missing_information": answer_an.get("missing_information", ""),
                    "ambiguities": answer_an.get("ambiguities", "")
                }) + MESSAGE_DELIMITER

                overall_elapsed = time.perf_counter() - overall_start
                logging.info(
                    "Query processing completed (non-translatable SQL) - Total time: %.2f seconds",
                    overall_elapsed
                )

            # Save conversation to memory (only for on-topic queries)
            # Determine the final answer based on which path was taken
            final_answer = user_readable_response if user_readable_response else follow_up_result

            # Build comprehensive response for memory
            full_response = {
                "question": queries_history[-1],
                "generated_sql": answer_an.get('sql_query', ""),
                "answer": final_answer
            }

            # Add error information if SQL execution failed
            if execution_error:
                full_response["error"] = execution_error
                full_response["success"] = False
            else:
                full_response["success"] = True


            # Save query to memory
            save_query_task = asyncio.create_task(
                memory_tool.save_query_memory(
                    query=queries_history[-1],
                    sql_query=answer_an["sql_query"],
                    success=full_response["success"],
                    error=execution_error
                )
            )
            save_query_task.add_done_callback(
                lambda t: logging.error("Query memory save failed: %s", t.exception())  # nosemgrep
                if t.exception() else logging.info("Query memory saved successfully")
            )

            # Save conversation with memory tool (run in background)
            save_task = asyncio.create_task(
                memory_tool.add_new_memory(full_response,
                                            [queries_history, result_history])
            )
            # Add error handling callback to prevent silent failures
            save_task.add_done_callback(
                lambda t: logging.error("Memory save failed: %s", t.exception())  # nosemgrep
                if t.exception() else logging.info("Conversation saved to memory tool")
            )
            logging.info("Conversation save task started in background")

            # Clean old memory in background (once per week cleanup)
            clean_memory_task = asyncio.create_task(memory_tool.clean_memory())
            clean_memory_task.add_done_callback(
                lambda t: logging.error("Memory cleanup failed: %s", t.exception())  # nosemgrep
                if t.exception() else logging.info("Memory cleanup completed successfully")
            )

        # Log timing summary at the end of processing
        overall_elapsed = time.perf_counter() - overall_start
        logging.info("Query processing pipeline completed - Total time: %.2f seconds",
                     overall_elapsed)

    return generate()


async def execute_destructive_operation(  # pylint: disable=too-many-statements
    user_id: str,
    graph_id: str,
    confirm_data: ConfirmRequest,
):
    """
    Handle user confirmation for destructive SQL operations
    """

    graph_id = _graph_name(user_id, graph_id)

    if hasattr(confirm_data, 'confirmation'):
        confirmation = confirm_data.confirmation.strip().upper()
    else:
        confirmation = ""

    sql_query = confirm_data.sql_query if hasattr(confirm_data, 'sql_query') else ""
    queries_history = confirm_data.chat if hasattr(confirm_data, 'chat') else []

    if not sql_query:
        raise InvalidArgumentError("No SQL query provided")

    # Create a generator function for streaming the confirmation response
    async def generate_confirmation():  # pylint: disable=too-many-locals,too-many-statements
        # Create memory tool for saving query results
        memory_tool = await MemoryTool.create(user_id, graph_id)

        if confirmation == "CONFIRM":
            try:
                db_description, db_url = await get_db_description(graph_id)

                # Determine database type and get appropriate loader
                _, loader_class = get_database_type_and_loader(db_url)

                if not loader_class:
                    yield json.dumps({
                        "type": "error",
                        "message": "Unable to determine database type"
                    }) + MESSAGE_DELIMITER
                    return

                step = {"type": "reasoning_step",
                       "message": "Step 2: Executing confirmed SQL query"}
                yield json.dumps(step) + MESSAGE_DELIMITER

                # Auto-quote table names for confirmed destructive operations
                sql_query = confirm_data.sql_query if hasattr(
                    confirm_data, 'sql_query'
                ) else ""
                if sql_query:
                    # Get schema to extract known tables
                    graph = db.select_graph(graph_id)
                    tables_query = "MATCH (t:Table) RETURN t.name"
                    try:
                        tables_res = (await graph.query(tables_query)).result_set
                        known_tables = (
                            {row[0] for row in tables_res}
                            if tables_res else set()
                        )
                    except Exception:  # pylint: disable=broad-exception-caught
                        known_tables = set()

                    # Determine database type and get appropriate quote character
                    db_type, _ = get_database_type_and_loader(db_url)
                    quote_char = DatabaseSpecificQuoter.get_quote_char(
                        db_type or 'postgresql'
                    )

                    # Auto-quote identifiers
                    sanitized_sql, was_modified = (
                        SQLIdentifierQuoter.auto_quote_identifiers(
                            sql_query, known_tables, quote_char
                        )
                    )
                    if was_modified:
                        logging.info("Confirmed SQL query auto-sanitized")
                        sql_query = sanitized_sql

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
                        await loader_class.refresh_graph_schema(graph_id, db_url)
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

                # Save successful confirmed query to memory
                save_query_task = asyncio.create_task(
                    memory_tool.save_query_memory(
                        query=(queries_history[-1] if queries_history
                               else "Destructive operation confirmation"),
                        sql_query=sql_query,
                        success=True,
                        error=""
                    )
                )
                save_query_task.add_done_callback(
                    lambda t: logging.error("Confirmed query memory save failed: %s",
                                            t.exception())  # nosemgrep
                    if t.exception() else logging.info("Confirmed query memory saved successfully")
                )

            except Exception as e:  # pylint: disable=broad-exception-caught
                logging.error("Error executing confirmed SQL query: %s", str(e))  # nosemgrep
                error_message = str(e) if str(e) else "Error executing query"

                # Save failed confirmed query to memory
                save_query_task = asyncio.create_task(
                    memory_tool.save_query_memory(
                        query=(queries_history[-1] if queries_history
                               else "Destructive operation confirmation"),
                        sql_query=sql_query,
                        success=False,
                        error=str(e)
                    )
                )
                save_query_task.add_done_callback(
                    lambda t: logging.error(  # nosemgrep
                        "Failed confirmed query memory save failed: %s", t.exception()
                    ) if t.exception() else logging.info(
                        "Failed confirmed query memory saved successfully"
                    )
                )

                yield json.dumps(
                    {"type": "error", "message": error_message}
                ) + MESSAGE_DELIMITER
        else:
            # User cancelled or provided invalid confirmation
            yield json.dumps(
                {
                    "type": "operation_cancelled",
                    "message": "Operation cancelled. The destructive SQL query was not executed."
                }
            ) + MESSAGE_DELIMITER

    return generate_confirmation()

async def refresh_database_schema(user_id: str, graph_id: str):
    """
    Manually refresh the graph schema from the database.
    This endpoint allows users to manually trigger a schema refresh
    if they suspect the graph is out of sync with the database.
    """
    graph_id = _graph_name(user_id, graph_id)

    # Prevent refresh of demo databases
    if GENERAL_PREFIX and graph_id.startswith(GENERAL_PREFIX):
        raise InvalidArgumentError("Demo graphs cannot be refreshed")

    try:
        # Get database description and URL
        _, db_url = await get_db_description(graph_id)

        if not db_url or db_url == "No URL available for this database.":
            raise InternalError("No database URL found for this graph")

        # Call load_database to refresh the schema by reconnecting
        return await load_database(db_url, user_id)
    except InternalError:
        raise
    except Exception as e:
        logging.error("Error in refresh_graph_schema: %s", str(e))
        raise InternalError("Internal server error while refreshing schema") from e

async def delete_database(user_id: str, graph_id: str):
    """Delete the specified graph (namespaced to the user).

    This will attempt to delete the FalkorDB graph belonging to the
    authenticated user. The graph id used by the client is stripped of
    namespace and will be namespaced using the user's id from the request
    state.
    """
    namespaced = _graph_name(user_id, graph_id)
    if GENERAL_PREFIX and graph_id.startswith(GENERAL_PREFIX):
        raise InvalidArgumentError("Demo graphs cannot be deleted")

    try:
        # Select and delete the graph using the FalkorDB client API
        graph = db.select_graph(namespaced)
        await graph.delete()
        return {"success": True, "graph": graph_id}
    except ResponseError as re:
        raise GraphNotFoundError("Failed to delete graph, Graph not found") from re
    except Exception as e:  # pylint: disable=broad-exception-caught
        logging.exception("Failed to delete graph %s: %s", sanitize_log_input(namespaced), e)
        raise InternalError("Failed to delete graph") from e
