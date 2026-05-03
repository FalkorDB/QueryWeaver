"""SDK Non-Streaming Functions for Text2SQL.

Thin orchestrator over helpers in :mod:`api.core.text2sql_common` — the
same helpers the streaming path uses. Only transport differs.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional, Type

from redis import RedisError

from api.agents import AnalysisAgent, FollowUpAgent, RelevancyAgent
from api.core.errors import InvalidArgumentError
from api.core.text2sql_common import (
    auto_quote_sql_identifiers,
    build_destructive_confirmation_message,
    detect_destructive_operation,
    execute_with_healing,
    format_ai_response,
    get_database_type_and_loader,
    graph_name,
    is_general_graph,
    quote_identifiers_from_graph,
    refresh_schema_if_modified,
    save_memory_background,
    truncate_for_log,
    validate_and_truncate_chat,
    validate_custom_model,
)
from api.graph import find, get_db_description, get_user_rules
from api.loaders.base_loader import BaseLoader
from api.memory.graphiti_tool import MemoryTool
from api.core.result_models import QueryAnalysis, QueryMetadata, QueryResult, RefreshResult


# ---------------------------------------------------------------------------
# Internal dataclasses
# ---------------------------------------------------------------------------


@dataclass
class _AnalysisResult:
    """Result from SQL analysis agent."""
    sql_query: str
    confidence: float
    is_valid: bool
    is_destructive: bool
    missing_info: str
    ambiguities: str
    explanation: str


@dataclass
class _ChatContext:
    """Chat history and configuration context."""
    queries_history: list
    result_history: Optional[list]
    instructions: Optional[str]
    custom_api_key: Optional[str] = None
    custom_model: Optional[str] = None


@dataclass
class _DatabaseContext:
    """Database connection context."""
    graph_id: str
    db_description: str
    db_url: str
    user_rules_spec: Optional[str] = None


@dataclass
class _QueryContext:
    """Combined context for query execution."""
    chat: _ChatContext
    db: _DatabaseContext
    overall_start: float
    memory_tool: Optional[MemoryTool] = None
    falkor_db: Any = None  # Injected FalkorDB handle (None ⇒ resolver fallback)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_query_result(
    sql_query: str,
    results: list,
    ai_response: str,
    metadata: QueryMetadata,
    analysis_result: Optional[_AnalysisResult] = None,
) -> QueryResult:
    """Assemble a :class:`QueryResult` from pipeline outputs."""
    if analysis_result:
        analysis = QueryAnalysis(
            missing_information=analysis_result.missing_info,
            ambiguities=analysis_result.ambiguities,
            explanation=analysis_result.explanation,
        )
    else:
        analysis = QueryAnalysis()

    return QueryResult(
        sql_query=sql_query,
        results=results,
        ai_response=ai_response,
        metadata=metadata,
        analysis=analysis,
    )


def _parse_analysis_result(answer_an: dict) -> _AnalysisResult:
    """Parse the AnalysisAgent response into a typed result."""
    sql_query = answer_an.get("sql_query", "")
    _, is_destructive = detect_destructive_operation(sql_query)

    return _AnalysisResult(
        sql_query=sql_query,
        confidence=answer_an.get("confidence", 0.0),
        is_valid=answer_an.get("is_sql_translatable", False),
        is_destructive=is_destructive,
        missing_info=answer_an.get("missing_information", ""),
        ambiguities=answer_an.get("ambiguities", ""),
        explanation=answer_an.get("explanation", ""),
    )


async def _initialize_query_context(  # pylint: disable=too-many-locals
    user_id: str, graph_id: str, chat_data, falkor_db=None,
) -> _QueryContext:
    """Build the per-query context (graph name, history, db metadata, memory tool)."""
    graph_id = graph_name(user_id, graph_id)
    queries_history, result_history, instructions, use_user_rules = (
        validate_and_truncate_chat(chat_data)
    )

    overall_start = time.perf_counter()
    logging.info("SDK Query: %s", truncate_for_log(queries_history[-1]))

    memory_tool = None
    if getattr(chat_data, 'use_memory', False):
        memory_tool = await MemoryTool.create(user_id, graph_id, db=falkor_db)

    db_description, db_url = await get_db_description(graph_id, db=falkor_db)
    user_rules_spec = (
        await get_user_rules(graph_id, db=falkor_db) if use_user_rules else None
    )

    custom_model = getattr(chat_data, 'custom_model', None)
    validate_custom_model(custom_model)

    chat_ctx = _ChatContext(
        queries_history=queries_history,
        result_history=result_history,
        instructions=instructions,
        custom_api_key=getattr(chat_data, 'custom_api_key', None),
        custom_model=custom_model,
    )
    db_ctx = _DatabaseContext(
        graph_id=graph_id,
        db_description=db_description,
        db_url=db_url,
        user_rules_spec=user_rules_spec,
    )

    return _QueryContext(
        chat=chat_ctx,
        db=db_ctx,
        overall_start=overall_start,
        memory_tool=memory_tool,
        falkor_db=falkor_db,
    )


async def _check_relevancy_and_find_tables(
    ctx: _QueryContext,
    agent_rel: RelevancyAgent,
) -> tuple[Optional[dict], Optional[list]]:
    """Run relevancy check and table-finding concurrently, short-circuit off-topic."""
    find_task = asyncio.create_task(
        find(
            ctx.db.graph_id,
            ctx.chat.queries_history,
            ctx.db.db_description,
            db=ctx.falkor_db,
        )
    )
    relevancy_task = asyncio.create_task(
        agent_rel.get_answer(ctx.chat.queries_history[-1], ctx.db.db_description)
    )

    answer_rel = await relevancy_task

    if answer_rel["status"] != "On-topic":
        find_task.cancel()
        try:
            await find_task
        except asyncio.CancelledError:
            logging.debug("Cancelled find_task after off-topic determination")
        return answer_rel, None

    return None, await find_task


def _elapsed(start: float) -> float:
    return time.perf_counter() - start


def _invalid_sql_result(
    ctx: _QueryContext,
    analysis: _AnalysisResult,
    answer_an: dict,
) -> QueryResult:
    """Return the follow-up question branch when SQL is not translatable."""
    follow_up = FollowUpAgent(
        ctx.chat.queries_history,
        ctx.chat.result_history,
        ctx.chat.custom_api_key,
        ctx.chat.custom_model,
    )
    return _build_query_result(
        sql_query=analysis.sql_query,
        results=[],
        ai_response=follow_up.generate_follow_up_question(
            user_question=ctx.chat.queries_history[-1],
            analysis_result=answer_an,
        ),
        metadata=QueryMetadata(
            confidence=analysis.confidence,
            is_valid=False,
            is_destructive=analysis.is_destructive,
            requires_confirmation=False,
            execution_time=_elapsed(ctx.overall_start),
        ),
        analysis_result=analysis,
    )


def _confirmation_required_result(
    ctx: _QueryContext, analysis: _AnalysisResult,
) -> QueryResult:
    """Return the confirmation-needed branch for destructive operations."""
    sql_type, _ = detect_destructive_operation(analysis.sql_query)
    return _build_query_result(
        sql_query=analysis.sql_query,
        results=[],
        ai_response=build_destructive_confirmation_message(sql_type, analysis.sql_query),
        metadata=QueryMetadata(
            confidence=analysis.confidence,
            is_valid=True,
            is_destructive=True,
            requires_confirmation=True,
            execution_time=_elapsed(ctx.overall_start),
        ),
        analysis_result=analysis,
    )


async def _execute_and_format_query(
    ctx: _QueryContext,
    analysis: _AnalysisResult,
    tables: Optional[list],
    loader_class: Type[BaseLoader],
    db_type: Optional[str],
) -> QueryResult:
    """Execute SQL (with healing + schema refresh) and build the user-facing response."""
    # Auto-quote identifiers from the Table list we already loaded.
    known_tables = {t[0] for t in tables} if tables else set()
    sql_to_run, was_modified = auto_quote_sql_identifiers(
        analysis.sql_query, known_tables, db_type,
    )
    if was_modified:
        logging.info("SQL auto-quoted: table identifiers with special characters")

    final_sql, query_results = await execute_with_healing(
        sql_query=sql_to_run,
        loader_class=loader_class,
        db_url=ctx.db.db_url,
        db_description=ctx.db.db_description,
        question=ctx.chat.queries_history[-1],
        db_type=db_type,
    )

    await refresh_schema_if_modified(
        sql_query=final_sql,
        loader_class=loader_class,
        graph_id=ctx.db.graph_id,
        db_url=ctx.db.db_url,
        db=ctx.falkor_db,
    )

    ai_response = format_ai_response(
        queries_history=ctx.chat.queries_history,
        result_history=ctx.chat.result_history,
        sql_query=final_sql,
        query_results=query_results,
        db_description=ctx.db.db_description,
        custom_api_key=ctx.chat.custom_api_key,
        custom_model=ctx.chat.custom_model,
    )

    if ctx.memory_tool:
        save_memory_background(
            memory_tool=ctx.memory_tool,
            question=ctx.chat.queries_history[-1],
            sql_query=final_sql,
            success=True,
            error="",
            full_response={
                "question": ctx.chat.queries_history[-1],
                "generated_sql": final_sql,
                "answer": ai_response,
                "success": True,
            },
            chat_histories=[ctx.chat.queries_history, ctx.chat.result_history],
        )

    return _build_query_result(
        sql_query=final_sql,
        results=query_results,
        ai_response=ai_response,
        metadata=QueryMetadata(
            confidence=analysis.confidence,
            is_valid=True,
            is_destructive=analysis.is_destructive,
            requires_confirmation=False,
            execution_time=_elapsed(ctx.overall_start),
        ),
        analysis_result=analysis,
    )


# ---------------------------------------------------------------------------
# Public SDK entrypoints
# ---------------------------------------------------------------------------


async def query_database_sync(  # pylint: disable=too-many-return-statements
    user_id: str,
    graph_id: str,
    chat_data,
    db=None,
) -> QueryResult:
    """Convert a natural-language question to SQL, execute it, and return a result.

    Args:
        user_id: Namespacing identifier.
        graph_id: Target graph/database id (un-prefixed; namespacing is applied).
        chat_data: Request-shaped object carrying chat history, instructions, etc.
        db: Optional FalkorDB handle; falls back to the server singleton.
    """
    ctx = await _initialize_query_context(user_id, graph_id, chat_data, falkor_db=db)

    db_type, loader_class = get_database_type_and_loader(ctx.db.db_url)
    if not loader_class:
        return _build_query_result(
            sql_query="",
            results=[],
            ai_response="Unable to determine database type",
            metadata=QueryMetadata(
                confidence=0.0,
                is_valid=False,
                execution_time=_elapsed(ctx.overall_start),
            ),
        )

    agent_rel = RelevancyAgent(
        ctx.chat.queries_history,
        ctx.chat.result_history,
        ctx.chat.custom_api_key,
        ctx.chat.custom_model,
    )
    off_topic, tables = await _check_relevancy_and_find_tables(ctx, agent_rel)

    if off_topic:
        return _build_query_result(
            sql_query="",
            results=[],
            ai_response=f"Off topic question: {off_topic['reason']}",
            metadata=QueryMetadata(
                confidence=0.0,
                is_valid=False,
                execution_time=_elapsed(ctx.overall_start),
            ),
        )

    agent_an = AnalysisAgent(
        ctx.chat.queries_history,
        ctx.chat.result_history,
        ctx.chat.custom_api_key,
        ctx.chat.custom_model,
    )
    memory_context = (
        await ctx.memory_tool.search_memories(query=ctx.chat.queries_history[-1])
        if ctx.memory_tool else None
    )
    answer_an = agent_an.get_analysis(
        ctx.chat.queries_history[-1],
        tables,
        ctx.db.db_description,
        ctx.chat.instructions,
        memory_context,
        db_type,
        ctx.db.user_rules_spec,
    )

    analysis = _parse_analysis_result(answer_an)

    if not analysis.is_valid:
        return _invalid_sql_result(ctx, analysis, answer_an)

    if analysis.is_destructive and not is_general_graph(ctx.db.graph_id):
        return _confirmation_required_result(ctx, analysis)

    try:
        return await _execute_and_format_query(ctx, analysis, tables, loader_class, db_type)
    except Exception as e:  # pylint: disable=broad-exception-caught
        # Broad catch: healer re-raises driver-specific exceptions on failure.
        logging.error("Error executing SQL query: %s", str(e))

        if ctx.memory_tool:
            save_memory_background(
                memory_tool=ctx.memory_tool,
                question=ctx.chat.queries_history[-1],
                sql_query=analysis.sql_query,
                success=False,
                error=str(e),
            )

        return _build_query_result(
            sql_query=analysis.sql_query,
            results=[],
            ai_response=f"Error executing SQL query: {str(e)}",
            metadata=QueryMetadata(
                confidence=analysis.confidence,
                is_valid=True,
                is_destructive=analysis.is_destructive,
                requires_confirmation=False,
                execution_time=_elapsed(ctx.overall_start),
            ),
            analysis_result=analysis,
        )


async def execute_destructive_operation_sync(  # pylint: disable=too-many-locals
    user_id: str,
    graph_id: str,
    confirm_data,
    db=None,
) -> QueryResult:
    """Execute a confirmed destructive operation and return a structured result."""
    namespaced = graph_name(user_id, graph_id)

    if is_general_graph(namespaced):
        # Match the streaming path: demo/general graphs are read-only — even
        # an explicit CONFIRM must not execute writes against them.
        raise InvalidArgumentError(
            "Destructive operations are not allowed on demo graphs"
        )

    graph_id = namespaced

    confirmation = getattr(confirm_data, 'confirmation', "") or ""
    confirmation = confirmation.strip().upper()
    sql_query = getattr(confirm_data, 'sql_query', "")
    queries_history = getattr(confirm_data, 'chat', [])
    custom_api_key = getattr(confirm_data, 'custom_api_key', None)
    custom_model = getattr(confirm_data, 'custom_model', None)

    if not sql_query:
        raise InvalidArgumentError("No SQL query provided")

    overall_start = time.perf_counter()

    if confirmation != "CONFIRM":
        return _build_query_result(
            sql_query=sql_query,
            results=[],
            ai_response="Operation cancelled. The destructive SQL query was not executed.",
            metadata=QueryMetadata(
                confidence=0.0,
                is_valid=True,
                is_destructive=True,
                requires_confirmation=False,
                execution_time=_elapsed(overall_start),
            ),
        )

    memory_tool = await MemoryTool.create(user_id, graph_id, db=db)
    question = queries_history[-1] if queries_history else "Destructive operation confirmation"

    try:
        db_description, db_url = await get_db_description(graph_id, db=db)
        db_type, loader_class = get_database_type_and_loader(db_url)

        if not loader_class:
            return _build_query_result(
                sql_query=sql_query,
                results=[],
                ai_response="Unable to determine database type",
                metadata=QueryMetadata(
                    confidence=0.0,
                    is_valid=False,
                    execution_time=_elapsed(overall_start),
                ),
            )

        sql_query, was_modified = await quote_identifiers_from_graph(
            sql_query=sql_query,
            graph_id=graph_id,
            db_type=db_type,
            db=db,
        )
        if was_modified:
            logging.info("Confirmed SQL query auto-quoted")

        query_results = loader_class.execute_sql_query(sql_query, db_url)

        await refresh_schema_if_modified(
            sql_query=sql_query,
            loader_class=loader_class,
            graph_id=graph_id,
            db_url=db_url,
            db=db,
        )

        ai_response = format_ai_response(
            queries_history=queries_history or [question],
            result_history=None,
            sql_query=sql_query,
            query_results=query_results,
            db_description=db_description,
            custom_api_key=custom_api_key,
            custom_model=custom_model,
        )

        save_memory_background(
            memory_tool=memory_tool,
            question=question,
            sql_query=sql_query,
            success=True,
            error="",
        )

        return _build_query_result(
            sql_query=sql_query,
            results=query_results,
            ai_response=ai_response,
            metadata=QueryMetadata(
                confidence=1.0,
                is_valid=True,
                is_destructive=True,
                requires_confirmation=False,
                execution_time=_elapsed(overall_start),
            ),
        )

    except Exception as e:  # pylint: disable=broad-exception-caught
        # Broad catch: loader_class.execute_sql_query raises driver-specific errors.
        logging.error("Error executing confirmed SQL: %s", str(e))

        save_memory_background(
            memory_tool=memory_tool,
            question=question,
            sql_query=sql_query,
            success=False,
            error=str(e),
        )

        return _build_query_result(
            sql_query=sql_query,
            results=[],
            ai_response=f"Error executing query: {str(e)}",
            metadata=QueryMetadata(
                confidence=0.0,
                is_valid=True,
                is_destructive=True,
                requires_confirmation=False,
                execution_time=_elapsed(overall_start),
            ),
        )


async def refresh_database_schema_sync(user_id: str, graph_id: str, db=None) -> RefreshResult:
    """Refresh the graph schema for a connected database and return status."""
    # Imported here to break the circular import with schema_loader.
    from api.core.schema_loader import load_database_sync  # pylint: disable=import-outside-toplevel

    namespaced = graph_name(user_id, graph_id)

    if is_general_graph(namespaced):
        raise InvalidArgumentError("Demo graphs cannot be refreshed")

    try:
        _, db_url = await get_db_description(namespaced, db=db)

        if not db_url or db_url == "No URL available for this database.":
            return RefreshResult(
                success=False,
                message="No database URL found for this graph",
            )

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
