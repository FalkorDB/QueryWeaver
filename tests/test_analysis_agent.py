"""Tests for selecting the corrected SQL from an analysis response."""

import json

import pytest

from api.agents import analysis_agent

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("literal", ["plain", "{", "}", 'quote " followed by {', "backslash \\"])
def test_analysis_uses_last_valid_sql(monkeypatch, literal):
    """Braces and escape sequences in a SQL literal are part of the JSON string."""
    corrected_sql = f"SELECT '{literal}'"
    first = {
        "is_sql_translatable": True,
        "sql_query": "SELECT 1",
        "ambiguities": [],
        "missing_information": [],
    }
    corrected = {**first, "sql_query": corrected_sql}
    response = "\n".join(map(json.dumps, (first, corrected)))
    monkeypatch.setattr(analysis_agent, "run_completion", lambda *args, **kwargs: response)

    agent = analysis_agent.AnalysisAgent([], None)
    analysis = agent.get_analysis("Return a literal", [], "")

    assert analysis["sql_query"] == corrected_sql
