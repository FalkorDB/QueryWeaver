"""Data models for QueryWeaver SDK results.

Thin re-export shim. The dataclasses live in ``api.core.result_models`` /
``api.core.request_models`` so the server code and the SDK share a single
source of truth. Importing from ``queryweaver.models`` still works for
external consumers.
"""

from api.core.request_models import QueryRequest
from api.core.result_models import (
    ChatMessage,
    DatabaseConnection,
    QueryAnalysis,
    QueryMetadata,
    QueryResult,
    RefreshResult,
    SchemaResult,
)

__all__ = [
    "ChatMessage",
    "DatabaseConnection",
    "QueryAnalysis",
    "QueryMetadata",
    "QueryRequest",
    "QueryResult",
    "RefreshResult",
    "SchemaResult",
]
