"""Utility functions for agents."""

import json
import logging
import time
from typing import Any, Dict, List

from litellm import completion
from api.config import Config


def _log_success(label: str, model: str, attempt: int, attempts: int,
                 elapsed: float) -> None:
    """Record a completed call, flagging one slow enough to be worth noticing."""
    logging.info(
        "llm_call label=%s model=%s attempt=%d/%d duration=%.2fs outcome=ok",
        label, model, attempt, attempts, elapsed,
    )
    if elapsed >= Config.LLM_SLOW_CALL_THRESHOLD:
        logging.warning(
            "llm_call label=%s model=%s duration=%.2fs exceeded slow-call "
            "threshold of %.0fs", label, model, elapsed,
            Config.LLM_SLOW_CALL_THRESHOLD,
        )


def _attempt(base_args: Dict[str, Any], remaining: float, overrides: Dict[str, Any]):
    """Issue one provider request bounded by *remaining* seconds.

    Merged into one mapping rather than passed as several ``**`` expansions:
    duplicate keywords are a ``TypeError`` that way, so a caller overriding
    ``timeout`` would crash instead of overriding.
    """
    return completion(**{
        **base_args,
        **Config.llm_call_bounds(timeout=remaining),
        **overrides,
    })


def run_completion(messages: List[Dict[str, str]], custom_model: str | None = None,
                   custom_api_key: str | None = None, *, label: str = "llm",
                   **kwargs) -> str:
    """Run an LLM completion with optional custom model/key overrides.

    Bounds the call with ``Config.llm_call_bounds()``: ``LLM_TIMEOUT`` is the
    budget for the whole call, divided across attempts, so retries cannot push
    the real ceiling past it. Duration is logged. Both exist because the
    2026-07-29 demo failure was an LLM call that stalled with no timeout and
    left no trace of how long it ran. ``label`` names the caller in those log
    lines and is not forwarded to the provider.

    A caller may still override the bounds explicitly; doing so is logged so it
    cannot silently weaken the ceiling.

    Returns the content string from the first choice.
    """
    base_args = {
        "model": custom_model if custom_model else Config.COMPLETION_MODEL,
        "messages": messages,
        "top_p": 1,
    }
    if custom_api_key:
        base_args["api_key"] = custom_api_key

    overrides = {
        key: kwargs[key]
        for key in ("timeout", "max_retries", "num_retries")
        if key in kwargs
    }
    if overrides:
        logging.info(
            "llm_call label=%s bound overrides in effect: %s", label, overrides
        )

    attempts = Config.llm_attempts()
    deadline = time.monotonic() + Config.LLM_TIMEOUT
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break

        # Each attempt gets what is left of the budget, so the total cannot
        # exceed LLM_TIMEOUT however many attempts are made. A retry therefore
        # only happens when time remains — which is the case that matters, a
        # fast transient failure rather than a call that already spent the
        # budget.
        started = time.monotonic()
        try:
            result = _attempt(base_args, remaining, kwargs)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            last_error = exc
            logging.warning(
                "llm_call label=%s model=%s attempt=%d/%d duration=%.2fs "
                "outcome=error error=%s",
                label, base_args["model"], attempt, attempts,
                time.monotonic() - started, type(exc).__name__,
            )
            continue

        _log_success(label, base_args["model"], attempt, attempts,
                     time.monotonic() - started)
        return result.choices[0].message.content

    if last_error is not None:
        raise last_error
    raise TimeoutError(
        f"llm_call label={label} exhausted its {Config.LLM_TIMEOUT}s budget "
        "before an attempt could start"
    )


class BaseAgent:  # pylint: disable=too-few-public-methods
    """Base class for agents."""

    def __init__(self, queries_history: list, result_history: list,
                 custom_api_key: str = None, custom_model: str = None):
        """Initialize the agent with query and result history."""
        if result_history is None:
            self.messages = []
        else:
            self.messages = []
            for query, result in zip(queries_history[:-1], result_history):
                self.messages.append({"role": "user", "content": query})
                self.messages.append({"role": "assistant", "content": result})

        self.custom_api_key = custom_api_key
        self.custom_model = custom_model


def parse_response(response: str) -> Dict[str, Any]:
    """
    Parse Claude's response to extract the analysis.
    Handles cases where LLM returns multiple JSON blocks by extracting the last valid one.

    Args:
        response: Claude's response string

    Returns:
        Parsed analysis results
    """
    try:
        # Try to find all JSON blocks (anything between { and })
        # and parse the last valid one (LLM sometimes corrects itself)
        # Find all potential JSON blocks
        json_blocks = []
        depth = 0
        start_idx = None

        for i, char in enumerate(response):
            if char == '{':
                if depth == 0:
                    start_idx = i
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0 and start_idx is not None:
                    json_blocks.append(response[start_idx:i+1])
                    start_idx = None

        # Try to parse JSON blocks from last to first (prefer the corrected version)
        for json_str in reversed(json_blocks):
            try:
                analysis = json.loads(json_str)
                # Validate it has required fields
                if "is_sql_translatable" in analysis and "sql_query" in analysis:
                    return analysis
            except json.JSONDecodeError:
                continue

        # Fallback to original method if block parsing fails
        json_start = response.find("{")
        json_end = response.rfind("}") + 1
        json_str = response[json_start:json_end]
        analysis = json.loads(json_str)
        return analysis
    except (json.JSONDecodeError, ValueError) as e:
        # Fallback if JSON parsing fails
        return {
            "is_sql_translatable": False,
            "confidence": 0,
            "explanation": f"Failed to parse response: {str(e)}",
            "error": str(response),
        }
