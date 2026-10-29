"""Oracle loader for loading database schemas into FalkorDB graphs."""

import contextlib
import datetime
import decimal
import logging
import re
from typing import AsyncGenerator, Dict, Any, List, Tuple
from urllib.parse import urlparse, parse_qs, unquote

import tqdm
import oracledb

from api.config import Config
from api.loaders.base_loader import BaseLoader
from api.loaders.graph_loader import load_to_graph
from api.loaders.introspection import run_introspection


class OracleQueryError(Exception):
    """Exception raised for Oracle query execution errors."""


class OracleConnectionError(Exception):
    """Exception raised for Oracle connection errors."""


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class OracleLoader(BaseLoader):
    """
    Loader for Oracle databases that connects and extracts schema information.

    Connects with python-oracledb in thin mode, which speaks the TNS wire
    protocol directly and needs no Oracle Instant Client install.
    """

    # DDL operations that modify database schema  # pylint: disable=duplicate-code
    SCHEMA_MODIFYING_OPERATIONS = {
        'CREATE', 'ALTER', 'DROP', 'RENAME', 'TRUNCATE'
    }

    # LOB-family types reject DISTINCT/ORDER BY outright (ORA-00932), which
    # the sample-value query relies on — sampling these raises instead of
    # returning no samples, so they are skipped rather than queried.
    UNSAMPLEABLE_TYPES = frozenset({
        'CLOB', 'NCLOB', 'BLOB', 'BFILE', 'LONG', 'LONG RAW', 'XMLTYPE',
    })

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
    ]

    @staticmethod
    def _validate_identifier(identifier: str, identifier_type: str = "identifier") -> None:
        """
        Validate that an identifier (table, column, schema name) is safe to
        interpolate into a SQL string.

        Oracle has no bind-variable syntax for identifiers — only for values —
        so table/column/schema names used in introspection queries are built
        by string formatting. Restricting them to Oracle's own unquoted-
        identifier charset before quoting closes that injection surface.

        Args:
            identifier: The identifier to validate
            identifier_type: Type of identifier for error messages

        Raises:
            ValueError: If identifier contains invalid characters
        """
        if not re.match(r'^[A-Za-z0-9_$#]+$', identifier):
            raise ValueError(
                f"Invalid {identifier_type}: {identifier!r}. "
                "Only alphanumeric characters, underscore, dollar sign and "
                "hash are allowed."
            )
        if len(identifier) > 128:
            raise ValueError(f"Invalid {identifier_type}: exceeds maximum length of 128")

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        """
        Safely quote an Oracle identifier by escaping embedded double quotes.

        Args:
            identifier: The identifier to quote

        Returns:
            Quoted identifier safe for SQL interpolation
        """
        escaped = identifier.replace('"', '""')
        return f'"{escaped}"'

    @staticmethod
    def _execute_sample_query(
        cursor, table_name: str, col_name: str, sample_size: int = 3
    ) -> List[Any]:
        """
        Execute query to get random sample values for a column.
        Oracle implementation using DBMS_RANDOM.VALUE for random sampling.
        """
        OracleLoader._validate_identifier(table_name, "table name")
        OracleLoader._validate_identifier(col_name, "column name")

        if not isinstance(sample_size, int) or sample_size <= 0:
            raise ValueError(f"sample_size must be a positive integer, got {sample_size!r}")

        quoted_table = OracleLoader._quote_identifier(table_name)
        quoted_col = OracleLoader._quote_identifier(col_name)

        query = f"""
            SELECT DISTINCT {quoted_col}
            FROM {quoted_table}
            WHERE {quoted_col} IS NOT NULL
            ORDER BY DBMS_RANDOM.VALUE
            FETCH FIRST :sample_size ROWS ONLY
        """
        cursor.execute(query, {"sample_size": sample_size})
        sample_results = cursor.fetchall()
        return [row[0] for row in sample_results if row[0] is not None]

    @staticmethod
    def _serialize_value(value):
        """
        Convert non-JSON serializable values to JSON serializable format.

        Args:
            value: The value to serialize

        Returns:
            JSON serializable version of the value
        """
        if isinstance(value, (datetime.date, datetime.datetime)):
            return value.isoformat()
        if isinstance(value, datetime.time):
            return value.isoformat()
        if isinstance(value, decimal.Decimal):
            return float(value)
        if isinstance(value, oracledb.LOB):
            # CLOB/BLOB columns surface as LOB handles, not plain Python
            # values; read() materializes the content before it leaves the
            # connection (a LOB handle is invalid once the cursor advances).
            return value.read()
        if value is None:
            return None
        return value

    @staticmethod
    def _parse_oracle_url(connection_url: str) -> Dict[str, Any]:
        """
        Parse Oracle connection URL into components.

        Format: oracle://username:password@host:port/service_name
        Optionally with a schema other than the connecting user's own via
        ``?schema=OTHER_SCHEMA``, and/or ``?ssl=true`` for endpoints that
        require TLS (e.g. Oracle Cloud Autonomous Database, which rejects
        plaintext TCP outright) — this builds an Easy Connect Plus ``tcps://``
        DSN instead of a plain ``host:port/service_name`` one, so no Oracle
        wallet file is needed for connections to a publicly-trusted endpoint.

        Args:
            connection_url: Oracle connection URL

        Returns:
            Dict with 'user', 'password', 'dsn' (for oracledb.connect) and
            'schema' (the owner to introspect)
        """
        if not connection_url.startswith('oracle://'):
            raise ValueError(
                "Invalid Oracle URL format. Expected "
                "oracle://username:password@host:port/service_name"
            )

        parsed = urlparse(connection_url)

        if not parsed.username:
            raise ValueError("Oracle URL must include username")
        if not parsed.hostname:
            raise ValueError("Oracle URL must include host")

        service_name = parsed.path.strip('/').split('/')[0]
        if not service_name:
            raise ValueError("Oracle URL must include a service name")

        # Credentials containing URL delimiters (':', '@', '/', '#', '?') must
        # arrive percent-encoded; the UI's URL builder encodes them for you.
        username = unquote(parsed.username)
        password = unquote(parsed.password or "")
        port = parsed.port or 1521

        query_params = parse_qs(parsed.query)
        # Unquoted Oracle identifiers are stored upper-case; a schema the
        # caller typed in lower case would otherwise match nothing.
        schema = query_params.get('schema', [username])[0].upper()
        use_tls = query_params.get('ssl', ['false'])[0].strip().lower() in ('1', 'true', 'yes')

        OracleLoader._validate_identifier(schema, "schema")

        if use_tls:
            dsn = f"tcps://{parsed.hostname}:{port}/{service_name}?ssl_server_dn_match=true"
        else:
            dsn = f"{parsed.hostname}:{port}/{service_name}"

        return {
            'user': username,
            'password': password,
            'dsn': dsn,
            'schema': schema,
        }

    @staticmethod
    def _introspect_schema(conn_params: Dict[str, Any], schema: str):
        """Connect, introspect and close — all inside one worker thread.

        Cleanup lives in the same thread that owns the connection, matching
        the other loaders: cancelling a ``to_thread`` call does not stop the
        thread, so closing from the event loop could run alongside an
        in-flight introspection, and without a ``finally`` here a client
        disconnect leaks the connection outright.

        Only the connect and each call are time-bounded: introspecting a
        very large schema can legitimately outlast DB_STATEMENT_TIMEOUT,
        which is sized for user queries.
        """
        conn = None
        cursor = None
        try:
            connect_kwargs = {k: v for k, v in conn_params.items() if k != 'schema'}
            conn = oracledb.connect(
                **connect_kwargs,
                tcp_connect_timeout=Config.DB_CONNECT_TIMEOUT,
            )
            # Bounds each round-trip call (milliseconds), not just the
            # connect — the per-query equivalent of a statement_timeout.
            conn.call_timeout = Config.DB_SCHEMA_TIMEOUT * 1000
            cursor = conn.cursor()
            entities = OracleLoader.extract_tables_info(cursor, schema)
            relationships = OracleLoader.extract_relationships(cursor, schema)
            return entities, relationships
        finally:
            if cursor is not None:
                with contextlib.suppress(Exception):
                    cursor.close()
            if conn is not None:
                with contextlib.suppress(Exception):
                    conn.close()

    @staticmethod
    async def load(  # pylint: disable=arguments-differ
        prefix: str,
        connection_url: str,
        db=None,
    ) -> AsyncGenerator[tuple[bool, str], None]:
        """
        Load the graph data from an Oracle database into the graph database.

        Args:
            connection_url: Oracle connection URL in format:
                          oracle://username:password@host:port/service_name
            db: Optional FalkorDB handle; falls back to the server singleton.

        Returns:
            Tuple[bool, str]: Success status and message
        """
        try:
            conn_params = OracleLoader._parse_oracle_url(connection_url)
            schema = conn_params['schema']
            # Namespace the graph by schema, not service name: two
            # connections to the same service can introspect different
            # schemas and must not collide on one graph.
            db_name = schema.lower()

            yield True, "Extracting table information..."
            entities, relationships = await run_introspection(
                OracleLoader._introspect_schema, conn_params, schema
            )

            yield True, "Loading data into graph..."
            await load_to_graph(f"{prefix}_{db_name}", entities, relationships,
                         db_name=db_name, db_url=connection_url, db=db)

            yield True, (f"Oracle schema loaded successfully. "
                         f"Found {len(entities)} tables.")

        except oracledb.Error as e:
            logging.error("Oracle connection error: %s", e)
            yield False, "Failed to connect to Oracle database"
        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.error("Error loading Oracle schema: %s", e)
            yield False, "Failed to load Oracle database schema"

    @staticmethod
    def extract_tables_info(cursor, schema: str) -> Dict[str, Any]:
        """
        Extract table and column information from an Oracle schema.

        Args:
            cursor: Database cursor
            schema: Schema (owner) to extract tables from

        Returns:
            Dict containing table information
        """
        OracleLoader._validate_identifier(schema, "schema")

        entities = {}

        cursor.execute("""
            SELECT table_name, comments
            FROM all_tab_comments
            WHERE owner = :schema
            AND table_type = 'TABLE'
            AND table_name NOT LIKE 'BIN$%'
            ORDER BY table_name
        """, {"schema": schema})

        tables = cursor.fetchall()

        for table_name, table_comment in tqdm.tqdm(tables, desc="Extracting table information"):
            columns_info = OracleLoader.extract_columns_info(cursor, schema, table_name)
            foreign_keys = OracleLoader.extract_foreign_keys(cursor, schema, table_name)

            table_description = table_comment if table_comment else f"Table: {table_name}"
            col_descriptions = [col_info['description'] for col_info in columns_info.values()]

            entities[table_name] = {
                'description': table_description,
                'columns': columns_info,
                'foreign_keys': foreign_keys,
                'col_descriptions': col_descriptions
            }

        return entities

    @staticmethod
    def _primary_key_columns(cursor, schema: str, table_name: str) -> set:
        """Return the set of column names that make up the table's primary key."""
        cursor.execute("""
            SELECT acc.column_name
            FROM all_constraints ac
            JOIN all_cons_columns acc
                ON acc.owner = ac.owner
                AND acc.constraint_name = ac.constraint_name
            WHERE ac.owner = :schema
            AND ac.table_name = :table_name
            AND ac.constraint_type = 'P'
        """, {"schema": schema, "table_name": table_name})
        return {row[0] for row in cursor.fetchall()}

    @staticmethod
    def extract_columns_info(  # pylint: disable=too-many-locals
        cursor, schema: str, table_name: str
    ) -> Dict[str, Any]:
        """
        Extract column information for a specific table.

        Args:
            cursor: Database cursor
            schema: Schema (owner)
            table_name: Name of the table

        Returns:
            Dict containing column information
        """
        OracleLoader._validate_identifier(schema, "schema")
        OracleLoader._validate_identifier(table_name, "table name")

        cursor.execute("""
            SELECT
                c.column_name,
                c.data_type,
                c.nullable,
                c.data_default,
                cc.comments
            FROM all_tab_columns c
            LEFT JOIN all_col_comments cc
                ON cc.owner = c.owner
                AND cc.table_name = c.table_name
                AND cc.column_name = c.column_name
            WHERE c.owner = :schema
            AND c.table_name = :table_name
            ORDER BY c.column_id
        """, {"schema": schema, "table_name": table_name})

        columns = cursor.fetchall()
        columns_info = {}

        primary_keys = OracleLoader._primary_key_columns(cursor, schema, table_name)
        foreign_keys_cols = {
            fk['column'] for fk in OracleLoader.extract_foreign_keys(cursor, schema, table_name)
        }

        for col_name, data_type, nullable, column_default, column_comment in columns:
            # ALL_TAB_COLUMNS.NULLABLE is 'Y'/'N'; normalise to the 'YES'/'NO'
            # convention the other loaders already use in descriptions.
            is_nullable = 'YES' if nullable == 'Y' else 'NO'

            if column_default is not None:
                # DATA_DEFAULT is a LONG column; Oracle pads it with a
                # trailing newline.
                column_default = column_default.strip()
                if not column_default:
                    column_default = None

            if col_name in primary_keys:
                key_type = 'PRIMARY KEY'
            elif col_name in foreign_keys_cols:
                key_type = 'FOREIGN KEY'
            else:
                key_type = 'NONE'

            description_parts = []
            if column_comment:
                description_parts.append(column_comment)
            else:
                description_parts.append(f"Column {col_name} of type {data_type}")

            if key_type != 'NONE':
                description_parts.append(f"({key_type})")

            if is_nullable == 'NO':
                description_parts.append("(NOT NULL)")

            if column_default:
                description_parts.append(f"(Default: {column_default})")

            sample_values = (
                []
                if data_type in OracleLoader.UNSAMPLEABLE_TYPES
                else OracleLoader.extract_sample_values_for_column(
                    cursor, table_name, col_name
                )
            )

            columns_info[col_name] = {
                'type': data_type,
                'null': is_nullable,
                'key': key_type,
                'description': ' '.join(description_parts),
                'default': column_default,
                'sample_values': sample_values
            }

        return columns_info

    @staticmethod
    def extract_foreign_keys(cursor, schema: str, table_name: str) -> List[Dict[str, str]]:
        """
        Extract foreign key information for a specific table.

        Args:
            cursor: Database cursor
            schema: Schema (owner)
            table_name: Name of the table

        Returns:
            List of foreign key dictionaries
        """
        OracleLoader._validate_identifier(schema, "schema")
        OracleLoader._validate_identifier(table_name, "table name")

        cursor.execute("""
            SELECT
                ac.constraint_name,
                acc.column_name,
                r_ac.table_name AS referenced_table,
                r_acc.column_name AS referenced_column
            FROM all_constraints ac
            JOIN all_cons_columns acc
                ON acc.owner = ac.owner
                AND acc.constraint_name = ac.constraint_name
            JOIN all_constraints r_ac
                ON r_ac.owner = ac.r_owner
                AND r_ac.constraint_name = ac.r_constraint_name
            JOIN all_cons_columns r_acc
                ON r_acc.owner = r_ac.owner
                AND r_acc.constraint_name = r_ac.constraint_name
                AND r_acc.position = acc.position
            WHERE ac.owner = :schema
            AND ac.table_name = :table_name
            AND ac.constraint_type = 'R'
            ORDER BY ac.constraint_name, acc.position
        """, {"schema": schema, "table_name": table_name})

        foreign_keys = []
        for constraint_name, column_name, foreign_table, foreign_column in cursor.fetchall():
            foreign_keys.append({
                'constraint_name': constraint_name,
                'column': column_name,
                'referenced_table': foreign_table,
                'referenced_column': foreign_column
            })

        return foreign_keys

    @staticmethod
    def extract_relationships(cursor, schema: str) -> Dict[str, List[Dict[str, str]]]:
        """
        Extract all relationship information from the schema.

        Args:
            cursor: Database cursor
            schema: Schema (owner)

        Returns:
            Dict containing relationship information
        """
        OracleLoader._validate_identifier(schema, "schema")

        cursor.execute("""
            SELECT
                ac.table_name,
                ac.constraint_name,
                acc.column_name,
                r_ac.table_name AS referenced_table,
                r_acc.column_name AS referenced_column
            FROM all_constraints ac
            JOIN all_cons_columns acc
                ON acc.owner = ac.owner
                AND acc.constraint_name = ac.constraint_name
            JOIN all_constraints r_ac
                ON r_ac.owner = ac.r_owner
                AND r_ac.constraint_name = ac.r_constraint_name
            JOIN all_cons_columns r_acc
                ON r_acc.owner = r_ac.owner
                AND r_acc.constraint_name = r_ac.constraint_name
                AND r_acc.position = acc.position
            WHERE ac.owner = :schema
            AND ac.constraint_type = 'R'
            ORDER BY ac.table_name, ac.constraint_name, acc.position
        """, {"schema": schema})

        relationships = {}
        for (table_name, constraint_name, column_name,
             foreign_table, foreign_column) in cursor.fetchall():
            if constraint_name not in relationships:
                relationships[constraint_name] = []

            relationships[constraint_name].append({
                'from': table_name,
                'to': foreign_table,
                'source_column': column_name,
                'target_column': foreign_column,
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

        normalized_query = sql_query.strip().upper()

        first_word = normalized_query.split()[0] if normalized_query.split() else ""
        if first_word in OracleLoader.SCHEMA_MODIFYING_OPERATIONS:
            for pattern in OracleLoader.SCHEMA_PATTERNS:
                if re.match(pattern, normalized_query, re.IGNORECASE):
                    return True, first_word
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

            graph = resolve_db(db).select_graph(graph_id)
            await graph.delete()

            parts = graph_id.split('_')
            if len(parts) >= 2:
                prefix = '_'.join(parts[:-1])
            else:
                prefix = graph_id

            success = False
            message = ""
            async for progress_tuple in OracleLoader.load(prefix, db_url, db=db):
                success, message = progress_tuple

            if success:
                logging.info("Graph schema refreshed successfully.")
                return True, message

            logging.error("Schema refresh failed")
            return False, "Failed to reload schema"

        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.error("Error refreshing graph schema: %s", str(e))
            error_msg = "Error refreshing graph schema"
            logging.error(error_msg)
            return False, error_msg

    @staticmethod
    def execute_sql_query(sql_query: str, db_url: str) -> List[Dict[str, Any]]:
        """
        Execute a SQL query on the Oracle database and return the results.

        Args:
            sql_query: The SQL query to execute
            db_url: Oracle connection URL in format:
                    oracle://username:password@host:port/service_name

        Returns:
            List of dictionaries containing the query results
        """
        conn = None
        cursor = None
        try:
            conn_params = OracleLoader._parse_oracle_url(db_url)
            connect_kwargs = {k: v for k, v in conn_params.items() if k != 'schema'}

            conn = oracledb.connect(
                **connect_kwargs,
                tcp_connect_timeout=Config.DB_CONNECT_TIMEOUT,
            )
            conn.call_timeout = Config.DB_STATEMENT_TIMEOUT * 1000
            cursor = conn.cursor()

            # Oracle has no bare trailing-semicolon convention for a single
            # statement submitted through a driver; a user-authored query
            # that includes one is otherwise rejected with ORA-00911.
            cursor.execute(sql_query.rstrip().rstrip(';'))

            if cursor.description is not None:
                columns = [desc[0] for desc in cursor.description]
                results = cursor.fetchall()
                result_list = [
                    {
                        columns[i]: OracleLoader._serialize_value(row[i])
                        for i in range(len(columns))
                    }
                    for row in results
                ]
            else:
                affected_rows = cursor.rowcount
                sql_type = sql_query.strip().split()[0].upper()

                if sql_type in ['INSERT', 'UPDATE', 'DELETE', 'MERGE']:
                    result_list = [{
                        "operation": sql_type,
                        "affected_rows": affected_rows,
                        "status": "success"
                    }]
                else:
                    result_list = [{
                        "operation": sql_type,
                        "status": "success"
                    }]

            conn.commit()

            return result_list

        except oracledb.Error as e:
            if conn is not None:
                with contextlib.suppress(Exception):
                    conn.rollback()
            logging.error("Oracle query execution error: %s", e)
            raise OracleQueryError(f"Oracle query execution error: {str(e)}") from e
        except Exception as e:
            if conn is not None:
                with contextlib.suppress(Exception):
                    conn.rollback()
            logging.error("Error executing SQL query: %s", e)
            raise OracleQueryError(f"Error executing SQL query: {str(e)}") from e
        finally:
            if cursor is not None:
                with contextlib.suppress(Exception):
                    cursor.close()
            if conn is not None:
                with contextlib.suppress(Exception):
                    conn.close()
