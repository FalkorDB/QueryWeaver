"""Request dataclasses accepted by the core text2sql API.

Split from ``result_models`` so request/response intents stay distinct.
``queryweaver_sdk.models`` re-exports these for the SDK's public surface.
"""

from dataclasses import dataclass, field


@dataclass
class QueryRequest:  # pylint: disable=too-many-instance-attributes
    """Request parameters for a query operation."""

    question: str
    """The natural language question to convert to SQL."""

    chat_history: list[str] = field(default_factory=list)
    """Previous questions in the conversation for context."""

    result_history: list[str] = field(default_factory=list)
    """Previous results for context."""

    instructions: str | None = None
    """Additional instructions for query generation."""

    use_user_rules: bool = True
    """Whether to apply user-defined rules from the database."""

    use_memory: bool = False
    """Whether to use long-term memory for context."""

    custom_api_key: str | None = None
    """Per-request override for the LLM API key. Falls back to env config."""

    custom_model: str | None = None
    """Per-request override for the LLM model (``vendor/model`` format)."""
