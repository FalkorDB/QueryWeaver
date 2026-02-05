"""SDK Non-Streaming Functions for Text2SQL.

This module provides non-streaming alternatives for the SDK, returning
structured results instead of async generators.
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional, Type

from redis import RedisError

from api.agents import AnalysisAgent, RelevancyAgent, ResponseFormatterAgent, FollowUpAgent
from api.agents.healer_agent import HealerAgent
from api.config import Config
from api.core.errors import InvalidArgumentError
from api.graph import find, get_db_description, get_user_rules
from api.loaders.base_loader import BaseLoader
from api.loaders.mysql_loader import MySQLLoader
from api.loaders.postgres_loader import PostgresLoader
from api.memory.graphiti_tool import MemoryTool
from api.sql_utils import SQLIdentifierQuoter, DatabaseSpecificQuoter
from queryweaver_sdk.models import QueryResult, QueryMetadata, QueryAnalysis, RefreshResult


GENERAL_PREFIX = os.getenv("GENERAL_PREFIX")


def _build_query_result(
    sql_query: str,
    results: list,
    ai_response: str,
    metadata: QueryMetadata,
    analysis_result: Optional["_AnalysisResult"] = None,
) -> QueryResult:
    """Build a QueryResult from components."""
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


def _graph_name(user_id: str, graph_id: str) -> str:
    """Generate namespaced graph name."""
    return f"{user_id}_{graph_id}"


def _get_database_type_and_loader(
    db_url: str
) -> tuple[Optional[str], Optional[Type[BaseLoader]]]:
    """Determine database type and loader from URL."""
    if db_url.startswith(('postgresql://', 'postgres://')):
        return 'postgresql', PostgresLoader
    if db_url.startswith('mysql://'):
        return 'mysql', MySQLLoader
    return None, None


def _sanitize_query(query: str) -> str:
    """Sanitize query for logging."""
    if len(query) > 200:
        return query[:200] + "..."
    return query


def _validate_chat_data(chat_data) -> tuple[list, Optional[list], Optional[str], bool]:
    """
    Validate and extract chat data fields.
    
    Returns:
        Tuple of (queries_history, result_history, instructions, use_user_rules)
        
    Raises:
        InvalidArgumentError: If chat data is invalid.
    """
    queries_history = getattr(chat_data, 'chat', None)
    result_history = getattr(chat_data, 'result', None)
    instructions = getattr(chat_data, 'instructions', None)
    use_user_rules = getattr(chat_data, 'use_user_rules', True)

    if not queries_history or not isinstance(queries_history, list):
        raise InvalidArgumentError("Invalid or missing chat history")

    if len(queries_history) == 0:
        raise InvalidArgumentError("Empty chat history")

    return queries_history, result_history, instructions, use_user_rules


def _truncate_history(
    queries_history: list,
    result_history: Optional[list]
) -> tuple[list, Optional[list]]:
    """Truncate history to configured length."""
    if len(queries_history) > Config.SHORT_MEMORY_LENGTH:
        queries_history = queries_history[-Config.SHORT_MEMORY_LENGTH:]
        if result_history and len(result_history) > 0:
            max_results = Config.SHORT_MEMORY_LENGTH - 1
            if max_results > 0:
                result_history = result_history[-max_results:]
            else:
                result_history = []
    return queries_history, result_history


@dataclass
class _ExecutionContext:
    """Context for SQL query execution."""
    loader_class: Type[BaseLoader]
    db_url: str
    db_description: str
    db_type: Optional[str]
    known_tables: set = field(default_factory=set)


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


def _parse_analysis_result(answer_an: dict, sql_query_raw: str) -> _AnalysisResult:
    """Parse analysis agent response into structured result."""
    sql_query = answer_an.get("sql_query", sql_query_raw)
    sql_type = sql_query.strip().split()[0].upper() if sql_query else ""
    destructive_ops = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER', 'TRUNCATE']

    return _AnalysisResult(
        sql_query=sql_query,
        confidence=answer_an.get("confidence", 0.0),
        is_valid=answer_an.get("is_sql_translatable", False),
        is_destructive=sql_type in destructive_ops,
        missing_info=answer_an.get("missing_information", ""),
        ambiguities=answer_an.get("ambiguities", ""),
        explanation=answer_an.get("explanation", ""),
    )


async def _execute_query_with_healing(
    sql_query: str,
    context: _ExecutionContext,
    question: str,
) -> tuple[str, list]:
    """
    Execute SQL query with auto-quoting and healing on failure.

    Returns:
        Tuple of (final_sql_query, query_results)

    Raises:
        Exception: If query fails and cannot be healed.
    """
    quote_char = DatabaseSpecificQuoter.get_quote_char(context.db_type or 'postgresql')
    sanitized_sql, was_modified = SQLIdentifierQuoter.auto_quote_identifiers(
        sql_query, context.known_tables, quote_char
    )
    if was_modified:
        sql_query = sanitized_sql

    try:
        query_results = context.loader_class.execute_sql_query(sql_query, context.db_url)
        return sql_query, query_results
    except (RedisError, ConnectionError, OSError) as exec_error:
        healer_agent = HealerAgent(max_healing_attempts=3)

        def execute_sql(sql: str):
            return context.loader_class.execute_sql_query(sql, context.db_url)

        healing_result = healer_agent.heal_and_execute(
            initial_sql=sql_query,
            initial_error=str(exec_error),
            execute_sql_func=execute_sql,
            db_description=context.db_description,
            question=question,
            database_type=context.db_type
        )

        if not healing_result.get("success"):
            raise exec_error

        return healing_result["sql_query"], healing_result["query_results"]


@dataclass
class _ChatContext:
    """Chat history and configuration context."""
    queries_history: list
    result_history: Optional[list]
    instructions: Optional[str]
    use_user_rules: bool


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


async def _initialize_query_context(
    user_id: str, graph_id: str, chat_data
) -> _QueryContext:
    """Initialize query context with database info."""
    graph_id = _graph_name(user_id, graph_id)
    queries_history, result_history, instructions, use_user_rules = _validate_chat_data(
        chat_data
    )
    queries_history, result_history = _truncate_history(queries_history, result_history)

    overall_start = time.perf_counter()
    logging.info("SDK Query: %s", _sanitize_query(queries_history[-1]))

    memory_tool = None
    if getattr(chat_data, 'use_memory', False):
        memory_tool = await MemoryTool.create(user_id, graph_id)

    db_description, db_url = await get_db_description(graph_id)
    user_rules_spec = await get_user_rules(graph_id) if use_user_rules else None

    chat_ctx = _ChatContext(
        queries_history=queries_history,
        result_history=result_history,
        instructions=instructions,
        use_user_rules=use_user_rules,
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
    )


async def _check_relevancy_and_find_tables(
    ctx: _QueryContext,
    agent_rel: RelevancyAgent,
) -> tuple[Optional[dict], Optional[list]]:
    """Check relevancy and find relevant tables concurrently.

    Returns:
        Tuple of (off_topic_reason or None, tables or None).
        If off_topic_reason is set, the query is off-topic.
    """
    find_task = asyncio.create_task(
        find(ctx.db.graph_id, ctx.chat.queries_history, ctx.db.db_description)
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
            logging.debug("Cancelled find_task after determining query was off-topic")
        return answer_rel, None

    result = await find_task
    return None, result


async def _execute_and_format_query(
    ctx: _QueryContext,
    analysis: _AnalysisResult,
    tables: Optional[list],
    loader_class: Type[BaseLoader],
    db_type: Optional[str],
) -> QueryResult:
    """Execute query with healing and format the response."""
    known_tables = {table[0] for table in tables} if tables else set()
    exec_context = _ExecutionContext(
        loader_class=loader_class,
        db_url=ctx.db.db_url,
        db_description=ctx.db.db_description,
        db_type=db_type,
        known_tables=known_tables,
    )

    final_sql, query_results = await _execute_query_with_healing(
        analysis.sql_query, exec_context, ctx.chat.queries_history[-1]
    )

    # Generate AI response
    response_agent = ResponseFormatterAgent()
    ai_response = response_agent.format_response(
        user_query=ctx.chat.queries_history[-1],
        sql_query=final_sql,
        query_results=query_results,
        db_description=ctx.db.db_description
    )

    execution_time = time.perf_counter() - ctx.overall_start

    # Save to memory in background if enabled
    if ctx.memory_tool:
        asyncio.create_task(
            ctx.memory_tool.save_query_memory(
                query=ctx.chat.queries_history[-1],
                sql_query=final_sql,
                success=True,
                error=""
            )
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
            execution_time=execution_time,
        ),
        analysis_result=analysis,
    )


async def query_database_sync(
    user_id: str,
    graph_id: str,
    chat_data
) -> QueryResult:
    """
    Query the database and return a structured result (non-streaming).

    This is the SDK-friendly version that returns a QueryResult dataclass
    instead of an async generator for HTTP streaming.

    Args:
        user_id: The user identifier for namespacing.
        graph_id: The ID of the graph/database to query.
        chat_data: The chat data containing user queries and context.

    Returns:
        QueryResult with SQL query, results, and AI response.
    """
    ctx = await _initialize_query_context(user_id, graph_id, chat_data)

    # Determine database type early for validation
    db_type, loader_class = _get_database_type_and_loader(ctx.db.db_url)

    if not loader_class:
        return _build_query_result(
            sql_query="",
            results=[],
            ai_response="Unable to determine database type",
            metadata=QueryMetadata(
                confidence=0.0,
                is_valid=False,
                execution_time=time.perf_counter() - ctx.overall_start,
            ),
        )

    # Run relevancy check and find tables concurrently
    agent_rel = RelevancyAgent(ctx.chat.queries_history, ctx.chat.result_history)
    off_topic, tables = await _check_relevancy_and_find_tables(ctx, agent_rel)

    if off_topic:
        return _build_query_result(
            sql_query="",
            results=[],
            ai_response=f"Off topic question: {off_topic['reason']}",
            metadata=QueryMetadata(
                confidence=0.0,
                is_valid=False,
                execution_time=time.perf_counter() - ctx.overall_start,
            ),
        )

    # Get memory context and generate SQL analysis
    agent_an = AnalysisAgent(ctx.chat.queries_history, ctx.chat.result_history)
    memory_context = (
        await ctx.memory_tool.search_memories(query=ctx.chat.queries_history[-1])
        if ctx.memory_tool else None
    )
    answer_an = agent_an.get_analysis(
        ctx.chat.queries_history[-1], tables, ctx.db.db_description,
        ctx.chat.instructions, memory_context, db_type, ctx.db.user_rules_spec
    )

    analysis = _parse_analysis_result(answer_an, "")

    if not analysis.is_valid:
        follow_up_agent = FollowUpAgent(ctx.chat.queries_history, ctx.chat.result_history)
        return _build_query_result(
            sql_query=analysis.sql_query,
            results=[],
            ai_response=follow_up_agent.generate_follow_up_question(
                user_question=ctx.chat.queries_history[-1],
                analysis_result=answer_an
            ),
            metadata=QueryMetadata(
                confidence=analysis.confidence,
                is_valid=False,
                is_destructive=analysis.is_destructive,
                requires_confirmation=False,
                execution_time=time.perf_counter() - ctx.overall_start,
            ),
            analysis_result=analysis,
        )

    # Check if requires confirmation
    if analysis.is_destructive and not (
        GENERAL_PREFIX and ctx.db.graph_id.startswith(GENERAL_PREFIX)
    ):
        return _build_query_result(
            sql_query=analysis.sql_query,
            results=[],
            ai_response=(
                "This is a destructive operation. Please confirm execution "
                "by calling execute_confirmed() with the SQL query."
            ),
            metadata=QueryMetadata(
                confidence=analysis.confidence,
                is_valid=True,
                is_destructive=True,
                requires_confirmation=True,
                execution_time=time.perf_counter() - ctx.overall_start,
            ),
            analysis_result=analysis,
        )

    # Execute the query
    try:
        return await _execute_and_format_query(
            ctx, analysis, tables, loader_class, db_type
        )
    except (RedisError, ConnectionError, OSError) as e:
        logging.error("Error executing SQL query: %s", str(e))
        return _build_query_result(
            sql_query=analysis.sql_query,
            results=[],
            ai_response=f"Error executing SQL query: {str(e)}",
            metadata=QueryMetadata(
                confidence=analysis.confidence,
                is_valid=True,
                is_destructive=analysis.is_destructive,
                requires_confirmation=False,
                execution_time=time.perf_counter() - ctx.overall_start,
            ),
            analysis_result=analysis,
        )


async def execute_destructive_operation_sync(
    user_id: str,
    graph_id: str,
    confirm_data,
) -> QueryResult:
    """
    Execute a confirmed destructive operation and return structured result.

    SDK-friendly version that returns QueryResult instead of streaming.

    Args:
        user_id: The user identifier.
        graph_id: The graph/database identifier.
        confirm_data: Confirmation request with SQL query.

    Returns:
        QueryResult with execution results.
    """
    graph_id = _graph_name(user_id, graph_id)

    confirmation = getattr(confirm_data, 'confirmation', "")
    if confirmation:
        confirmation = confirmation.strip().upper()
    sql_query = getattr(confirm_data, 'sql_query', "")
    queries_history = getattr(confirm_data, 'chat', [])

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
                execution_time=time.perf_counter() - overall_start,
            ),
        )

    try:
        db_description, db_url = await get_db_description(graph_id)
        _, loader_class = _get_database_type_and_loader(db_url)

        if not loader_class:
            return _build_query_result(
                sql_query=sql_query,
                results=[],
                ai_response="Unable to determine database type",
                metadata=QueryMetadata(
                    confidence=0.0,
                    is_valid=False,
                    execution_time=time.perf_counter() - overall_start,
                ),
            )

        # Execute SQL
        query_results = loader_class.execute_sql_query(sql_query, db_url)

        # Generate response
        response_agent = ResponseFormatterAgent()
        ai_response = response_agent.format_response(
            user_query=queries_history[-1] if queries_history else "Destructive operation",
            sql_query=sql_query,
            query_results=query_results,
            db_description=db_description
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
                execution_time=time.perf_counter() - overall_start,
            ),
        )

    except (RedisError, ConnectionError, OSError) as e:
        logging.error("Error executing confirmed SQL: %s", str(e))
        return _build_query_result(
            sql_query=sql_query,
            results=[],
            ai_response=f"Error executing query: {str(e)}",
            metadata=QueryMetadata(
                confidence=0.0,
                is_valid=True,
                is_destructive=True,
                requires_confirmation=False,
                execution_time=time.perf_counter() - overall_start,
            ),
        )


async def refresh_database_schema_sync(user_id: str, graph_id: str) -> RefreshResult:
    """
    Refresh database schema and return structured result.

    SDK-friendly version that returns RefreshResult instead of streaming.

    Args:
        user_id: The user identifier.
        graph_id: The graph/database identifier.

    Returns:
        RefreshResult with refresh status.
    """
    # Imported here to break circular dependency between text2sql_sync and schema_loader
    from api.core.schema_loader import load_database_sync  # pylint: disable=import-outside-toplevel

    namespaced = _graph_name(user_id, graph_id)

    if GENERAL_PREFIX and graph_id.startswith(GENERAL_PREFIX):
        raise InvalidArgumentError("Demo graphs cannot be refreshed")

    try:
        _, db_url = await get_db_description(namespaced)

        if not db_url or db_url == "No URL available for this database.":
            return RefreshResult(
                success=False,
                message="No database URL found for this graph",
            )

        # Use the sync version of load_database
        connection_result = await load_database_sync(db_url, user_id)

        return RefreshResult(
            success=connection_result.success,
            message=connection_result.message,
            tables_updated=connection_result.tables_loaded,
        )

    except (RedisError, ConnectionError, OSError) as e:
        logging.error("Error refreshing schema: %s", str(e))
        return RefreshResult(
            success=False,
            message=f"Failed to refresh schema: {str(e)}",
        )
