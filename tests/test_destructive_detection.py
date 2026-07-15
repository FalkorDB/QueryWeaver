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

pytestmark = pytest.mark.unit


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


class TestReplaceStatement:
    """MySQL ``REPLACE`` is a write (delete-then-insert) and must be caught,
    but the same-named ``REPLACE()`` string function must not false-trigger."""

    def test_replace_is_in_destructive_ops(self):
        assert "REPLACE" in DESTRUCTIVE_OPS

    def test_replace_into_is_destructive(self):
        assert detect_destructive_operation("REPLACE INTO users VALUES (1, 'a')") == (
            "REPLACE",
            True,
        )

    def test_replace_into_via_cte_is_destructive(self):
        sql = "WITH t AS (SELECT 1 AS id) REPLACE INTO users SELECT id FROM t"
        assert detect_destructive_operation(sql) == ("REPLACE", True)

    def test_replace_into_stacked_is_destructive(self):
        assert detect_destructive_operation("SELECT 1; REPLACE INTO t VALUES (1)") == (
            "REPLACE",
            True,
        )

    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT REPLACE(name, 'a', 'b') FROM users",
            "SELECT REPLACE (name, 'a', 'b') FROM users",  # space before paren
            "SELECT id, INSERT(name, 1, 2, 'x') FROM users",  # MySQL INSERT() fn
            "SELECT TRUNCATE(price, 2) FROM products",  # numeric TRUNCATE() fn
        ],
    )
    def test_destructive_word_as_function_call_is_read_only(self, sql):
        sql_type, is_destructive = detect_destructive_operation(sql)
        assert is_destructive is False
        assert sql_type == "SELECT"


class TestExecutableComments:
    """MySQL/MariaDB executable comments run on the server, so a destructive
    verb inside one must be detected — not skipped like an ordinary comment."""

    def test_executable_comment_drop_is_destructive(self):
        assert detect_destructive_operation("/*! DROP TABLE users */") == ("DROP", True)

    def test_executable_comment_leading_then_select(self):
        # Executable comment with a destructive payload before a read.
        sql = "/*! DELETE FROM users */ SELECT 1"
        assert detect_destructive_operation(sql) == ("DELETE", True)

    def test_version_gated_executable_comment_is_destructive(self):
        assert detect_destructive_operation("/*!50110 DROP TABLE users */") == (
            "DROP",
            True,
        )

    def test_mariadb_executable_comment_is_destructive(self):
        assert detect_destructive_operation("/*M! DELETE FROM users */") == (
            "DELETE",
            True,
        )

    def test_executable_comment_inside_statement_is_destructive(self):
        sql = "SELECT 1 /*! ; DROP TABLE users */"
        assert detect_destructive_operation(sql) == ("DROP", True)

    def test_benign_executable_comment_is_read_only(self):
        # SET is not destructive; the surrounding query is a read. (sql_type is
        # unused for non-destructive results, so only is_destructive matters.)
        sql = "/*!40101 SET NAMES utf8 */ SELECT * FROM users"
        assert detect_destructive_operation(sql)[1] is False

    def test_ordinary_block_comment_payload_stays_read_only(self):
        # A non-executable /* ... */ comment must still be ignored.
        assert detect_destructive_operation("SELECT 1 /* DROP TABLE users */") == (
            "SELECT",
            False,
        )
