"""Unit tests for dialect-aware row limiting in the analysis and healer prompts.

SQL Server has no ``LIMIT`` clause, so the analysis prompt must steer T-SQL
toward ``TOP`` / ``OFFSET ... FETCH`` while every other dialect keeps the
original ``LIMIT`` wording verbatim. No LLM calls are made: prompts are only
rendered.
"""

import pytest

from api.agents import analysis_agent
from api.agents.analysis_agent import AnalysisAgent
from api.agents.healer_agent import HealerAgent

pytestmark = pytest.mark.unit

# The exact LIMIT sentences the analysis prompt carried before SQL Server
# support. Non-SQL-Server prompts must keep them byte-for-byte.
ORIGINAL_LIMIT_SENTENCES = [
    "P4. Top/most/least intent: If the question asks for top/bottom N or "
    "most/least/highest/lowest, apply ORDER BY on the metric and LIMIT "
    "accordingly (LIMIT 1 for most/least) unless the user asks for ties.",
    "P7. NULL handling: Add IS NOT NULL only if required to prevent NULLs from "
    "dominating ORDER BY+LIMIT results or explicitly requested.",
    "If the question asks for the entity/row associated with the extreme, use "
    "ORDER BY ... LIMIT 1 and return only the requested entity/label columns.",
    "RANKING/LIMIT: <ORDER BY ... LIMIT ... | NONE>.",
    "7. Handle NULLs: Add IS NOT NULL only when explicitly requested or to "
    "prevent NULL domination in ORDER BY+LIMIT.",
]

NON_SQLSERVER_TYPES = ["postgresql", "mysql", "sqlite", "snowflake", None]


def _render(database_type):
    """Render the analysis prompt without touching the LLM."""
    agent = AnalysisAgent.__new__(AnalysisAgent)
    # pylint: disable=protected-access
    return agent._build_prompt(
        "Which customer spent the most?", "Table: customers - c\n", "desc",
        instructions=None, database_type=database_type,
    )


class TestAnalysisPromptRowLimiting:
    """The ranking guidance follows the target dialect."""

    @pytest.mark.parametrize("database_type", NON_SQLSERVER_TYPES)
    def test_non_sqlserver_prompt_keeps_original_limit_wording(self, database_type):
        """Non-SQL-Server dialects keep the original LIMIT sentences verbatim."""
        prompt = _render(database_type)
        for sentence in ORIGINAL_LIMIT_SENTENCES:
            assert sentence in prompt
        assert "T-SQL" not in prompt
        assert "FETCH NEXT" not in prompt
        assert "TOP n" not in prompt

    @pytest.mark.parametrize("database_type", ["sqlserver", "SQLSERVER"])
    def test_sqlserver_prompt_uses_top_and_offset_fetch(self, database_type):
        """SQL Server is told to use TOP / OFFSET-FETCH and that LIMIT is invalid."""
        prompt = _render(database_type)
        assert "SELECT TOP n ... ORDER BY ..." in prompt
        assert "TOP 1 for most/least" in prompt
        assert "TOP n WITH TIES" in prompt
        assert "OFFSET k ROWS FETCH NEXT n ROWS ONLY" in prompt
        assert "LIMIT is NOT valid T-SQL" in prompt
        assert "use SELECT TOP 1 ... ORDER BY ..." in prompt
        assert "ORDER BY+TOP" in prompt
        for sentence in ORIGINAL_LIMIT_SENTENCES:
            assert sentence not in prompt
        # LIMIT is only ever mentioned as forbidden (or as the template field
        # name RANKING/LIMIT), never as a clause to emit.
        assert "ORDER BY ... LIMIT" not in prompt
        assert "LIMIT 1" not in prompt
        assert "+LIMIT" not in prompt

    def test_sqlserver_prompt_differs_only_in_row_limit_phrases(self):
        """Swapping the T-SQL phrases back yields the PostgreSQL prompt exactly."""
        # pylint: disable=protected-access
        sqlserver_prompt = _render("sqlserver")
        defaults = analysis_agent._DEFAULT_ROW_LIMIT_PHRASES
        for key, tsql_phrase in analysis_agent._SQLSERVER_ROW_LIMIT_PHRASES.items():
            sqlserver_prompt = sqlserver_prompt.replace(tsql_phrase, defaults[key])
        sqlserver_prompt = sqlserver_prompt.replace(
            "TARGET DATABASE: SQLSERVER", "TARGET DATABASE: POSTGRESQL"
        )
        assert sqlserver_prompt == _render("postgresql")


class TestHealerSqlServer:
    """The healer gives T-SQL-specific guidance for SQL Server."""

    @pytest.mark.parametrize("error, expected", [
        ("('42000', \"[42000] [Microsoft][ODBC Driver 18 for SQL Server][SQL Server]"
         "Incorrect syntax near 'LIMIT'. (102)\")", "use SELECT TOP n"),
        ("Incorrect syntax near 'LIMIT'.", "OFFSET k ROWS FETCH NEXT n ROWS ONLY"),
        ("Invalid object name 'orders'.", "needs schema qualification"),
        ("Invalid object name 'orders'.", "[dbo].[Order Details]"),
        ("Invalid column name 'cust_name'.", "Column name doesn't exist"),
        ("Invalid column name 'Order Date'.", "[brackets]: [Column Name]"),
        ("Ambiguous column name 'id'.", "qualify it with the table alias"),
        ("An expression of non-boolean type specified in a context where a "
         "condition is expected, near 'ILIKE'.", "use LIKE"),
        ("'EXTRACT' is not a recognized built-in function name.", "DATEPART(year, col)"),
        ("The ORDER BY clause is invalid in views, inline functions, derived tables, "
         "subqueries, and common table expressions, unless TOP, OFFSET or FOR XML "
         "is also specified.", "requires TOP or OFFSET ... FETCH"),
        ("Incorrect syntax near '|'.", "concatenate with + or CONCAT()"),
    ])
    def test_analyze_error_sqlserver_hints(self, error, expected):
        """Common T-SQL failures map to targeted hints."""
        # pylint: disable=protected-access
        hints = HealerAgent()._analyze_error(error, "sqlserver")
        assert expected in hints
        assert "Check syntax compatibility" not in hints

    def test_analyze_error_sqlserver_unknown_error_falls_back(self):
        """Unrecognised T-SQL errors still get the generic hints."""
        # pylint: disable=protected-access
        hints = HealerAgent()._analyze_error("Arithmetic overflow error", "sqlserver")
        assert "Check syntax compatibility with SQLSERVER" in hints

    def test_analyze_error_sqlserver_hints_not_used_for_postgres(self):
        """T-SQL hints do not leak into other dialects."""
        # pylint: disable=protected-access
        hints = HealerAgent()._analyze_error("Incorrect syntax near 'LIMIT'.", "postgresql")
        assert "TOP" not in hints

    def test_healing_prompt_sqlserver_critical_rules(self):
        """The CRITICAL RULES section has a T-SQL branch."""
        # pylint: disable=protected-access
        prompt = HealerAgent()._build_healing_prompt(
            "SELECT name FROM customers ORDER BY spend DESC LIMIT 1",
            "Incorrect syntax near 'LIMIT'.", "", "Top customer?", "sqlserver",
        )
        assert "CRITICAL RULES FOR SQLSERVER:" in prompt
        assert "does NOT support LIMIT - use SELECT TOP n ... ORDER BY ..." in prompt
        assert "OFFSET 10 ROWS FETCH NEXT 5 ROWS ONLY" in prompt
        assert "[brackets]" in prompt
        assert "dbo.table" in prompt
        assert "No ILIKE - use LIKE" in prompt
        assert "DATEPART(year, col)" in prompt
        assert "+ or CONCAT()" in prompt
        assert "unless TOP or OFFSET ... FETCH is also used" in prompt
        assert "SQLite does NOT support" not in prompt

    @pytest.mark.parametrize("database_type", ["postgresql", "mysql", "sqlite"])
    def test_healing_prompt_other_dialects_have_no_tsql_rules(self, database_type):
        """Other dialects do not get the SQL Server rules."""
        # pylint: disable=protected-access
        prompt = HealerAgent()._build_healing_prompt(
            "SELECT 1", "boom", "", "", database_type,
        )
        assert "T-SQL" not in prompt
        assert "FETCH NEXT" not in prompt

    @pytest.mark.parametrize("sql", [
        "SELECT TOP 5 name FROM dbo.customers ORDER BY spend DESC",
        "SELECT TOP 1 WITH TIES [Customer Name] FROM [dbo].[Customers] ORDER BY spend DESC",
        "SELECT name FROM customers ORDER BY spend DESC OFFSET 10 ROWS FETCH NEXT 5 ROWS ONLY",
    ])
    def test_validate_sql_syntax_accepts_tsql_row_limiting(self, sql):
        """The pre-heal syntax check does not reject valid T-SQL row limiting."""
        result = HealerAgent.validate_sql_syntax(sql)
        assert result["is_valid"] is True
        assert not result["errors"]
        assert not result["warnings"]
