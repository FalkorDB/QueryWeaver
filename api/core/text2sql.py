"""Graph-related routes for the text2sql API."""
# pylint: disable=line-too-long,trailing-whitespace

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Optional, TYPE_CHECKING, Union

from pydantic import BaseModel
from redis import ResponseError, RedisError

from api.core.errors import GraphNotFoundError, InternalError, InvalidArgumentError
from api.core.schema_loader import load_database
from api.core.pipeline import (
    auto_quote_sql_identifiers,
    build_destructive_confirmation_message,
    check_schema_modification,
    detect_destructive_operation,
    format_ai_response,
    get_database_type_and_loader,
    graph_name,
    is_general_graph,
    quote_identifiers_from_graph,
    sanitize_log_input,
    sanitize_query,
    save_memory_background,
    validate_and_truncate_chat,
    validate_custom_model,
)
from api.agents import AnalysisAgent, RelevancyAgent, FollowUpAgent
from api.agents.healer_agent import HealerAgent
from api.core.db_resolver import resolve_db
from api.core.usage_tracking import record_query_usage_background
from api.core.result_models import QueryAnalysis, QueryMetadata, QueryResult, RefreshResult
from api.graph import find, get_db_description, get_user_rules

if TYPE_CHECKING:
    from falkordb.asyncio import FalkorDB


async def _create_memory_tool(user_id: str, graph_id: str, db=None):
    """Lazy-create a MemoryTool.

    ``graphiti_core`` lives in the ``[server]`` extra; deferring the import
    keeps ``pip install queryweaver`` (no extras) working for SDK callers
    that pass ``use_memory=False`` (the SDK default).
    """
    # pylint: disable=import-outside-toplevel
    from api.memory.graphiti_tool import MemoryTool
    return await MemoryTool.create(user_id, graph_id, db=db)


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
    custom_api_key: str | None = None
    custom_model: str | None = None
    use_user_rules: bool = True  # If True, fetch rules from database; if False, don't use rules
    use_memory: bool = True


class ConfirmRequest(BaseModel):
    """Confirmation request model.

    Args:
        BaseModel (_type_): _description_
    """
    sql_query: str
    confirmation: str = ""
    chat: list = []
    custom_api_key: str | None = None
    custom_model: str | None = None
    use_memory: bool = False



async def get_schema(user_id: str, graph_id: str, db=None):  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    """Return all nodes and edges for the specified database schema (namespaced to the user).

    This endpoint returns a JSON object with two keys: `nodes` and `edges`.
    Nodes contain a minimal set of properties (id, name, labels, props).
    Edges contain source and target node names (or internal ids), type and props.

        args:
            graph_id (str): The ID of the graph to query (the database name).
    """
    namespaced = graph_name(user_id, graph_id)
    try:
        graph = resolve_db(db).select_graph(namespaced)
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


# ---------------------------------------------------------------------------
# Unified text2sql pipeline
#
# ``run_query`` and ``run_confirmed`` are async generators that yield wire-format
# progress events as plain dicts and end with a ``_Final(QueryResult)`` sentinel.
#
# • Streaming consumers (api/routes/graphs.py): serialize each yielded dict as
#   ``json + MESSAGE_DELIMITER`` and stop when ``_Final`` arrives — the user-facing
#   "final" event was already emitted as a regular dict before the sentinel.
# • SDK consumers (queryweaver): use ``collect_result`` to drop progress
#   events and return the final ``QueryResult``.
#
# This is the one source of truth for the text2sql pipeline.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Final:
    """Sentinel terminating the pipeline generator with a structured result."""
    value: QueryResult


async def collect_result(
    gen: AsyncGenerator[Union[dict, _Final], None],
) -> QueryResult:
    """Drain a pipeline generator, returning the final ``QueryResult``.

    Used by SDK consumers that don't care about progress events. Streaming
    consumers iterate manually so they can serialize each dict event.
    """
    async for event in gen:
        if isinstance(event, _Final):
            return event.value
    raise InternalError("Pipeline produced no final result")


async def _emit_schema_refresh(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    loader_class,
    namespaced: str,
    db_url: str,
    operation_type: str,
    *,
    db: Optional["FalkorDB"] = None,
    mark_final_response: bool = False,
) -> AsyncGenerator[dict, None]:
    """Refresh the graph schema and yield the standard wire events.

    ``mark_final_response`` adds the ``final_response: False`` field to events.
    The streaming path (``run_query``) sets it; the confirm path historically
    omits it. Threading the divergence through one parameter keeps the two
    callers from drifting again.
    """
    base = {"final_response": False} if mark_final_response else {}
    yield {
        **base,
        "type": "reasoning_step",
        "message": "Step 3: Schema change detected - refreshing graph...",
    }

    refresh_success, refresh_message = await loader_class.refresh_graph_schema(
        namespaced, db_url, db=db,
    )
    if refresh_success:
        yield {
            **base,
            "type": "schema_refresh",
            "message": (
                f"✅ Schema change detected ({operation_type} operation)\n\n"
                "🔄 Graph schema has been automatically refreshed with the "
                "latest database structure."
            ),
            "refresh_status": "success",
        }
    else:
        yield {
            **base,
            "type": "schema_refresh",
            "message": (
                f"⚠️ Schema was modified but graph refresh failed: "
                f"{refresh_message}"
            ),
            "refresh_status": "failed",
        }


def _build_query_result(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    sql_query: str,
    results: list,
    ai_response: str,
    *,
    confidence: float = 0.0,
    is_valid: bool = True,
    is_destructive: bool = False,
    requires_confirmation: bool = False,
    execution_time: float = 0.0,
    missing_information: str = "",
    ambiguities: str = "",
    explanation: str = "",
    error_message: Optional[str] = None,
) -> QueryResult:
    """Assemble a ``QueryResult`` from the pipeline's loose state."""
    return QueryResult(
        sql_query=sql_query,
        results=results,
        ai_response=ai_response,
        metadata=QueryMetadata(
            confidence=confidence,
            is_valid=is_valid,
            is_destructive=is_destructive,
            requires_confirmation=requires_confirmation,
            execution_time=execution_time,
        ),
        analysis=QueryAnalysis(
            missing_information=missing_information,
            ambiguities=ambiguities,
            explanation=explanation,
        ),
        error_message=error_message,
    )


async def run_query(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    user_id: str,
    graph_id: str,
    chat_data: Any,
    db: Optional["FalkorDB"] = None,
) -> AsyncGenerator[Union[dict, _Final], None]:
    """Run the full text2sql pipeline.

    Yields wire-format progress dicts (matching the streaming JSON shapes the
    React frontend already parses) and ends with a ``_Final(QueryResult)``
    sentinel carrying the structured result for SDK callers.

    Args:
        user_id: Namespacing identifier.
        graph_id: Un-prefixed graph id; namespacing is applied internally.
        chat_data: Anything with ``chat`` / ``result`` / ``instructions`` /
            ``custom_api_key`` / ``custom_model`` / ``use_user_rules`` /
            ``use_memory`` attributes (Pydantic ``ChatRequest`` works).
        db: Optional FalkorDB handle; resolves to the server singleton when
            ``None``.
    """
    overall_start = time.perf_counter()
    namespaced = graph_name(user_id, graph_id)
    queries_history, result_history, instructions, use_user_rules = (
        validate_and_truncate_chat(chat_data)
    )
    custom_api_key = getattr(chat_data, "custom_api_key", None)
    custom_model = getattr(chat_data, "custom_model", None)
    use_memory = getattr(chat_data, "use_memory", False)
    validate_custom_model(custom_model)

    logging.info("User Query: %s", sanitize_query(queries_history[-1]))

    # Memory tool created concurrently with relevancy/find work — small perf
    # win for streaming, harmless for SDK. Lazy-imported via _create_memory_tool.
    memory_tool_task = (
        asyncio.create_task(_create_memory_tool(user_id, namespaced, db=db))
        if use_memory else None
    )

    yield {
        "type": "reasoning_step",
        "final_response": False,
        "message": "Step 1: Analyzing user query and generating SQL...",
    }

    db_description, db_url = await get_db_description(namespaced, db=db)
    user_rules_spec = (
        await get_user_rules(namespaced, db=db) if use_user_rules else None
    )
    db_type, loader_class = get_database_type_and_loader(db_url)

    if not loader_class:
        yield {"type": "error", "final_response": True,
               "message": "Unable to determine database type"}
        yield _Final(_build_query_result(
            sql_query="", results=[],
            ai_response="Unable to determine database type",
            is_valid=False,
            execution_time=time.perf_counter() - overall_start,
            error_message="Unable to determine database type",
        ))
        return

    # Concurrent: relevancy check + table-finding
    find_task = asyncio.create_task(
        find(namespaced, queries_history, db_description, db=db)
    )
    agent_rel = RelevancyAgent(
        queries_history, result_history, custom_api_key, custom_model,
    )
    relevancy_task = asyncio.create_task(
        agent_rel.get_answer(queries_history[-1], db_description)
    )
    answer_rel = await relevancy_task

    if answer_rel["status"] != "On-topic":
        find_task.cancel()
        try:
            await find_task
        except asyncio.CancelledError:
            logging.debug("Find task cancelled (off-topic query)")
        msg = "Off topic question: " + answer_rel["reason"]
        yield {"type": "followup_questions", "final_response": True, "message": msg}
        yield _Final(_build_query_result(
            sql_query="", results=[], ai_response=msg,
            is_valid=False,
            execution_time=time.perf_counter() - overall_start,
        ))
        return

    tables = await find_task

    memory_tool = None
    memory_context = None
    if memory_tool_task is not None:
        memory_tool = await memory_tool_task
        memory_context = await memory_tool.search_memories(query=queries_history[-1])

    agent_an = AnalysisAgent(
        queries_history, result_history, custom_api_key, custom_model,
    )
    answer_an = agent_an.get_analysis(
        queries_history[-1], tables, db_description, instructions, memory_context,
        db_type, user_rules_spec,
    )

    yield {
        "type": "sql_query",
        "data": answer_an["sql_query"],
        "conf": answer_an["confidence"],
        "miss": answer_an["missing_information"],
        "amb": answer_an["ambiguities"],
        "exp": answer_an["explanation"],
        "is_valid": answer_an["is_sql_translatable"],
        "final_response": False,
    }

    if not answer_an["is_sql_translatable"]:
        follow_up_agent = FollowUpAgent(
            queries_history, result_history, custom_api_key, custom_model,
        )
        follow_up = follow_up_agent.generate_follow_up_question(
            user_question=queries_history[-1],
            analysis_result=answer_an,
        )
        yield {
            "type": "followup_questions",
            "final_response": True,
            "message": follow_up,
            "missing_information": answer_an.get("missing_information", ""),
            "ambiguities": answer_an.get("ambiguities", ""),
        }
        yield _Final(_build_query_result(
            sql_query=answer_an.get("sql_query", ""),
            results=[],
            ai_response=follow_up,
            confidence=answer_an.get("confidence", 0.0),
            is_valid=False,
            execution_time=time.perf_counter() - overall_start,
            missing_information=answer_an.get("missing_information", ""),
            ambiguities=answer_an.get("ambiguities", ""),
            explanation=answer_an.get("explanation", ""),
        ))
        return

    # Auto-quote identifiers using the table set we already loaded.
    known_tables = {t[0] for t in tables} if tables else set()
    sanitized_sql, was_modified = auto_quote_sql_identifiers(
        answer_an["sql_query"], known_tables, db_type,
    )
    if was_modified:
        logging.info(
            "SQL query auto-sanitized: quoted table names with special characters"
        )
        answer_an["sql_query"] = sanitized_sql

    sql_query = answer_an["sql_query"]
    sql_type, is_destructive = detect_destructive_operation(sql_query)
    on_demo = is_general_graph(namespaced)

    if is_destructive and on_demo:
        yield {
            "type": "error",
            "final_response": True,
            "message": "Destructive operation not allowed on demo graphs",
        }
        yield _Final(_build_query_result(
            sql_query=sql_query, results=[],
            ai_response="Destructive operation not allowed on demo graphs",
            confidence=answer_an.get("confidence", 0.0),
            is_valid=True, is_destructive=True,
            execution_time=time.perf_counter() - overall_start,
            error_message="Destructive operation not allowed on demo graphs",
        ))
        return

    if is_destructive:
        confirmation_msg = build_destructive_confirmation_message(sql_type, sql_query)
        yield {
            "type": "destructive_confirmation",
            "message": confirmation_msg,
            "sql_query": sql_query,
            "operation_type": sql_type,
            "final_response": False,
        }
        yield _Final(_build_query_result(
            sql_query=sql_query, results=[], ai_response=confirmation_msg,
            confidence=answer_an.get("confidence", 0.0),
            is_valid=True, is_destructive=True, requires_confirmation=True,
            execution_time=time.perf_counter() - overall_start,
        ))
        return

    yield {
        "type": "reasoning_step",
        "final_response": False,
        "message": "Step 2: Executing SQL query",
    }

    is_schema_modifying, operation_type = check_schema_modification(sql_query, loader_class)

    execution_error_msg = None
    query_results: list = []
    user_readable_response = ""

    try:
        try:
            query_results = loader_class.execute_sql_query(sql_query, db_url)
        except Exception as exec_error:  # pylint: disable=broad-exception-caught
            yield {
                "type": "reasoning_step",
                "final_response": False,
                "message": "Step 2a: SQL execution failed, attempting to heal query...",
            }
            healer = HealerAgent(max_healing_attempts=3)

            def _run_sql(sql: str):
                return loader_class.execute_sql_query(sql, db_url)

            healing_result = healer.heal_and_execute(
                initial_sql=sql_query,
                initial_error=str(exec_error),
                execute_sql_func=_run_sql,
                db_description=db_description,
                question=queries_history[-1],
                database_type=db_type,
            )

            if not healing_result.get("success"):
                yield {
                    "type": "healing_failed",
                    "final_response": False,
                    "message": (
                        f"❌ Failed to heal query after "
                        f"{healing_result.get('attempts', 0)} attempt(s)"
                    ),
                    "final_error": healing_result.get("final_error", str(exec_error)),
                }
                raise exec_error

            sql_query = healing_result["sql_query"]
            answer_an["sql_query"] = sql_query
            query_results = healing_result["query_results"]

            yield {
                "type": "healing_success",
                "final_response": False,
                "message": (
                    f"✅ Query healed and executed successfully after "
                    f"{healing_result.get('attempts', 0)} attempt(s)"
                ),
                "healed_sql": sql_query,
                "attempts": healing_result.get("attempts", 0),
            }

        if query_results:
            yield {
                "type": "query_result",
                "data": query_results,
                "final_response": False,
            }

        if is_schema_modifying:
            async for ev in _emit_schema_refresh(
                loader_class, namespaced, db_url, operation_type,
                db=db, mark_final_response=True,
            ):
                yield ev

        step_num = "4" if is_schema_modifying else "3"
        yield {
            "type": "reasoning_step",
            "final_response": False,
            "message": f"Step {step_num}: Generating user-friendly response",
        }

        user_readable_response = format_ai_response(
            queries_history=queries_history,
            result_history=result_history,
            sql_query=sql_query,
            query_results=query_results,
            db_description=db_description,
            custom_api_key=custom_api_key,
            custom_model=custom_model,
        )

        yield {
            "type": "ai_response",
            "final_response": True,
            "message": user_readable_response,
        }
    except Exception as e:  # pylint: disable=broad-exception-caught
        execution_error_msg = str(e)
        logging.error("Error executing SQL query: %s", str(e))  # nosemgrep
        yield {
            "type": "error",
            "final_response": True,
            "message": "Error executing SQL query",
        }
        if not user_readable_response:
            user_readable_response = f"Error executing SQL query: {execution_error_msg}"

    # Always-on usage tracking — independent of ``use_memory``/provider, so it
    # records every query (unlike the optional memory write below).
    record_query_usage_background(
        user_id, namespaced, success=execution_error_msg is None, db=db
    )

    if memory_tool is not None:
        full_response = {
            "question": queries_history[-1],
            "generated_sql": answer_an.get("sql_query", ""),
            "answer": user_readable_response,
            "success": execution_error_msg is None,
        }
        if execution_error_msg:
            full_response["error"] = execution_error_msg
        save_memory_background(
            memory_tool=memory_tool,
            question=queries_history[-1],
            sql_query=answer_an.get("sql_query", ""),
            success=execution_error_msg is None,
            error=execution_error_msg or "",
            full_response=full_response,
            chat_histories=[queries_history, result_history],
        )

    yield _Final(_build_query_result(
        sql_query=answer_an.get("sql_query", ""),
        results=query_results if execution_error_msg is None else [],
        ai_response=user_readable_response,
        confidence=answer_an.get("confidence", 0.0),
        is_valid=True,
        is_destructive=is_destructive,
        execution_time=time.perf_counter() - overall_start,
        missing_information=answer_an.get("missing_information", ""),
        ambiguities=answer_an.get("ambiguities", ""),
        explanation=answer_an.get("explanation", ""),
        error_message=execution_error_msg,
    ))


async def run_confirmed(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    user_id: str,
    graph_id: str,
    confirm_data: Any,
    db: Optional["FalkorDB"] = None,
) -> AsyncGenerator[Union[dict, _Final], None]:
    """Execute a user-confirmed destructive SQL operation.

    Same wire-format-+-_Final shape as ``run_query``. Confirmed destructive
    queries are NOT auto-healed (we just confirmed *this* SQL, not a healed
    variant), so this path skips the healer entirely.
    """
    overall_start = time.perf_counter()
    namespaced = graph_name(user_id, graph_id)

    if is_general_graph(namespaced):
        # Match streaming refusal: even an explicit CONFIRM cannot run writes
        # on a demo graph.
        raise InvalidArgumentError(
            "Destructive operations are not allowed on demo graphs"
        )

    confirmation = (getattr(confirm_data, "confirmation", "") or "").strip().upper()
    sql_query = getattr(confirm_data, "sql_query", "") or ""
    queries_history = getattr(confirm_data, "chat", []) or []
    custom_api_key = getattr(confirm_data, "custom_api_key", None)
    custom_model = getattr(confirm_data, "custom_model", None)
    validate_custom_model(custom_model)

    if not sql_query:
        raise InvalidArgumentError("No SQL query provided")

    question = (
        queries_history[-1] if queries_history else "Destructive operation confirmation"
    )

    if confirmation != "CONFIRM":
        yield {
            "type": "operation_cancelled",
            "message": (
                "Operation cancelled. The destructive SQL query was not executed."
            ),
        }
        yield _Final(_build_query_result(
            sql_query=sql_query, results=[],
            ai_response="Operation cancelled. The destructive SQL query was not executed.",
            is_valid=True, is_destructive=True,
            execution_time=time.perf_counter() - overall_start,
        ))
        return

    use_memory = bool(getattr(confirm_data, "use_memory", False))
    memory_tool = None
    execution_error_msg = None
    user_readable_response = ""
    query_results: list = []

    try:
        # Only create the MemoryTool when the caller asks for it. graphiti_core
        # is in the [server] extra; SDK installs without it would otherwise
        # ImportError here at runtime.
        if use_memory:
            memory_tool = await _create_memory_tool(user_id, namespaced, db=db)
        db_description, db_url = await get_db_description(namespaced, db=db)
        db_type, loader_class = get_database_type_and_loader(db_url)

        if not loader_class:
            yield {"type": "error", "message": "Unable to determine database type"}
            yield _Final(_build_query_result(
                sql_query=sql_query, results=[],
                ai_response="Unable to determine database type",
                is_valid=False, is_destructive=True,
                execution_time=time.perf_counter() - overall_start,
                error_message="Unable to determine database type",
            ))
            return

        yield {"type": "reasoning_step",
               "message": "Step 2: Executing confirmed SQL query"}

        sql_query, was_modified = await quote_identifiers_from_graph(
            sql_query=sql_query, graph_id=namespaced, db_type=db_type, db=db,
        )
        if was_modified:
            logging.info("Confirmed SQL query auto-sanitized")

        is_schema_modifying, operation_type = check_schema_modification(
            sql_query, loader_class,
        )
        query_results = loader_class.execute_sql_query(sql_query, db_url)
        yield {"type": "query_result", "data": query_results}

        if is_schema_modifying:
            async for ev in _emit_schema_refresh(
                loader_class, namespaced, db_url, operation_type, db=db,
            ):
                yield ev

        step_num = "4" if is_schema_modifying else "3"
        yield {"type": "reasoning_step",
               "message": f"Step {step_num}: Generating user-friendly response"}

        user_readable_response = format_ai_response(
            queries_history=queries_history or [question],
            result_history=None,
            sql_query=sql_query,
            query_results=query_results,
            db_description=db_description,
            custom_api_key=custom_api_key,
            custom_model=custom_model,
        )

        yield {"type": "ai_response", "message": user_readable_response}

    except Exception as e:  # pylint: disable=broad-exception-caught
        # Wraps both MemoryTool.create failures and driver-specific execution errors.
        execution_error_msg = str(e) or "Error executing query"
        logging.error("Error executing confirmed SQL query: %s", str(e))  # nosemgrep
        yield {"type": "error", "message": execution_error_msg}
        if not user_readable_response:
            user_readable_response = execution_error_msg

    # Always-on usage tracking — see note in ``run_query``.
    record_query_usage_background(
        user_id, namespaced, success=execution_error_msg is None, db=db
    )

    if memory_tool is not None:
        save_memory_background(
            memory_tool=memory_tool,
            question=question,
            sql_query=sql_query,
            success=execution_error_msg is None,
            error=execution_error_msg or "",
        )

    yield _Final(_build_query_result(
        sql_query=sql_query,
        results=query_results if execution_error_msg is None else [],
        ai_response=user_readable_response,
        is_valid=True, is_destructive=True,
        execution_time=time.perf_counter() - overall_start,
        error_message=execution_error_msg,
    ))



async def _resolve_refresh_target(
    user_id: str, graph_id: str, db: Optional["FalkorDB"] = None,
) -> tuple[str, str]:
    """Validate refresh prerequisites and return ``(namespaced, db_url)``.

    Raises:
        InvalidArgumentError: For demo graphs, which are read-only.
        InternalError: When no source URL is on record for the graph.
    """
    namespaced = graph_name(user_id, graph_id)
    if is_general_graph(namespaced):
        raise InvalidArgumentError("Demo graphs cannot be refreshed")

    _, db_url = await get_db_description(namespaced, db=db)
    if not db_url or db_url == "No URL available for this database.":
        raise InternalError("No database URL found for this graph")

    return namespaced, db_url


async def refresh_database_schema(user_id: str, graph_id: str, db=None):
    """
    Manually refresh the graph schema from the database.
    This endpoint allows users to manually trigger a schema refresh
    if they suspect the graph is out of sync with the database.
    """
    try:
        _, db_url = await _resolve_refresh_target(user_id, graph_id, db=db)
        return await load_database(db_url, user_id, db=db)
    except (InvalidArgumentError, InternalError):
        raise
    except Exception as e:
        logging.error("Error in refresh_graph_schema: %s", str(e))
        raise InternalError("Internal server error while refreshing schema") from e


async def refresh_schema_for_sdk(
    user_id: str, graph_id: str, db: Optional["FalkorDB"] = None,
) -> RefreshResult:
    """SDK-facing schema refresh that returns a structured ``RefreshResult``.

    The streaming ``refresh_database_schema`` returns a wire-format generator;
    SDK callers want a single dataclass back. Both share the same underlying
    reload via ``load_database_sync``.
    """
    # Lazy import to break the circular dep with schema_loader.
    from api.core.schema_loader import load_database_sync  # pylint: disable=import-outside-toplevel

    try:
        _, db_url = await _resolve_refresh_target(user_id, graph_id, db=db)
    except InternalError as e:
        # SDK contract is to return a RefreshResult, not raise, when the URL
        # is missing. InvalidArgumentError (demo graph) still propagates.
        return RefreshResult(success=False, message=str(e))

    try:
        connection_result = await load_database_sync(db_url, user_id, db=db)
        return RefreshResult(
            success=connection_result.success,
            message=connection_result.message,
        )
    except (RedisError, ConnectionError, OSError) as e:
        logging.error("Error refreshing schema: %s", str(e))
        return RefreshResult(
            success=False,
            message=f"Failed to refresh schema: {str(e)}",
        )


async def delete_database(user_id: str, graph_id: str, db=None):
    """Delete the specified graph (namespaced to the user).

    This will attempt to delete the FalkorDB graph belonging to the
    authenticated user. The graph id used by the client is stripped of
    namespace and will be namespaced using the user's id from the request
    state.
    """
    namespaced = graph_name(user_id, graph_id)
    if is_general_graph(graph_id):
        raise InvalidArgumentError("Demo graphs cannot be deleted")

    try:
        # Select and delete the graph using the FalkorDB client API
        graph = resolve_db(db).select_graph(namespaced)
        await graph.delete()
        return {"success": True, "graph": graph_id}
    except ResponseError as re:
        raise GraphNotFoundError("Failed to delete graph, Graph not found") from re
    except (RedisError, ConnectionError) as e:
        logging.exception("Failed to delete graph %s: %s", sanitize_log_input(namespaced), e)
        raise InternalError("Failed to delete graph") from e
    except Exception as e:  # pylint: disable=broad-exception-caught
        # Catch-all so any future driver-specific exception is wrapped into
        # a consistent API/SDK error contract instead of leaking as a 500.
        logging.exception(
            "Unexpected error deleting graph %s: %s", sanitize_log_input(namespaced), e,
        )
        raise InternalError("Failed to delete graph") from e
