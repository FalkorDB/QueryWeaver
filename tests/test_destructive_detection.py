"""Unit tests for destructive-operation detection in ``api.core.pipeline``.

These tests focus on the confirmation/demo-graph safety gate: a statement that
mutates data or schema MUST be classified as destructive so it cannot execute
without user confirmation. They cover a previously exploitable bypass where a
first-token-only check missed data-modifying CTEs (``WITH ... DELETE ...``) and
stacked statements (``SELECT 1; DROP TABLE ...``), while making sure ordinary
read-only queries are not misclassified.
"""

import pytest

from api.core.pipeline import (
    DESTRUCTIVE_OPS,
    build_destructive_confirmation_message,
    detect_destructive_operation,
)


class TestPlainDestructiveOperations:
    """A statement that starts with a destructive verb is destructive."""

    @pytest.mark.parametrize("verb", sorted(DESTRUCTIVE_OPS))
    def test_leading_verb_is_destructive(self, verb):
        sql = f"{verb} something here"
        sql_type, is_destructive = detect_destructive_operation(sql)
        assert is_destructive is True
        assert sql_type == verb

    def test_leading_verb_is_case_insensitive(self):
        assert detect_destructive_operation("delete from users") == ("DELETE", True)
        assert detect_destructive_operation("InSeRt into t values (1)") == ("INSERT", True)

    def test_leading_whitespace_and_newlines(self):
        assert detect_destructive_operation("\n\t  DELETE FROM users") == ("DELETE", True)


class TestReadOnlyOperations:
    """Read-only statements must never be flagged as destructive."""

    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT * FROM users",
            "select id, name from users where id = 1",
            "WITH t AS (SELECT id FROM orders) SELECT * FROM t",
            "WITH RECURSIVE t AS (SELECT 1) SELECT * FROM t",
            "EXPLAIN SELECT * FROM users",
            "SELECT * FROM users WHERE status = 'active'",
        ],
    )
    def test_select_is_not_destructive(self, sql):
        sql_type, is_destructive = detect_destructive_operation(sql)
        assert is_destructive is False
        assert sql_type == sql.strip().split()[0].upper()


class TestDataModifyingCteBypass:
    """Regression tests for the CTE / stacked-statement confirmation bypass.

    A data-modifying CTE reads as ``WITH`` on its first token, so a
    first-token-only classifier treated it as read-only and executed the write
    without confirmation (and bypassed the demo-graph guard). These must all be
    detected as destructive.
    """

    def test_write_after_cte_is_destructive(self):
        # The write is at the top level, after the CTE definition.
        sql = (
            "WITH doomed AS (SELECT id FROM users WHERE inactive) "
            "DELETE FROM users WHERE id IN (SELECT id FROM doomed)"
        )
        assert detect_destructive_operation(sql) == ("DELETE", True)

    def test_write_inside_cte_body_is_destructive(self):
        # PostgreSQL data-modifying CTE: the write lives inside the CTE body.
        sql = (
            "WITH removed AS (DELETE FROM users WHERE id = 5 RETURNING id) "
            "SELECT * FROM removed"
        )
        assert detect_destructive_operation(sql) == ("DELETE", True)

    def test_insert_via_cte_is_destructive(self):
        sql = (
            "WITH src AS (SELECT 1 AS id) "
            "INSERT INTO audit (id) SELECT id FROM src"
        )
        assert detect_destructive_operation(sql) == ("INSERT", True)

    def test_update_via_cte_is_destructive(self):
        sql = (
            "WITH t AS (SELECT id FROM users) "
            "UPDATE users SET active = false WHERE id IN (SELECT id FROM t)"
        )
        assert detect_destructive_operation(sql) == ("UPDATE", True)

    def test_cte_bypass_is_case_insensitive(self):
        sql = "with t as (select 1) delete from users where id = 1"
        assert detect_destructive_operation(sql) == ("DELETE", True)

    def test_stacked_statement_is_destructive(self):
        sql = "SELECT 1; DROP TABLE users"
        assert detect_destructive_operation(sql) == ("DROP", True)

    def test_leading_comment_then_cte_write_is_destructive(self):
        sql = "/* harmless */ WITH t AS (SELECT 1) DELETE FROM users WHERE id = 1"
        assert detect_destructive_operation(sql) == ("DELETE", True)


class TestCommentBypass:
    """Comment prefixes/inlines must not smuggle or fake destructive verbs."""

    def test_line_comment_prefix_does_not_hide_delete(self):
        sql = "-- just a comment\nDELETE FROM users"
        assert detect_destructive_operation(sql) == ("DELETE", True)

    def test_block_comment_prefix_does_not_hide_drop(self):
        sql = "/* note */ DROP TABLE users"
        assert detect_destructive_operation(sql) == ("DROP", True)

    def test_destructive_word_only_in_line_comment_is_read_only(self):
        sql = "SELECT id FROM users -- DELETE everything\n"
        assert detect_destructive_operation(sql) == ("SELECT", False)

    def test_destructive_word_only_in_block_comment_is_read_only(self):
        sql = "SELECT id FROM users /* TODO: DROP later */ WHERE id = 1"
        assert detect_destructive_operation(sql) == ("SELECT", False)


class TestFalsePositiveGuards:
    """Destructive words inside strings/identifiers must not trigger detection."""

    def test_destructive_word_in_string_literal(self):
        sql = "SELECT * FROM audit WHERE action = 'DELETE'"
        assert detect_destructive_operation(sql) == ("SELECT", False)

    def test_multiple_dml_words_in_string_literal(self):
        sql = "SELECT * FROM audit WHERE action IN ('INSERT', 'UPDATE', 'DELETE')"
        assert detect_destructive_operation(sql) == ("SELECT", False)

    def test_escaped_quote_in_string_literal(self):
        sql = "SELECT * FROM t WHERE note = 'it''s fine to DROP nothing'"
        assert detect_destructive_operation(sql) == ("SELECT", False)

    def test_destructive_word_in_double_quoted_identifier(self):
        sql = 'SELECT "delete" FROM t'
        assert detect_destructive_operation(sql) == ("SELECT", False)

    def test_destructive_word_in_backtick_identifier(self):
        sql = "SELECT `delete` FROM t"
        assert detect_destructive_operation(sql) == ("SELECT", False)

    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT deleted_at FROM users",
            "SELECT update_count FROM stats",
            "SELECT insert_ts, is_deleted FROM events",
            "SELECT createdby FROM records",
        ],
    )
    def test_destructive_word_as_identifier_substring(self, sql):
        sql_type, is_destructive = detect_destructive_operation(sql)
        assert is_destructive is False
        assert sql_type == "SELECT"


class TestEdgeCases:
    """Empty / degenerate inputs."""

    @pytest.mark.parametrize("sql", ["", "   ", "\n\t", None])
    def test_empty_or_none_is_not_destructive(self, sql):
        assert detect_destructive_operation(sql) == ("", False)

    def test_only_comment_is_not_destructive(self):
        assert detect_destructive_operation("-- nothing here") == ("", False)


class TestConfirmationMessageIntegration:
    """The confirmation message names the real mutation, even for CTEs."""

    def test_cte_write_confirmation_names_delete(self):
        sql = "WITH t AS (SELECT 1) DELETE FROM users WHERE id = 1"
        sql_type, is_destructive = detect_destructive_operation(sql)
        assert is_destructive is True
        message = build_destructive_confirmation_message(sql_type, sql)
        assert "DELETE" in message
        assert "DESTRUCTIVE OPERATION DETECTED" in message
