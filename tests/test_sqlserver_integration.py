"""Introspection run against a real SQL Server.

The unit tests drive a fake cursor, so they pin what the loader *does* with a
result set but never send a statement to a server. Every blocker found in review
lived in the part they cannot reach: ``SELECT DISTINCT ... ORDER BY NEWID()`` is
rejected by the parser, ``uniqueidentifier`` only becomes a ``uuid.UUID`` once a
driver decodes one, and an identifier the allow-list refused only fails when a
real catalog hands it back.

So this file builds a deliberately awkward schema -- non-ASCII names, a bracket
and a dot in a table name, types SQL Server will not compare, a GUID column, a
composite key and a cross-schema reference -- and asserts on what
``_introspect_schema`` returns. It is one pass over one fixture, not a second
copy of the unit tests: what is being checked is that the SQL is valid and that
the awkward cases degrade the way they are supposed to.

Set ``SQLSERVER_TEST_URL`` to run it, e.g. against

    docker run -e ACCEPT_EULA=Y -e MSSQL_SA_PASSWORD=Str0ng!Passw0rd \
        -p 1433:1433 -d mcr.microsoft.com/mssql/server:2022-latest

    SQLSERVER_TEST_URL='sqlserver://sa:Str0ng!Passw0rd@localhost:1433/master'

Without it, the module skips.
"""
# pylint: disable=protected-access

import json
import os
import uuid
import importlib

import pytest

pymssql = pytest.importorskip("pymssql")

# See ``tests/test_sqlserver_loader.py``: ``api.core.__init__`` eagerly pulls in
# the pipeline, which imports the loaders, so importing a loader first leaves
# ``graph_loader`` half-built.
importlib.import_module("api.core")

from api.loaders.sqlserver_loader import SQLServerLoader  # noqa: E402  pylint: disable=wrong-import-position

pytestmark = [pytest.mark.integration]

# Names the old ASCII allow-list rejected outright, plus the two punctuation
# cases that have to survive quoting rather than validation.
GERMAN = "Kunden_Ä"
HEBREW = "לקוחות"
CJK = "顧客"
BRACKETED = "my]table"
DOTTED = "weird.name"


def _q(identifier: str) -> str:
    """Bracket-quote for the fixture DDL, the same way the loader does."""
    return f"[{identifier.replace(']', ']]')}]"


@pytest.fixture(name="schema", scope="module")
def _schema():
    """A throwaway schema, dropped afterwards so a rerun starts clean."""
    url = os.getenv("SQLSERVER_TEST_URL")
    if not url:
        pytest.skip("SQLSERVER_TEST_URL is not set")

    params = SQLServerLoader._parse_sqlserver_url(url)
    try:
        conn = pymssql.connect(**params)
    except pymssql.Error as exc:
        pytest.skip(f"SQL Server unreachable: {exc}")

    name = f"qw_{uuid.uuid4().hex[:12]}"
    other = f"{name}_ext"
    try:
        with conn.cursor() as cur:
            _build_fixture(cur, name, other)
        conn.commit()
        yield name
    finally:
        with conn.cursor() as cur:
            for target in (name, other):
                _drop_schema(cur, target)
        conn.commit()
        conn.close()


def _build_fixture(cur, schema: str, other: str) -> None:
    """Create the awkward schema the assertions below rely on."""
    cur.execute(f"CREATE SCHEMA {_q(schema)}")
    cur.execute(f"CREATE SCHEMA {_q(other)}")

    # Parent with a non-ASCII name, a non-ASCII column and a GUID.
    cur.execute(f"""
        CREATE TABLE {_q(schema)}.{_q(GERMAN)} (
            id INT NOT NULL PRIMARY KEY,
            {_q("Straße")} NVARCHAR(50) NULL,
            guid UNIQUEIDENTIFIER NULL
        )
    """)
    cur.execute(f"""
        INSERT INTO {_q(schema)}.{_q(GERMAN)} (id, {_q("Straße")}, guid)
        VALUES (1, N'Hauptstraße', '3F2504E0-4F89-11D3-9A0C-0305E82C3301')
    """)

    # Child, also non-ASCII, referencing the parent.
    cur.execute(f"""
        CREATE TABLE {_q(schema)}.{_q(HEBREW)} (
            id INT NOT NULL PRIMARY KEY,
            kunde_id INT NOT NULL
                CONSTRAINT fk_hebrew_kunde REFERENCES {_q(schema)}.{_q(GERMAN)} (id)
        )
    """)

    # Types SQL Server refuses to compare, alongside one that samples normally.
    cur.execute(f"""
        CREATE TABLE {_q(schema)}.{_q(CJK)} (
            id INT NOT NULL PRIMARY KEY,
            label NVARCHAR(50) NULL,
            payload XML NULL,
            notes TEXT NULL,
            spot GEOGRAPHY NULL
        )
    """)
    cur.execute(f"""
        INSERT INTO {_q(schema)}.{_q(CJK)} (id, label, payload, notes, spot)
        VALUES (1, N'顧客A', '<a/>', 'note',
                geography::Point(47.6, -122.3, 4326))
    """)

    # Punctuation that has to survive quoting rather than validation.
    cur.execute(f"CREATE TABLE {_q(schema)}.{_q(BRACKETED)} (id INT NOT NULL PRIMARY KEY)")
    cur.execute(f"INSERT INTO {_q(schema)}.{_q(BRACKETED)} (id) VALUES (1)")
    cur.execute(f"CREATE TABLE {_q(schema)}.{_q(DOTTED)} (id INT NOT NULL PRIMARY KEY)")
    cur.execute(f"INSERT INTO {_q(schema)}.{_q(DOTTED)} (id) VALUES (1)")

    # Composite key: one constraint, two columns.
    cur.execute(f"""
        CREATE TABLE {_q(schema)}.[Region] (
            country CHAR(2) NOT NULL,
            code INT NOT NULL,
            CONSTRAINT pk_region PRIMARY KEY (country, code)
        )
    """)
    cur.execute(f"""
        CREATE TABLE {_q(schema)}.[Store] (
            id INT NOT NULL PRIMARY KEY,
            country CHAR(2) NOT NULL,
            code INT NOT NULL,
            CONSTRAINT fk_store_region FOREIGN KEY (country, code)
                REFERENCES {_q(schema)}.[Region] (country, code)
        )
    """)

    # Cross-schema reference: in range on the parent side, out of range on the
    # referenced side, so the loader has to drop it rather than emit a
    # relationship pointing at a table it never loaded.
    cur.execute(f"CREATE TABLE {_q(other)}.[Outside] (id INT NOT NULL PRIMARY KEY)")
    cur.execute(f"""
        CREATE TABLE {_q(schema)}.[CrossRef] (
            id INT NOT NULL PRIMARY KEY,
            outside_id INT NOT NULL
                CONSTRAINT fk_crossref_outside REFERENCES {_q(other)}.[Outside] (id)
        )
    """)


def _drop_schema(cur, schema: str) -> None:
    """Drop every table in *schema*, then the schema itself."""
    cur.execute("""
        SELECT t.name FROM sys.tables t
        JOIN sys.schemas s ON t.schema_id = s.schema_id
        WHERE s.name = %s
    """, (schema,))
    tables = [row[0] for row in cur.fetchall()]
    # Foreign keys first; a table cannot be dropped while one points at it.
    for table in tables:
        cur.execute("""
            SELECT fk.name
            FROM sys.foreign_keys fk
            JOIN sys.tables t ON fk.parent_object_id = t.object_id
            JOIN sys.schemas s ON t.schema_id = s.schema_id
            WHERE s.name = %s AND t.name = %s
        """, (schema, table))
        for (constraint,) in cur.fetchall():
            cur.execute(
                f"ALTER TABLE {_q(schema)}.{_q(table)} DROP CONSTRAINT {_q(constraint)}"
            )
    for table in tables:
        cur.execute(f"DROP TABLE {_q(schema)}.{_q(table)}")
    cur.execute(f"DROP SCHEMA {_q(schema)}")


@pytest.fixture(name="introspection", scope="module")
def _introspection(schema):
    """One introspection pass, shared by every assertion below."""
    params = SQLServerLoader._parse_sqlserver_url(os.getenv("SQLSERVER_TEST_URL"))
    return SQLServerLoader._introspect_schema(params, schema)


class TestIntrospectionAgainstRealServer:
    """What the loader gets back from a server that actually parses the SQL."""

    def test_every_table_loads(self, introspection):
        """No statement in the walk is rejected, whatever the names look like.

        Regression test for error 145: the sample query paired ``DISTINCT`` with
        ``ORDER BY NEWID()``, which SQL Server refuses, so the first column of
        the first table took the whole load down.
        """
        entities, _relationships = introspection
        assert set(entities) == {
            GERMAN, HEBREW, CJK, BRACKETED, DOTTED, "Region", "Store", "CrossRef",
        }

    def test_non_comparable_types_cost_only_their_own_column(self, introspection):
        """``xml``, ``text`` and ``geography`` cannot be DISTINCT-ed."""
        entities, _relationships = introspection
        columns = entities[CJK]['columns']
        for col in ("payload", "notes", "spot"):
            assert columns[col]['sample_values'] == []
        assert columns['label']['sample_values'] == ["顧客A"]

    def test_a_dotted_table_name_loads_without_samples(self, introspection):
        """A dot makes the qualified name ambiguous, so sampling is skipped."""
        entities, _relationships = introspection
        assert entities[DOTTED]['columns']['id']['sample_values'] == []

    def test_a_bracketed_table_name_still_samples(self, introspection):
        """``]`` is doubled by the quoter, so it needs no special handling."""
        entities, _relationships = introspection
        assert entities[BRACKETED]['columns']['id']['sample_values'] == ["1"]

    def test_non_ascii_names_and_values_round_trip(self, introspection):
        """The old allow-list rejected all three of these."""
        entities, _relationships = introspection
        assert entities[GERMAN]['columns']["Straße"]['sample_values'] == ["Hauptstraße"]

    def test_guids_arrive_as_json_encodable_strings(self, introspection):
        """pymssql decodes ``uniqueidentifier`` to ``uuid.UUID``."""
        entities, _relationships = introspection
        samples = entities[GERMAN]['columns']['guid']['sample_values']
        assert samples == ["3f2504e0-4f89-11d3-9a0c-0305e82c3301"]
        json.dumps(entities[GERMAN]['columns']['guid'])

    def test_a_composite_key_is_one_relationship_with_two_columns(self, introspection):
        """Both column pairs land under the single constraint name."""
        _entities, relationships = introspection
        assert sorted(
            (edge['source_column'], edge['target_column'])
            for edge in relationships['fk_store_region']
        ) == [("code", "code"), ("country", "country")]

    def test_a_cross_schema_key_is_left_out_of_both_structures(self, introspection):
        """Otherwise the graph gains an edge to a table that was never loaded."""
        entities, relationships = introspection
        assert "fk_crossref_outside" not in relationships
        assert entities["CrossRef"]['foreign_keys'] == []

    def test_key_kinds_come_back_in_the_loader_vocabulary(self, introspection):
        """The CASE emits these directly; nothing translates MySQL codes."""
        entities, _relationships = introspection
        assert entities[GERMAN]['columns']['id']['key'] == "PRIMARY KEY"
        assert entities[HEBREW]['columns']['kunde_id']['key'] == "FOREIGN KEY"
        assert entities[CJK]['columns']['label']['key'] == "NONE"
