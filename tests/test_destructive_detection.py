"""Unit tests for destructive-operation detection in ``api.core.pipeline``.

Detection is AST-based (sqlglot, dialect-aware). These tests focus on the
confirmation / demo-graph safety gate: any statement that mutates data or
schema — even when hidden in a CTE, a stacked statement, an executable comment,
or behind dialect-specific escapes — must be classified destructive, while
ordinary reads must not be. They also cover a previously exploitable bypass
where a first-token-only check missed data-modifying CTEs and stacked writes.
"""

import pytest

from api.core.pipeline import (
    DESTRUCTIVE_OPS,
    build_destructive_confirmation_message,
    detect_destructive_operation,
)

pytestmark = pytest.mark.unit


class TestPlainStatements:
    """A statement whose operation is a write/DDL is destructive."""

    @pytest.mark.parametrize(
        "sql,verb",
        [
            ("INSERT INTO users (id) VALUES (1)", "INSERT"),
            ("UPDATE users SET active = FALSE WHERE id = 1", "UPDATE"),
            ("DELETE FROM users WHERE id = 1", "DELETE"),
            ("DROP TABLE users", "DROP"),
            ("CREATE TABLE t (id INT)", "CREATE"),
            ("ALTER TABLE users ADD COLUMN c INT", "ALTER"),
            ("TRUNCATE TABLE users", "TRUNCATE"),
        ],
    )
    def test_plain_write_is_destructive(self, sql, verb):
        assert detect_destructive_operation(sql) == (verb, True)

    def test_case_insensitive(self):
        assert detect_destructive_operation("delete from users where id = 1") == ("DELETE", True)

    def test_whitespace_prefixed(self):
        assert detect_destructive_operation("\n\t  DELETE FROM users") == ("DELETE", True)


class TestReadOnly:
    """Read-only statements must never be flagged as destructive."""

    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT * FROM users",
            "select id, name from users where id = 1",
            "WITH t AS (SELECT id FROM orders) SELECT * FROM t",
            "WITH RECURSIVE t AS (SELECT 1) SELECT * FROM t",
            "SELECT * FROM users WHERE status = 'active'",
            "SELECT COUNT(*) FROM users",
        ],
    )
    def test_reads_are_not_destructive(self, sql):
        assert detect_destructive_operation(sql)[1] is False


class TestDataModifyingCteBypass:
    """Regression tests for the CTE / stacked-statement confirmation bypass.

    A data-modifying CTE reads as ``WITH`` on its first token, so a
    first-token-only classifier treated it as read-only and executed the write
    without confirmation (and bypassed the demo-graph guard).
    """

    def test_write_after_cte(self):
        sql = (
            "WITH doomed AS (SELECT id FROM users) "
            "DELETE FROM users WHERE id IN (SELECT id FROM doomed)"
        )
        assert detect_destructive_operation(sql) == ("DELETE", True)

    def test_write_inside_cte_body(self):
        sql = (
            "WITH removed AS (DELETE FROM users WHERE id = 5 RETURNING id) "
            "SELECT * FROM removed"
        )
        assert detect_destructive_operation(sql, "postgresql") == ("DELETE", True)

    def test_insert_via_cte(self):
        sql = "WITH src AS (SELECT 1 AS id) INSERT INTO audit (id) SELECT id FROM src"
        assert detect_destructive_operation(sql) == ("INSERT", True)

    def test_update_via_cte(self):
        sql = (
            "WITH t AS (SELECT id FROM users) "
            "UPDATE users SET active = FALSE WHERE id IN (SELECT id FROM t)"
        )
        assert detect_destructive_operation(sql) == ("UPDATE", True)

    def test_case_insensitive_cte(self):
        sql = "with t as (select 1) delete from users where id = 1"
        assert detect_destructive_operation(sql) == ("DELETE", True)

    def test_stacked_statement(self):
        assert detect_destructive_operation("SELECT 1; DROP TABLE users") == ("DROP", True)


class TestExtraMutators:
    """Writes/DDL/privilege/bulk ops beyond the basic verbs, caught via AST."""

    def test_merge(self):
        sql = "MERGE INTO t USING s ON t.id = s.id WHEN MATCHED THEN UPDATE SET t.v = s.v"
        assert detect_destructive_operation(sql) == ("MERGE", True)

    def test_replace_into(self):
        assert detect_destructive_operation("REPLACE INTO users VALUES (1, 'a')", "mysql") == (
            "REPLACE",
            True,
        )

    def test_replace_into_stacked(self):
        assert detect_destructive_operation("SELECT 1; REPLACE INTO t VALUES (1)", "mysql")[1] is True

    def test_select_into(self):
        assert detect_destructive_operation("SELECT * INTO archived FROM users")[1] is True

    def test_grant(self):
        assert detect_destructive_operation("GRANT ALL ON users TO app")[1] is True

    def test_revoke(self):
        assert detect_destructive_operation("REVOKE SELECT ON users FROM app")[1] is True

    def test_call_procedure(self):
        assert detect_destructive_operation("CALL purge_users()")[1] is True

    def test_rename_table(self):
        assert detect_destructive_operation("RENAME TABLE users TO users_old", "mysql")[1] is True

    def test_copy(self):
        assert detect_destructive_operation("COPY users FROM '/data/u.csv'", "postgresql")[1] is True

    def test_load_data(self):
        sql = "LOAD DATA INFILE '/data/u.csv' INTO TABLE users"
        assert detect_destructive_operation(sql, "mysql")[1] is True


class TestDialectEscapeBypasses:
    """Escapes/quotes/comments that a naive scanner mis-tokenises. sqlglot
    parses them dialect-aware, so the hidden write is still detected."""

    def test_postgres_dollar_quote_hiding_quote(self):
        sql = "WITH cte AS (SELECT $$'$$ AS s) DELETE FROM users WHERE id = 1"
        assert detect_destructive_operation(sql, "postgresql") == ("DELETE", True)

    def test_mysql_backslash_escape(self):
        sql = r"WITH cte AS (SELECT '\'' AS s) DELETE FROM users WHERE id = 1"
        assert detect_destructive_operation(sql, "mysql") == ("DELETE", True)

    def test_mysql_hash_comment(self):
        sql = "WITH cte AS (SELECT 1 # x\n) DELETE FROM users WHERE id = 1"
        assert detect_destructive_operation(sql, "mysql") == ("DELETE", True)


class TestExecutableComments:
    """MySQL/MariaDB executable comments run on the server, so a destructive
    payload inside one must be detected — not dropped like a normal comment."""

    def test_executable_comment_drop(self):
        assert detect_destructive_operation("/*! DROP TABLE users */", "mysql") == ("DROP", True)

    def test_version_gated_executable_comment(self):
        assert detect_destructive_operation("/*!50110 DROP TABLE users */", "mysql") == ("DROP", True)

    def test_mariadb_executable_comment(self):
        assert detect_destructive_operation("/*M! DELETE FROM users */", "mysql") == ("DELETE", True)

    def test_executable_comment_fragment_inside_read(self):
        sql = "SELECT * FROM t WHERE 1 /*! ; DELETE FROM t */"
        assert detect_destructive_operation(sql, "mysql")[1] is True

    def test_benign_executable_comment_is_read_only(self):
        sql = "/*!40101 SET NAMES utf8 */; SELECT * FROM users"
        assert detect_destructive_operation(sql, "mysql")[1] is False

    def test_ordinary_block_comment_is_ignored(self):
        assert detect_destructive_operation("SELECT 1 /* DROP TABLE users */")[1] is False


class TestFalsePositiveGuards:
    """Destructive words inside strings/identifiers/functions stay read-only."""

    @pytest.mark.parametrize(
        "sql,dialect",
        [
            ("SELECT * FROM audit WHERE action = 'DELETE'", None),
            ("SELECT * FROM audit WHERE action IN ('INSERT', 'UPDATE', 'DELETE')", None),
            ("SELECT * FROM t WHERE note = 'it''s fine to DROP nothing'", None),
            ('SELECT "delete" FROM t', None),
            ("SELECT `delete` FROM t", "mysql"),
            ("SELECT deleted_at, update_count, is_deleted FROM events", None),
            ("SELECT REPLACE(name, 'a', 'b') FROM users", None),
            ("SELECT INSERT(name, 1, 2, 'x') FROM users", "mysql"),
            ("SELECT TRUNCATE(price, 2) FROM products", "mysql"),
        ],
    )
    def test_read_only_not_flagged(self, sql, dialect):
        assert detect_destructive_operation(sql, dialect)[1] is False


class TestConservativeFallback:
    """Unparseable / opaque statements are treated as destructive."""

    def test_unparseable_is_destructive(self):
        assert detect_destructive_operation("!!! not valid sql @@@")[1] is True

    def test_explain_analyze_write_is_destructive(self):
        # EXPLAIN parses to an opaque Command whose payload is not introspectable,
        # and EXPLAIN ANALYZE <write> executes, so treat it as destructive.
        assert detect_destructive_operation("EXPLAIN ANALYZE DELETE FROM users", "postgresql")[1] is True


class TestEdgeCases:
    """Empty / degenerate inputs."""

    @pytest.mark.parametrize("sql", ["", "   ", "\n\t", None])
    def test_empty_or_none(self, sql):
        assert detect_destructive_operation(sql) == ("", False)

    def test_comment_only_is_not_destructive(self):
        assert detect_destructive_operation("-- nothing here")[1] is False


class TestDestructiveOpsConstant:
    def test_core_verbs_present(self):
        for verb in ("INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE", "REPLACE"):
            assert verb in DESTRUCTIVE_OPS


class TestConfirmationMessageIntegration:
    """The confirmation message names the real mutation, even for CTEs."""

    def test_cte_write_confirmation_names_delete(self):
        sql = "WITH t AS (SELECT 1) DELETE FROM users WHERE id = 1"
        sql_type, is_destructive = detect_destructive_operation(sql)
        assert is_destructive is True
        message = build_destructive_confirmation_message(sql_type, sql)
        assert "DELETE" in message
        assert "DESTRUCTIVE OPERATION DETECTED" in message
