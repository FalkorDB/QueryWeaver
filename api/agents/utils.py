"""Utility functions for agents."""

import json
from typing import Any, Dict


class BaseAgent:
    """Base class for agents."""

    def __init__(self, queries_history: list, result_history: list):
        """Initialize the agent with query and result history."""
        if result_history is None:
            self.messages = []
        else:
            self.messages = []
            for query, result in zip(queries_history[:-1], result_history):
                self.messages.append({"role": "user", "content": query})
                self.messages.append({"role": "assistant", "content": result})


def parse_response(response: str) -> Dict[str, Any]:
    """
    Parse Claude's response to extract the analysis.

    Args:
        response: Claude's response string

    Returns:
        Parsed analysis results
    """
    try:
        # Extract JSON from the response
        json_start = response.find("{")
        json_end = response.rfind("}") + 1
        json_str = response[json_start:json_end]

        # Parse the JSON
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
