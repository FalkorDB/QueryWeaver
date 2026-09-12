"""SQL Server loader for loading database schemas into FalkorDB graphs."""

import datetime
import decimal
import logging
import re
import uuid
from typing import AsyncGenerator, Dict, Any, List, Tuple
from urllib.parse import urlparse, parse_qs, unquote

import tqdm
import pymssql

from api.config import Config
from api.loaders.base_loader import BaseLoader
from api.loaders.graph_loader import load_to_graph
from api.loaders.introspection import run_introspection

DEFAULT_SCHEMA = "dbo"
DEFAULT_PORT = 1433

_CONTROL_CHARS = re.compile(r'[\x00-\x1f\x7f]')


class SQLServerQueryError(Exception):
    """Exception raised for SQL Server query execution errors."""


class SQLServerConnectionError(Exception):
    """Exception raised for SQL Server connection errors."""


def validate_ident(
    identifier: str, identifier_type: str = "identifier", allow_dot: bool = True
) -> str:
    """Validate that a *user-supplied* identifier is safe to interpolate into T-SQL.

    T-SQL cannot bind identifiers as parameters, so the schema taken from the
    connection URL must be interpolated. This is an anchored allow-list: only
    characters that can legitimately appear in a SQL Server object name are
    accepted, and everything capable of breaking out of a bracket-delimited
    identifier (``]``, quotes, semicolons, backslashes, control characters) is
    rejected. Names read back from the system catalog go through
    :func:`validate_catalog_ident` instead, which is deliberately laxer.

    Args:
        identifier: Raw identifier supplied by the user.
        identifier_type: Label used in the error message.
        allow_dot: Whether ``.`` is accepted. A dot is legal inside a
            bracket-quoted SQL Server name, but callers that recover a schema
            and a table from one dotted string cannot tell the two apart, so
            they pass ``False`` and get a clear error instead of a query
            against the wrong object.

    Returns:
        The identifier, unchanged, once validated.

    Raises:
        ValueError: If the identifier is empty, over-long, or contains a
            character outside the allow-list.
    """
    if not identifier or len(identifier) > 128:
        raise ValueError(
            f"Invalid {identifier_type}: {identifier!r}. "
            "Must be between 1 and 128 characters."
        )
    allowed = r'[A-Za-z0-9_$#@ .\-]+' if allow_dot else r'[A-Za-z0-9_$#@ \-]+'
    if not re.fullmatch(allowed, identifier):
        dot = "dot, " if allow_dot else ""
        raise ValueError(
            f"Invalid {identifier_type}: {identifier!r}. Only letters, digits, "
            f"underscore, dollar, hash, at-sign, space, {dot}and dash are allowed."
        )
    return identifier


def validate_catalog_ident(
    identifier: str, identifier_type: str = "identifier", allow_dot: bool = True
) -> str:
    """Validate an identifier that the server itself returned from the catalog.

    SQL Server allows almost anything inside a delimited identifier, and Hebrew,
    German and CJK table names are ordinary in the databases this loader reads.
    Holding catalog names to the ASCII allow-list above would fail the whole
    schema load over one such name, so this only rejects what bracket-quoting
    cannot survive: control characters, and — when *allow_dot* is False — a dot
    that would make a schema-qualified name ambiguous.

    Raises:
        ValueError: If the identifier is empty, over-long, contains a control
            character, or contains a dot that the caller cannot allow.
    """
    if not identifier or len(identifier) > 128:
        raise ValueError(
            f"Invalid {identifier_type}: {identifier!r}. "
            "Must be between 1 and 128 characters."
        )
    if _CONTROL_CHARS.search(identifier):
        raise ValueError(
            f"Invalid {identifier_type}: {identifier!r}. "
            "Control characters are not allowed."
        )
    if not allow_dot and '.' in identifier:
        raise ValueError(
            f"Invalid {identifier_type}: {identifier!r}. A dot would make a "
            "schema-qualified name ambiguous."
        )
    return identifier


def quote_ident(identifier: str) -> str:
    """Bracket-quote a T-SQL identifier, escaping any embedded ``]``.

    SQL Server escapes a closing bracket inside a delimited identifier by
    doubling it, so ``my]table`` must become ``[my]]table]``. Without this a
    crafted identifier would terminate the quote early.

    This is defence in depth: callers that interpolate the result into a
    statement validate the identifier with :func:`validate_ident` or
    :func:`validate_catalog_ident` first.

    Args:
        identifier: Raw identifier as read from the system catalog.

    Returns:
        The bracket-quoted identifier.
    """
    return f"[{identifier.replace(']', ']]')}]"


def _build_column_description(col_info: Dict[str, Any], key_type: str, is_nullable: str) -> str:
    """Build the human-readable description shown for a column.

    Args:
        col_info: One row from the column catalog query.
        key_type: Resolved key kind, or ``NONE``.
        is_nullable: ``YES`` or ``NO``.

    Returns:
        The description string.
    """
    comment = col_info['column_comment']
    parts = [
        str(comment) if comment
        else f"Column {col_info['column_name']} of type {col_info['data_type']}"
    ]
    if key_type != 'NONE':
        parts.append(f"({key_type})")
    if is_nullable == 'NO':
        parts.append("(NOT NULL)")
    if col_info['column_default'] is not None:
        parts.append(f"(Default: {col_info['column_default']})")
    return ' '.join(parts)


class SQLServerLoader(BaseLoader):
    """
    Loader for SQL Server databases that connects and extracts schema information.
    """

    # DDL operations that modify database schema  # pylint: disable=duplicate-code
    SCHEMA_MODIFYING_OPERATIONS = {
        'CREATE', 'ALTER', 'DROP', 'RENAME', 'TRUNCATE'
    }

    # More specific patterns for schema-affecting operations
    SCHEMA_PATTERNS = [  # pylint: disable=duplicate-code
        r'^\s*CREATE\s+TABLE',
        r'^\s*CREATE\s+INDEX',
        r'^\s*CREATE\s+UNIQUE\s+INDEX',
        r'^\s*ALTER\s+TABLE',
        r'^\s*DROP\s+TABLE',
        r'^\s*DROP\s+INDEX',
        r'^\s*RENAME\s+TABLE',
        r'^\s*TRUNCATE\s+TABLE',
        r'^\s*CREATE\s+VIEW',
        r'^\s*DROP\s+VIEW',
        r'^\s*CREATE\s+SCHEMA',
        r'^\s*DROP\s+SCHEMA',
    ]

    @staticmethod
    def _execute_sample_query(
        cursor, table_name: str, col_name: str, sample_size: int = 3
    ) -> List[Any]:
        """
        Execute query to get random sample values for a column.
        SQL Server implementation using TOP with NEWID() for random sampling.

        ``table_name`` may be schema-qualified (``schema.table``); each part is
        bracket-quoted separately so the schema prefix survives. A dot is legal
        inside a bracket-quoted name, but a single dotted string cannot say
        which dot is the separator, so neither part may contain one: a
        dot-bearing name is rejected rather than sampled from the wrong object.
        """
        schema, _, bare_table = table_name.rpartition('.')
        qualified = quote_ident(
            validate_catalog_ident(bare_table, "table name", allow_dot=False)
        )
        if schema:
            qualified = (
                f"{quote_ident(validate_catalog_ident(schema, 'schema name', allow_dot=False))}"
                f".{qualified}"
            )

        col = quote_ident(validate_catalog_ident(col_name, "column name"))
        if not isinstance(sample_size, int) or sample_size <= 0:
            raise ValueError(f"sample_size must be a positive integer, got {sample_size!r}")

        # Identifiers are validated and bracket-quoted with ``]`` escaped, since
        # T-SQL cannot bind identifiers as parameters.
        #
        # The DISTINCT sits in a derived table because SQL Server rejects
        # ``SELECT DISTINCT ... ORDER BY NEWID()`` outright: "ORDER BY items
        # must appear in the select list if SELECT DISTINCT is specified".
        query = (
            f"SELECT TOP {int(sample_size)} {col}"
            f" FROM (SELECT DISTINCT {col} FROM {qualified}"
            f" WHERE {col} IS NOT NULL) AS sampled"
            f" ORDER BY NEWID()"
        )
        cursor.execute(query)

        # The cursor is opened with ``as_dict=True`` so rows are keyed by column
        # name only — pymssql's ``row2dict`` strips positional keys.
        #
        # Serialized here because the base wrapper keeps a sample only when it
        # is already a str/int/float, so the driver's own objects — uuid.UUID
        # for ``uniqueidentifier``, datetime, Decimal, bytes — would otherwise
        # be dropped and the column would silently describe itself with no
        # examples at all.
        sample_results = cursor.fetchall()
        return [
            SQLServerLoader._serialize_value(row[col_name])
            for row in sample_results
            if row[col_name] is not None
        ]

    @classmethod
    def extract_sample_values_for_column(
        cls, cursor, table_name: str, col_name: str, sample_size: int = 3
    ) -> List[Any]:
        """Sample *col_name*, returning ``[]`` rather than failing the whole load.

        Sampling is best-effort decoration on top of the catalog data, but it is
        also the only part of introspection that touches user tables, so it is
        where the surprises live: ``DISTINCT`` is not defined for ``xml``,
        ``text``, ``image`` or the spatial types, and a name that survives the
        catalog can still be one this loader will not interpolate. Either would
        otherwise abort a schema that is fine apart from one column.
        """
        try:
            return super().extract_sample_values_for_column(
                cursor, table_name, col_name, sample_size
            )
        except (ValueError, pymssql.Error) as exc:
            # %r so a control character in a catalog name cannot forge a log line.
            logging.warning(
                "Skipping sample values for %r.%r: %s", table_name, col_name, exc
            )
            return []

    @staticmethod
    def _serialize_value(value):
        """
        Convert non-JSON serializable values to JSON serializable format.

        Args:
            value: The value to serialize

        Returns:
            JSON serializable version of the value
        """
        if isinstance(value, (datetime.date, datetime.datetime, datetime.time)):
            return value.isoformat()
        if isinstance(value, decimal.Decimal):
            return float(value)
        # pymssql decodes ``uniqueidentifier`` to uuid.UUID, which the result
        # stream's plain json.dumps cannot encode.
        if isinstance(value, uuid.UUID):
            return str(value)
        if isinstance(value, bytes):
            return value.hex()
        return value

    @staticmethod
    def parse_schema_from_url(connection_url: str) -> str:
        """
        Parse the target schema from the connection URL's ``schema`` parameter.

        Expected format:
            ``sqlserver://user:pass@host:port/database?schema=schema_name``

        Args:
            connection_url: SQL Server connection URL

        Returns:
            The requested schema, or ``dbo`` when not specified.

        Raises:
            ValueError: If the requested schema is not a valid identifier.
        """
        try:
            parsed = urlparse(connection_url)
            # parse_qs already percent-decodes; decoding again would accept
            # double-encoded values that validate_ident should reject.
            schema = parse_qs(parsed.query).get('schema', [''])[0].strip()
        except (ValueError, AttributeError):
            return DEFAULT_SCHEMA
        if not schema:
            return DEFAULT_SCHEMA
        return validate_ident(schema, "schema name")

    @staticmethod
    def _parse_sqlserver_url(connection_url: str) -> Dict[str, Any]:
        """
        Parse SQL Server connection URL into connection parameters.

        Args:
            connection_url: SQL Server connection URL in format:
                          sqlserver://user:password@host:port/database

        Returns:
            Dict with connection parameters accepted by ``pymssql.connect``.

        Raises:
            ValueError: If the URL is malformed.
        """
        if not connection_url.lower().startswith('sqlserver://'):
            raise ValueError(
                "Invalid SQL Server URL format. Expected "
                "sqlserver://user:password@host:port/database"
            )

        parsed = urlparse(connection_url)

        if not parsed.hostname:
            raise ValueError("SQL Server URL must include a host")

        database = unquote(parsed.path or '').lstrip('/')
        if not database:
            raise ValueError("SQL Server URL must include database name")

        if not parsed.username:
            raise ValueError("SQL Server URL must include username and host")

        params: Dict[str, Any] = {
            'server': parsed.hostname,
            'port': parsed.port or DEFAULT_PORT,
            'user': unquote(parsed.username),
            'password': unquote(parsed.password) if parsed.password else "",
            'database': database,
        }

        # Opt-in transport encryption: ``?encrypt=true`` maps to FreeTDS' TLS
        # negotiation. Left unset otherwise to preserve driver defaults.
        encrypt = parse_qs(parsed.query).get('encrypt', [''])[0].strip().lower()
        if encrypt in ('true', '1', 'yes', 'require'):
            params['encryption'] = 'require'
        elif encrypt in ('false', '0', 'no', 'off'):
            params['encryption'] = 'off'

        return params

    @staticmethod
    def _with_timeouts(conn_params: Dict[str, Any]) -> Dict[str, Any]:
        """Bound how long a connect or a query may pin a worker thread.

        Without these, a blackholed network or a stalled server holds a thread
        forever and eventually drains the shared introspection executor, taking
        every other database with it. ``login_timeout`` covers the TCP/login
        handshake and ``timeout`` the query itself, both in seconds.

        Both are deliberately the *same* for every caller. pymssql documents
        that ``timeout`` and ``login_timeout`` "[have] a process-wide effect
        because the FreeTDS db-lib API functions used to implement such timeouts
        have a global effect" — so handing introspection and query execution
        different budgets would just let concurrent operations overwrite each
        other's, leaving both nondeterministic. The larger of the two settings
        wins: it still bounds the wait, and it is the only choice that cannot
        cut short an operation that was legitimately given the longer budget.
        """
        return {
            **conn_params,
            'login_timeout': Config.DB_CONNECT_TIMEOUT,
            'timeout': max(Config.DB_SCHEMA_TIMEOUT, Config.DB_STATEMENT_TIMEOUT),
        }

    @staticmethod
    def _introspect_schema(
        conn_params: Dict[str, Any], schema: str
    ) -> Tuple[Dict[str, Any], Dict[str, List[Dict[str, str]]]]:
        """Connect, introspect and close — all inside one worker thread.

        Everything touching the driver lives here so the connection and cursor
        are created, used and closed by the same thread. Closing them from the
        event loop instead can run while an offloaded introspection is still
        using them, because cancelling a ``to_thread`` call does not stop the
        thread it is running in.

        Mirrors ``PostgresLoader._introspect_schema``; see ``load`` for why the
        work is offloaded at all.
        """
        conn = None
        cursor = None
        try:
            conn = pymssql.connect(  # pylint: disable=no-member
                **SQLServerLoader._with_timeouts(conn_params)
            )
            cursor = conn.cursor(as_dict=True)

            foreign_keys = SQLServerLoader.extract_foreign_keys(cursor, schema)
            entities = SQLServerLoader.extract_tables_info(
                cursor, schema, SQLServerLoader.group_foreign_keys(foreign_keys)
            )
            relationships = SQLServerLoader.build_relationships(foreign_keys)
            return entities, relationships
        finally:
            SQLServerLoader._close_quietly(cursor, conn)

    @staticmethod
    async def load(  # pylint: disable=arguments-differ
        prefix: str,
        connection_url: str,
        db=None,
    ) -> AsyncGenerator[tuple[bool, str], None]:
        """
        Load the graph data from a SQL Server database into the graph database.

        Args:
            prefix: Graph name prefix (typically the user id).
            connection_url: SQL Server connection URL in format:
                          sqlserver://user:password@host:port/database
            db: Optional FalkorDB handle; falls back to the server singleton.

        Yields:
            Tuple[bool, str]: Success status and message
        """
        try:
            # Parsed here rather than in the worker so a malformed URL is
            # reported as a failure before any progress is announced.
            conn_params = SQLServerLoader._parse_sqlserver_url(connection_url)
            schema = SQLServerLoader.parse_schema_from_url(connection_url)
            db_name = conn_params['database']

            # pymssql is a blocking driver, so every connect/execute/fetch would
            # stall the event loop — and with it every other request and the
            # stream keepalives. Offload to the shared introspection executor,
            # the same way the PostgreSQL and MySQL loaders do.
            yield True, "Extracting table information..."
            entities, relationships = await run_introspection(
                SQLServerLoader._introspect_schema, conn_params, schema
            )

            # Load data into graph
            yield True, "Loading data into graph..."
            await load_to_graph(f"{prefix}_{db_name}", entities, relationships,
                                db_name=db_name, db_url=connection_url, db=db)

            yield True, (f"SQL Server schema loaded successfully. "
                         f"Found {len(entities)} tables.")

        except pymssql.Error as e:
            logging.error("SQL Server connection error: %s", e)
            yield False, "Failed to connect to SQL Server database"
        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.error("Error loading SQL Server schema: %s", e)
            yield False, "Failed to load SQL Server database schema"

    @staticmethod
    def _close_quietly(cursor, conn) -> None:
        """Close *cursor* and *conn* if still open, ignoring teardown errors."""
        for handle in (cursor, conn):
            if handle is None:
                continue
            try:
                handle.close()
            except Exception:  # pylint: disable=broad-exception-caught
                logging.debug("Ignoring error while closing SQL Server handle", exc_info=True)

    @staticmethod
    def extract_tables_info(
        cursor,
        schema: str = DEFAULT_SCHEMA,
        foreign_keys_by_table: Dict[str, List[Dict[str, str]]] | None = None,
    ) -> Dict[str, Any]:
        """
        Extract table and column information from a SQL Server schema.

        Args:
            cursor: Database cursor
            schema: Schema to extract tables from (default: ``dbo``)
            foreign_keys_by_table: Foreign keys for the whole schema, keyed by
                owning table, as produced by :meth:`group_foreign_keys`. Passed
                in rather than queried per table, which would be one round trip
                per table on a large schema.

        Returns:
            Dict containing table information
        """
        entities = {}
        foreign_keys_by_table = foreign_keys_by_table or {}

        # Get all tables in the requested schema. ``s.name`` is selected back so
        # sample queries qualify tables with the server's own canonical schema
        # name rather than the string taken from the connection URL.
        cursor.execute("""
            SELECT
                t.name AS table_name,
                s.name AS schema_name,
                ISNULL(CAST(ep.value AS NVARCHAR(MAX)), '') AS table_comment
            FROM sys.tables t
            JOIN sys.schemas s ON t.schema_id = s.schema_id
            LEFT JOIN sys.extended_properties ep
                ON ep.major_id = t.object_id
                AND ep.minor_id = 0
                AND ep.class = 1
                AND ep.name = 'MS_Description'
            WHERE t.is_ms_shipped = 0
            AND s.name = %s
            ORDER BY t.name;
        """, (schema,))

        tables = cursor.fetchall()

        for table_info in tqdm.tqdm(tables, desc="Extracting table information"):
            table_name = table_info['table_name']
            table_comment = table_info['table_comment']
            catalog_schema = table_info['schema_name']

            # Get column information for this table
            columns_info = SQLServerLoader.extract_columns_info(
                cursor, schema, table_name, catalog_schema
            )

            # Generate table description
            table_description = table_comment if table_comment else f"Table: {table_name}"

            # Get column descriptions for batch embedding
            col_descriptions = [col_info['description'] for col_info in columns_info.values()]

            entities[table_name] = {
                'description': table_description,
                'columns': columns_info,
                'foreign_keys': foreign_keys_by_table.get(table_name, []),
                'col_descriptions': col_descriptions
            }

        return entities

    @staticmethod
    def extract_columns_info(
        cursor, schema: str, table_name: str, catalog_schema: str
    ) -> Dict[str, Any]:
        """
        Extract column information for a specific table.

        Args:
            cursor: Database cursor
            schema: Schema owning the table. Only ever passed to the driver as
                a bound query parameter, never interpolated into a statement.
            table_name: Name of the table, as returned by ``sys.tables``
            catalog_schema: Schema name as returned by ``sys.schemas``. Sample
                queries interpolate this rather than *schema*, so the value
                that reaches a statement body comes from the server rather
                than from the connection URL.

        Returns:
            Dict containing column information
        """
        cursor.execute("""
            SELECT
                c.name AS column_name,
                tp.name AS data_type,
                c.is_nullable,
                dc.definition AS column_default,
                CASE
                    WHEN pk.column_id IS NOT NULL THEN 'PRIMARY KEY'
                    WHEN fk.parent_column_id IS NOT NULL THEN 'FOREIGN KEY'
                    WHEN uc.column_id IS NOT NULL THEN 'UNIQUE KEY'
                    ELSE 'NONE'
                END AS column_key,
                ISNULL(CAST(ep.value AS NVARCHAR(MAX)), '') AS column_comment
            FROM sys.columns c
            JOIN sys.types tp ON c.user_type_id = tp.user_type_id
            JOIN sys.tables t ON c.object_id = t.object_id
            JOIN sys.schemas s ON t.schema_id = s.schema_id
            LEFT JOIN sys.default_constraints dc ON c.default_object_id = dc.object_id
            LEFT JOIN (
                SELECT ic.object_id, ic.column_id
                FROM sys.index_columns ic
                JOIN sys.indexes i ON ic.object_id = i.object_id AND ic.index_id = i.index_id
                WHERE i.is_primary_key = 1
            ) pk ON c.object_id = pk.object_id AND c.column_id = pk.column_id
            LEFT JOIN (
                SELECT DISTINCT fkc.parent_object_id, fkc.parent_column_id
                FROM sys.foreign_key_columns fkc
            ) fk ON fk.parent_object_id = c.object_id AND fk.parent_column_id = c.column_id
            LEFT JOIN (
                SELECT DISTINCT ic.object_id, ic.column_id
                FROM sys.index_columns ic
                JOIN sys.indexes i ON ic.object_id = i.object_id AND ic.index_id = i.index_id
                WHERE i.is_unique = 1 AND i.is_primary_key = 0
            ) uc ON c.object_id = uc.object_id AND c.column_id = uc.column_id
            LEFT JOIN sys.extended_properties ep
                ON ep.major_id = c.object_id
                AND ep.minor_id = c.column_id
                AND ep.class = 1
                AND ep.name = 'MS_Description'
            WHERE s.name = %s AND t.name = %s
            ORDER BY c.column_id;
        """, (schema, table_name))

        columns = cursor.fetchall()
        columns_info = {}

        qualified_table = f"{catalog_schema}.{table_name}"

        for col_info in columns:
            col_name = col_info['column_name']
            is_nullable = 'YES' if col_info['is_nullable'] else 'NO'
            key_type = col_info['column_key']

            columns_info[col_name] = {
                'type': col_info['data_type'],
                'null': is_nullable,
                'key': key_type,
                'description': _build_column_description(col_info, key_type, is_nullable),
                'default': col_info['column_default'],
                # Stored separately, not folded into the description.
                'sample_values': SQLServerLoader.extract_sample_values_for_column(
                    cursor, qualified_table, col_name
                ),
            }

        return columns_info

    @staticmethod
    def extract_foreign_keys(
        cursor, schema: str = DEFAULT_SCHEMA
    ) -> List[Dict[str, str]]:
        """
        Extract every foreign key in a schema, in a single query.

        Both the parent and the referenced table must live in *schema*, so a key
        never names a table that was not loaded. The per-entity view and the
        relationship map are both derived from these rows — see
        :meth:`group_foreign_keys` and :meth:`build_relationships` — rather than
        from a second query per table.

        Args:
            cursor: Database cursor
            schema: Schema to extract foreign keys from (default: ``dbo``)

        Returns:
            One dict per foreign-key column, in constraint order.
        """
        cursor.execute("""
            SELECT
                pt.name AS table_name,
                fk.name AS constraint_name,
                cp.name AS column_name,
                rt.name AS referenced_table_name,
                cr.name AS referenced_column_name
            FROM sys.foreign_keys fk
            JOIN sys.foreign_key_columns fkc
                ON fk.object_id = fkc.constraint_object_id
            JOIN sys.columns cp
                ON fkc.parent_object_id = cp.object_id
                AND fkc.parent_column_id = cp.column_id
            JOIN sys.tables pt
                ON fkc.parent_object_id = pt.object_id
            JOIN sys.schemas ps ON pt.schema_id = ps.schema_id
            JOIN sys.tables rt
                ON fkc.referenced_object_id = rt.object_id
            JOIN sys.schemas rs ON rt.schema_id = rs.schema_id
            JOIN sys.columns cr
                ON fkc.referenced_object_id = cr.object_id
                AND fkc.referenced_column_id = cr.column_id
            WHERE ps.name = %s AND rs.name = %s
            ORDER BY pt.name, fk.name;
        """, (schema, schema))

        return [{
            'table': fk_info['table_name'],
            'constraint_name': fk_info['constraint_name'],
            'column': fk_info['column_name'],
            'referenced_table': fk_info['referenced_table_name'],
            'referenced_column': fk_info['referenced_column_name'],
        } for fk_info in cursor.fetchall()]

    @staticmethod
    def group_foreign_keys(
        foreign_keys: List[Dict[str, str]]
    ) -> Dict[str, List[Dict[str, str]]]:
        """Group :meth:`extract_foreign_keys` rows by the table that owns them."""
        by_table: Dict[str, List[Dict[str, str]]] = {}
        for fk in foreign_keys:
            by_table.setdefault(fk['table'], []).append(
                {key: value for key, value in fk.items() if key != 'table'}
            )
        return by_table

    @staticmethod
    def build_relationships(
        foreign_keys: List[Dict[str, str]]
    ) -> Dict[str, List[Dict[str, str]]]:
        """Group :meth:`extract_foreign_keys` rows by constraint.

        A composite key contributes one row per column, all under the one
        constraint name.
        """
        relationships: Dict[str, List[Dict[str, str]]] = {}
        for fk in foreign_keys:
            constraint_name = fk['constraint_name']
            relationships.setdefault(constraint_name, []).append({
                'from': fk['table'],
                'to': fk['referenced_table'],
                'source_column': fk['column'],
                'target_column': fk['referenced_column'],
                'note': f'Foreign key constraint: {constraint_name}'
            })
        return relationships

    @staticmethod
    def is_schema_modifying_query(sql_query: str) -> Tuple[bool, str]:
        """
        Check if a SQL query modifies the database schema.

        Args:
            sql_query: The SQL query to check

        Returns:
            Tuple of (is_schema_modifying, operation_type)
        """
        if not sql_query or not sql_query.strip():
            return False, ""

        # Clean and normalize the query
        normalized_query = sql_query.strip().upper()

        # Check for basic DDL operations
        first_word = normalized_query.split()[0] if normalized_query.split() else ""
        if first_word in SQLServerLoader.SCHEMA_MODIFYING_OPERATIONS:
            # Additional pattern matching for more precise detection
            for pattern in SQLServerLoader.SCHEMA_PATTERNS:
                if re.match(pattern, normalized_query, re.IGNORECASE):
                    return True, first_word

            # If it's a known DDL operation but doesn't match specific patterns,
            # still consider it schema-modifying (better safe than sorry)
            return True, first_word

        return False, ""

    @staticmethod
    async def refresh_graph_schema(graph_id: str, db_url: str, db=None) -> Tuple[bool, str]:
        """
        Refresh the graph schema by clearing existing data and reloading from the database.

        Args:
            graph_id: The graph ID to refresh
            db_url: Database connection URL
            db: Optional FalkorDB handle; falls back to the server singleton.

        Returns:
            Tuple of (success, message)
        """
        try:
            logging.info("Schema modification detected. Refreshing graph schema.")

            from api.core.db_resolver import resolve_db  # pylint: disable=import-outside-toplevel

            # ``load`` names the graph f"{prefix}_{db_name}", so strip that exact
            # suffix — splitting on "_" mistakes a database name that contains one
            # for the prefix boundary. Parsed before the delete so a bad URL cannot
            # drop the graph without reloading it.
            db_name = SQLServerLoader._parse_sqlserver_url(db_url)['database']
            suffix = f"_{db_name}"
            prefix = graph_id[:-len(suffix)] if graph_id.endswith(suffix) else graph_id

            # Clear existing graph data
            # Drop current graph before reloading
            graph = resolve_db(db).select_graph(graph_id)
            await graph.delete()

            # Reuse the existing load method to reload the schema
            success, message = False, ""
            async for progress in SQLServerLoader.load(prefix, db_url, db=db):
                success, message = progress

            if success:
                logging.info("Graph schema refreshed successfully.")
                return True, message

            logging.error("Schema refresh failed")
            return False, "Failed to reload schema"

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Log the error and return failure
            logging.error("Error refreshing graph schema: %s", str(e))
            error_msg = "Error refreshing graph schema"
            logging.error(error_msg)
            return False, error_msg

    @staticmethod
    def execute_sql_query(sql_query: str, db_url: str) -> List[Dict[str, Any]]:
        """
        Execute a SQL query on the SQL Server database and return the results.

        Args:
            sql_query: The SQL query to execute
            db_url: SQL Server connection URL in format:
                    sqlserver://user:password@host:port/database

        Returns:
            List of dictionaries containing the query results

        Raises:
            SQLServerQueryError: If the query fails.
        """
        conn = None
        cursor = None
        try:
            # Parse connection URL
            conn_params = SQLServerLoader._parse_sqlserver_url(db_url)

            # Connect to SQL Server database
            conn = pymssql.connect(  # pylint: disable=no-member
                **SQLServerLoader._with_timeouts(conn_params)
            )
            cursor = conn.cursor(as_dict=True)

            # Execute the SQL query
            cursor.execute(sql_query)

            # Check if the query returns results (SELECT queries)
            if cursor.description is not None:
                # This is a SELECT query or similar that returns rows
                results = cursor.fetchall()
                result_list = []
                for row in results:
                    # Serialize each value to ensure JSON compatibility
                    serialized_row = {
                        key: SQLServerLoader._serialize_value(value)
                        for key, value in row.items()
                    }
                    result_list.append(serialized_row)
            else:
                # This is an INSERT, UPDATE, DELETE, or other non-SELECT query
                # Return information about the operation
                affected_rows = cursor.rowcount
                sql_type = sql_query.strip().split()[0].upper()

                if sql_type in ['INSERT', 'UPDATE', 'DELETE']:
                    result_list = [{
                        "operation": sql_type,
                        "affected_rows": affected_rows,
                        "status": "success"
                    }]
                else:
                    # For other types of queries (CREATE, DROP, etc.)
                    result_list = [{
                        "operation": sql_type,
                        "status": "success"
                    }]

            # Commit the transaction for write operations
            conn.commit()

            return result_list

        except pymssql.Error as e:
            SQLServerLoader._rollback_quietly(conn)
            logging.error("SQL Server query execution error: %s", e)
            raise SQLServerQueryError(f"SQL Server query execution error: {str(e)}") from e
        except Exception as e:
            SQLServerLoader._rollback_quietly(conn)
            logging.error("Error executing SQL query: %s", e)
            raise SQLServerQueryError(f"Error executing SQL query: {str(e)}") from e
        finally:
            SQLServerLoader._close_quietly(cursor, conn)

    @staticmethod
    def _rollback_quietly(conn) -> None:
        """Roll *conn* back if it exists, ignoring rollback failures."""
        if conn is None:
            return
        try:
            conn.rollback()
        except Exception:  # pylint: disable=broad-exception-caught
            logging.debug("Ignoring error during SQL Server rollback", exc_info=True)
