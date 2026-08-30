"""Utility functions for agents."""

import json
import logging
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List

from litellm import batch_completion, completion
from api.config import Config

# Backoff between retryable failures: base doubles per attempt, capped so a
# late retry cannot sleep away the whole budget. Module-level so tests can
# shrink it.
_RETRY_BACKOFF_SECONDS = 0.5
_RETRY_BACKOFF_CAP_SECONDS = 8.0


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


def _retryable(exc: Exception) -> bool:
    """Whether a failed attempt is worth spending remaining budget on.

    Transport-level failures (timeouts, dropped connections) carry no status
    code and are treated as transient. When the provider did answer, its
    verdict decides: 408/429/5xx describe the service's moment and can change
    on a replay; everything else (400, 401, 403, 404, ...) describes the
    request itself, so a retry would replay the same failure — a bad API key
    does not become valid by asking twice.
    """
    status_code = getattr(exc, "status_code", None)
    if status_code is None:
        return True
    return status_code in (408, 429) or status_code >= 500


def _retry_after_header(exc: Exception):
    """The raw ``Retry-After`` value from wherever the client stashed it."""
    for source in ("litellm_response_headers", "response_headers"):
        headers = getattr(exc, source, None)
        if headers is not None:
            break
    else:
        headers = getattr(getattr(exc, "response", None), "headers", None)
    if headers is None:
        return None
    try:
        return headers.get("retry-after")
    except (AttributeError, TypeError):
        return None


def _http_date_delay(value) -> float | None:
    """Seconds until an HTTP-date ``Retry-After``, the spec's other form."""
    try:
        when = parsedate_to_datetime(str(value))
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())


def _retry_after_seconds(exc: Exception) -> float | None:
    """The provider's ``Retry-After``, if the failure carried one.

    litellm keeps the provider's original headers on the exception as
    ``litellm_response_headers``; ``exc.response.headers`` is litellm's own
    reconstructed response and does not carry them, so reading that returned
    ``None`` for every real 429 and the backoff fell back to its own guess.

    Both header spellings are accepted: a delay in seconds, or an HTTP date.
    """
    value = _retry_after_header(exc)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return _http_date_delay(value)


def _retry_delay(exc: Exception, attempt: int) -> float:
    """Seconds to wait before the next attempt.

    The provider's own ``Retry-After`` wins when present — a 429 states exactly
    when trying again stops being rude — and is honoured in full rather than
    truncated: the caller already refuses a delay that outlives the budget, so
    capping it here only produced a retry that was certain to be rejected
    again. The exponential fallback stays capped, since it is a guess.
    """
    retry_after = _retry_after_seconds(exc)
    if retry_after is not None and retry_after >= 0:
        return retry_after
    return min(_RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1)),
               _RETRY_BACKOFF_CAP_SECONDS)


def _pause_before_retry(delay: float, deadline: float) -> bool:
    """Sleep *delay* before the next attempt.

    Returns ``False`` when sleeping would outlive the budget, in which case
    there is no point in another attempt at all.
    """
    if delay >= deadline - time.monotonic():
        return False
    time.sleep(delay)
    return True


def _log_failure(label: str, model: str, attempt: str, *,
                 elapsed: float, exc: Exception) -> None:
    """Record a failed attempt and whether it is worth replaying."""
    logging.warning(
        "llm_call label=%s model=%s attempt=%s duration=%.2fs "
        "outcome=error error=%s retryable=%s",
        label, model, attempt, elapsed,
        type(exc).__name__, _retryable(exc),
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
            _log_failure(label, base_args["model"], f"{attempt}/{attempts}",
                         elapsed=time.monotonic() - started, exc=exc)
            if not _retryable(exc):
                # The provider judged the request itself invalid; a replay
                # would fail identically, so surface it now.
                raise
            if attempt < attempts and not _pause_before_retry(
                    _retry_delay(exc, attempt), deadline):
                break  # sleeping would outlive the budget
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


def _fail_unanswered_slots(results: List[Any], label: str) -> None:
    """Turn every still-``None`` slot into an explicit failure.

    A slot can hold ``None`` when the library answered short or the budget ran
    out before the slot was ever attempted. Callers branch on
    ``isinstance(..., Exception)`` and treat everything else as a response, so
    ``None`` must leave as a failure, not a response.
    """
    for i, item in enumerate(results):
        if item is None:
            results[i] = TimeoutError(
                f"llm_call label={label} slot {i} got no answer within the "
                f"{Config.LLM_TIMEOUT}s budget"
            )


def run_batch_completion(messages_list: List[List[Dict[str, str]]], *,
                         label: str = "llm-batch", **base_args) -> List[Any]:
    """Batch counterpart of ``run_completion``: same budget, same verdicts.

    litellm's ``batch_completion`` reports a failed item by returning the
    exception in that item's slot, and its own retry knobs conflict (it treats
    ``num_retries`` as overriding ``max_retries``), so callers passing the pair
    got no retry at all. This drives the whole batch against one ``LLM_TIMEOUT``
    budget instead and retries only the items whose failure was transient
    (:func:`_retryable`), with whatever budget remains.

    Returns a list aligned with *messages_list*; an item that never succeeded
    holds its final exception, which is the contract callers already handle.
    """
    results: List[Any] = [None] * len(messages_list)
    pending = list(range(len(messages_list)))
    attempts = Config.llm_attempts()
    deadline = time.monotonic() + Config.LLM_TIMEOUT

    for attempt in range(1, attempts + 1):
        remaining = deadline - time.monotonic()
        if not pending or remaining <= 0:
            break

        started = time.monotonic()
        batch = batch_completion(**{
            **base_args,
            "messages": [messages_list[i] for i in pending],
            **Config.llm_call_bounds(timeout=remaining),
        })

        retry_slots = []
        for slot, response in zip(pending, batch):
            results[slot] = response
            if isinstance(response, Exception) and _retryable(response):
                retry_slots.append(slot)

        failed = sum(1 for i in pending if isinstance(results[i], Exception))
        logging.info(
            "llm_call label=%s model=%s attempt=%d/%d duration=%.2fs "
            "outcome=%d/%d ok (%d retryable)",
            label, base_args.get("model"), attempt, attempts,
            time.monotonic() - started, len(pending) - failed, len(pending),
            len(retry_slots),
        )

        pending = retry_slots
        if pending and attempt < attempts and not _pause_before_retry(
                max(_retry_delay(results[i], attempt) for i in pending),
                deadline):
            break  # sleeping would outlive the budget

    _fail_unanswered_slots(results, label)
    return results


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
