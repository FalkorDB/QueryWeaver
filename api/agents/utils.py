"""Utility functions for agents."""

import json
from typing import Any, Dict, List

from litellm import completion
from api.config import Config


def run_completion(messages: List[Dict[str, str]], custom_model: str = None,
                   custom_api_key: str = None, **kwargs) -> str:
    """Run an LLM completion with optional custom model/key overrides.

    Returns the content string from the first choice.
    """
    completion_args = {
        "model": custom_model if custom_model else Config.COMPLETION_MODEL,
        "messages": messages,
        "top_p": 1,
        **kwargs,
    }

    if custom_api_key:
        completion_args["api_key"] = custom_api_key

    result = completion(**completion_args)
    return result.choices[0].message.content


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
