"""End-to-end QueryWeaver SDK example against the e-commerce schema.

Connects to the demo PostgreSQL database (loaded from
``ecommerce_example.sql``), introspects the schema into FalkorDB, runs a
one-shot natural-language query, then a follow-up that uses chat history,
and finally tears down the loaded schema.

Required environment variables:
    FALKORDB_URL         e.g. redis://localhost:6379
    OPENAI_API_KEY       — or any other LiteLLM-supported provider
                           (AZURE_API_KEY+AZURE_API_BASE+AZURE_API_VERSION,
                            GEMINI_API_KEY, ANTHROPIC_API_KEY, COHERE_API_KEY)

Required (for the demo Postgres loaded from ``ecommerce_example.sql``):
    DEMO_POSTGRES_URL    e.g. postgresql://USER:PASSWORD@localhost:5432/queryweaver_demo
"""

import asyncio
import os
from urllib.parse import urlparse

from queryweaver import QueryRequest, QueryWeaver


def _redact_url(url: str) -> str:
    """Render a connection URL without leaking the password."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    user = f"{parsed.username}@" if parsed.username else ""
    return f"{parsed.scheme}://{user}{host}{parsed.path}"


POSTGRES_URL = os.environ.get("DEMO_POSTGRES_URL", "")
FALKORDB_URL = os.environ.get("FALKORDB_URL", "redis://localhost:6379")

if not POSTGRES_URL:
    raise SystemExit(
        "Set DEMO_POSTGRES_URL, e.g. "
        "postgresql://USER:PASSWORD@localhost:5432/queryweaver_demo"
    )


def _print_rows(rows, limit=10):
    for row in rows[:limit]:
        print(f"  {row}")
    if len(rows) > limit:
        print(f"  ... ({len(rows) - limit} more rows)")


async def main() -> None:
    async with QueryWeaver(falkordb_url=FALKORDB_URL, user_id="demo") as qw:
        print(f"Connecting to PostgreSQL at {_redact_url(POSTGRES_URL)}")
        conn = await qw.connect_database(POSTGRES_URL)
        if not conn.success:
            raise SystemExit(f"connect failed: {conn.message}")
        print(f"  connected; database_id={conn.database_id}\n")

        schema = await qw.get_schema(conn.database_id)
        print(f"Schema: {len(schema.nodes)} tables, {len(schema.links)} relationships\n")

        # 1) One-shot query
        question = (
            "Show each customer's total spending and number of orders, "
            "sorted by total spending descending"
        )
        print(f"Q: {question}")
        result = await qw.query(conn.database_id, question)
        print(f"\n  SQL: {result.sql_query}")
        print(f"  Rows ({len(result.results)}):")
        _print_rows(result.results)
        print(f"\n  AI summary: {result.ai_response}")
        print(
            f"  (confidence={result.metadata.confidence:.2f}, "
            f"took {result.metadata.execution_time:.2f}s)\n"
        )

        # 2) Multi-turn: follow-up uses chat_history + result_history
        first_q = "Show all products with their categories"
        print(f"Q: {first_q}")
        first = await qw.query(conn.database_id, first_q)
        print(f"  -> {len(first.results)} rows\n")

        followup_q = "Of those, which ones have an average review rating above 4?"
        print(f"Q (follow-up): {followup_q}")
        followup = QueryRequest(
            question=followup_q,
            chat_history=[first_q],
            result_history=[first.ai_response],
        )
        second = await qw.query(conn.database_id, followup)
        print(f"\n  SQL: {second.sql_query}")
        print(f"  Rows ({len(second.results)}):")
        _print_rows(second.results)
        print()

        await qw.delete_database(conn.database_id)
        print(f"Cleaned up: removed schema for {conn.database_id} from FalkorDB")


if __name__ == "__main__":
    asyncio.run(main())
