"""SQL Server loader for loading database schemas into FalkorDB graphs."""

import datetime
import decimal
import logging
import re
from typing import AsyncGenerator, Dict, Any, List, Tuple
from urllib.parse import urlparse, parse_qs, unquote

import tqdm
import pymssql

from api.loaders.base_loader import BaseLoader
from api.loaders.graph_loader import load_to_graph

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

DEFAULT_SCHEMA = "dbo"
DEFAULT_PORT = 1433


class SQLServerQueryError(Exception):
    """Exception raised for SQL Server query execution errors."""


class SQLServerConnectionError(Exception):
    """Exception raised for SQL Server connection errors."""


def validate_ident(identifier: str, identifier_type: str = "identifier") -> str:
    """Validate that an identifier is safe to interpolate into T-SQL.

    T-SQL cannot bind identifiers as parameters, so table, schema and column
    names must be interpolated. This is an anchored allow-list: only characters
    that can legitimately appear in a SQL Server object name are accepted, and
    everything capable of breaking out of a bracket-delimited identifier
    (``]``, quotes, semicolons, backslashes, control characters) is rejected.

    Args:
        identifier: Raw identifier, typically read from the system catalog.
        identifier_type: Label used in the error message.

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
    if not re.fullmatch(r'[A-Za-z0-9_$#@ .\-]+', identifier):
        raise ValueError(
            f"Invalid {identifier_type}: {identifier!r}. Only letters, digits, "
            "underscore, dollar, hash, at-sign, space, dot and dash are allowed."
        )
    return identifier


def quote_ident(identifier: str) -> str:
    """Bracket-quote a T-SQL identifier, escaping any embedded ``]``.

    SQL Server escapes a closing bracket inside a delimited identifier by
    doubling it, so ``my]table`` must become ``[my]]table]``. Without this a
    crafted identifier would terminate the quote early.

    This is defence in depth: callers that interpolate the result into a
    statement validate the identifier with :func:`validate_ident` first.

    Args:
        identifier: Raw identifier as read from the system catalog.

    Returns:
        The bracket-quoted identifier.
    """
    return f"[{identifier.replace(']', ']]')}]"


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
        bracket-quoted separately so the schema prefix survives.
        """
        schema, _, bare_table = table_name.rpartition('.')
        qualified = quote_ident(validate_ident(bare_table, "table name"))
        if schema:
            qualified = f"{quote_ident(validate_ident(schema, 'schema name'))}.{qualified}"

        col = quote_ident(validate_ident(col_name, "column name"))
        if not isinstance(sample_size, int) or sample_size <= 0:
            raise ValueError(f"sample_size must be a positive integer, got {sample_size!r}")

        # Identifiers are allow-list validated and bracket-quoted with ``]``
        # escaped, since T-SQL cannot bind identifiers as parameters.
        query = (
            f"SELECT DISTINCT TOP {int(sample_size)} {col}"
            f" FROM {qualified}"
            f" WHERE {col} IS NOT NULL"
            f" ORDER BY NEWID()"
        )
        cursor.execute(query)

        # The cursor is opened with ``as_dict=True`` so rows are keyed by column
        # name only — pymssql's ``row2dict`` strips positional keys.
        sample_results = cursor.fetchall()
        return [row[col_name] for row in sample_results if row[col_name] is not None]

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
        if isinstance(value, bytes):
            return value.hex()
        if value is None:
            return None
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
            schema = parse_qs(parsed.query).get('schema', [''])[0]
            schema = unquote(schema).strip()
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
        conn = None
        cursor = None
        try:
            # Parse connection URL
            conn_params = SQLServerLoader._parse_sqlserver_url(connection_url)
            schema = SQLServerLoader.parse_schema_from_url(connection_url)

            # Connect to SQL Server database
            conn = pymssql.connect(**conn_params)  # pylint: disable=no-member
            cursor = conn.cursor(as_dict=True)

            # Get database name
            db_name = conn_params['database']

            # Get all table information
            yield True, "Extracting table information..."
            entities = SQLServerLoader.extract_tables_info(cursor, schema)

            # Get all relationship information
            yield True, "Extracting relationship information..."
            relationships = SQLServerLoader.extract_relationships(cursor, schema)

            # Close database connection
            cursor.close()
            cursor = None
            conn.close()
            conn = None

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
        finally:
            SQLServerLoader._close_quietly(cursor, conn)

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
    def extract_tables_info(cursor, schema: str = DEFAULT_SCHEMA) -> Dict[str, Any]:
        """
        Extract table and column information from a SQL Server schema.

        Args:
            cursor: Database cursor
            schema: Schema to extract tables from (default: ``dbo``)

        Returns:
            Dict containing table information
        """
        entities = {}

        # Get all tables in the requested schema
        cursor.execute("""
            SELECT
                t.name AS table_name,
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

            # Get column information for this table
            columns_info = SQLServerLoader.extract_columns_info(cursor, schema, table_name)

            # Get foreign keys for this table
            foreign_keys = SQLServerLoader.extract_foreign_keys(cursor, schema, table_name)

            # Generate table description
            table_description = table_comment if table_comment else f"Table: {table_name}"

            # Get column descriptions for batch embedding
            col_descriptions = [col_info['description'] for col_info in columns_info.values()]

            entities[table_name] = {
                'description': table_description,
                'columns': columns_info,
                'foreign_keys': foreign_keys,
                'col_descriptions': col_descriptions
            }

        return entities

    @staticmethod
    def extract_columns_info(cursor, schema: str, table_name: str) -> Dict[str, Any]:
        """
        Extract column information for a specific table.

        Args:
            cursor: Database cursor
            schema: Schema owning the table
            table_name: Name of the table

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
                    WHEN pk.column_id IS NOT NULL THEN 'PRI'
                    WHEN fk.parent_column_id IS NOT NULL THEN 'MUL'
                    WHEN uc.column_id IS NOT NULL THEN 'UNI'
                    ELSE ''
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
            LEFT JOIN sys.foreign_key_columns fk
                ON fk.parent_object_id = c.object_id AND fk.parent_column_id = c.column_id
            LEFT JOIN (
                SELECT ic.object_id, ic.column_id
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

        for col_info in columns:
            col_name = col_info['column_name']
            data_type = col_info['data_type']
            is_nullable = 'YES' if col_info['is_nullable'] else 'NO'
            column_default = col_info['column_default']
            column_key = col_info['column_key']
            column_comment = col_info['column_comment']

            # Determine key type
            if column_key == 'PRI':
                key_type = 'PRIMARY KEY'
            elif column_key == 'MUL':
                key_type = 'FOREIGN KEY'
            elif column_key == 'UNI':
                key_type = 'UNIQUE KEY'
            else:
                key_type = 'NONE'

            # Generate column description
            description_parts = []
            if column_comment:
                description_parts.append(str(column_comment))
            else:
                description_parts.append(f"Column {col_name} of type {data_type}")

            if key_type != 'NONE':
                description_parts.append(f"({key_type})")

            if is_nullable == 'NO':
                description_parts.append("(NOT NULL)")

            if column_default is not None:
                description_parts.append(f"(Default: {column_default})")

            # Extract sample values for the column (stored separately, not in description)
            sample_values = SQLServerLoader.extract_sample_values_for_column(
                cursor, f"{schema}.{table_name}", col_name
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
            schema: Schema owning the table
            table_name: Name of the table

        Returns:
            List of foreign key dictionaries
        """
        cursor.execute("""
            SELECT
                fk.name AS constraint_name,
                cp.name AS column_name,
                rt.name AS referenced_table_name,
                rs.name AS referenced_schema_name,
                cr.name AS referenced_column_name
            FROM sys.foreign_keys fk
            JOIN sys.foreign_key_columns fkc
                ON fk.object_id = fkc.constraint_object_id
            JOIN sys.columns cp
                ON fkc.parent_object_id = cp.object_id
                AND fkc.parent_column_id = cp.column_id
            JOIN sys.tables rt
                ON fkc.referenced_object_id = rt.object_id
            JOIN sys.schemas rs ON rt.schema_id = rs.schema_id
            JOIN sys.columns cr
                ON fkc.referenced_object_id = cr.object_id
                AND fkc.referenced_column_id = cr.column_id
            JOIN sys.tables pt
                ON fkc.parent_object_id = pt.object_id
            JOIN sys.schemas ps ON pt.schema_id = ps.schema_id
            WHERE ps.name = %s AND pt.name = %s
            ORDER BY fk.name;
        """, (schema, table_name))

        foreign_keys = []
        for fk_info in cursor.fetchall():
            foreign_keys.append({
                'constraint_name': fk_info['constraint_name'],
                'column': fk_info['column_name'],
                'referenced_table': fk_info['referenced_table_name'],
                'referenced_column': fk_info['referenced_column_name']
            })

        return foreign_keys

    @staticmethod
    def extract_relationships(
        cursor, schema: str = DEFAULT_SCHEMA
    ) -> Dict[str, List[Dict[str, str]]]:
        """
        Extract all relationship information from a schema.

        Only foreign keys whose parent *and* referenced tables both live in
        *schema* are returned, so relationships always point at entities that
        were actually loaded.

        Args:
            cursor: Database cursor
            schema: Schema to extract relationships from (default: ``dbo``)

        Returns:
            Dict containing relationship information
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

        relationships: Dict[str, List[Dict[str, str]]] = {}
        for rel_info in cursor.fetchall():
            constraint_name = rel_info['constraint_name']

            if constraint_name not in relationships:
                relationships[constraint_name] = []

            relationships[constraint_name].append({
                'from': rel_info['table_name'],
                'to': rel_info['referenced_table_name'],
                'source_column': rel_info['column_name'],
                'target_column': rel_info['referenced_column_name'],
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

            # Clear existing graph data
            # Drop current graph before reloading
            graph = resolve_db(db).select_graph(graph_id)
            await graph.delete()

            # Extract prefix from graph_id (remove database name part)
            # graph_id format is typically "prefix_database_name"
            parts = graph_id.split('_')
            if len(parts) >= 2:
                # Reconstruct prefix by joining all parts except the last one
                prefix = '_'.join(parts[:-1])
            else:
                prefix = graph_id

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
            conn = pymssql.connect(**conn_params)  # pylint: disable=no-member
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
