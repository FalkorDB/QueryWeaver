"""Snowflake loader for loading database schemas into FalkorDB graphs."""

import base64
import datetime
import decimal
import logging
import re
from typing import AsyncGenerator, Dict, Any, List, Tuple
from urllib.parse import urlparse, parse_qs

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

import tqdm
import snowflake.connector
from snowflake.connector import DictCursor

from api.config import Config
from api.loaders.base_loader import BaseLoader
from api.loaders.graph_loader import load_to_graph


class SnowflakeQueryError(Exception):
    """Exception raised for Snowflake query execution errors."""


class SnowflakeConnectionError(Exception):
    """Exception raised for Snowflake connection errors."""


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class SnowflakeLoader(BaseLoader):
    """
    Loader for Snowflake databases that connects and extracts schema information.
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
        r'^\s*CREATE\s+DATABASE',
        r'^\s*DROP\s+DATABASE',
        r'^\s*CREATE\s+SCHEMA',
        r'^\s*DROP\s+SCHEMA',
    ]

    @staticmethod
    def _validate_identifier(identifier: str, identifier_type: str = "identifier") -> None:
        """
        Validate that an identifier (table, column, database, schema name) is safe.

        Args:
            identifier: The identifier to validate
            identifier_type: Type of identifier for error messages

        Raises:
            ValueError: If identifier contains invalid characters
        """
        # Allow alphanumeric, underscore, dollar sign, and limit to reasonable length
        # Snowflake identifiers can contain these characters when quoted
        if not re.match(r'^[A-Za-z0-9_$]+$', identifier):
            raise ValueError(
                f"Invalid {identifier_type}: {identifier!r}. "
                "Only alphanumeric characters, underscore, and dollar sign are allowed."
            )
        if len(identifier) > 255:
            raise ValueError(f"Invalid {identifier_type}: exceeds maximum length of 255")

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        """
        Safely quote a Snowflake identifier by escaping double quotes.

        Args:
            identifier: The identifier to quote

        Returns:
            Quoted identifier safe for SQL interpolation
        """
        # Escape any existing double quotes by doubling them
        escaped = identifier.replace('"', '""')
        return f'"{escaped}"'

    @staticmethod
    def _execute_sample_query(
        cursor, table_name: str, col_name: str, sample_size: int = 3
    ) -> List[Any]:
        """
        Execute query to get random sample values for a column.
        Snowflake implementation using SAMPLE for random sampling.
        """
        # Validate identifiers to prevent SQL injection
        SnowflakeLoader._validate_identifier(table_name, "table name")
        SnowflakeLoader._validate_identifier(col_name, "column name")

        # Validate sample_size is a positive integer
        if not isinstance(sample_size, int) or sample_size <= 0:
            raise ValueError(f"sample_size must be a positive integer, got {sample_size!r}")

        # Quote identifiers safely
        quoted_table = SnowflakeLoader._quote_identifier(table_name)
        quoted_col = SnowflakeLoader._quote_identifier(col_name)

        # Oversample by 10x to increase the chance of getting sample_size
        # distinct non-null values after filtering (Snowflake's SAMPLE clause
        # returns approximate row counts, and rows may contain NULLs or duplicates)
        sample_rows = sample_size * 10

        query = f"""
            SELECT DISTINCT {quoted_col}
            FROM {quoted_table} SAMPLE ({sample_rows} ROWS)
            WHERE {quoted_col} IS NOT NULL
            LIMIT %s;
        """
        cursor.execute(query, (sample_size,))

        sample_results = cursor.fetchall()
        # DictCursor returns dicts; extract the column value by name
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
        if value is None:
            return None
        return value

    @staticmethod
    def _parse_snowflake_url(connection_url: str) -> Dict[str, Any]:  # pylint: disable=too-many-locals
        """
        Parse Snowflake connection URL into components.

        Supports two authentication modes:
          - Password: snowflake://user:pass@account/db/schema?warehouse=WH
          - Key-pair: snowflake://user@account/db/schema?warehouse=WH&private_key=BASE64_PEM
            (optionally with &private_key_passphrase=PASSPHRASE)

        Args:
            connection_url: Snowflake connection URL

        Returns:
            Dict with connection parameters for snowflake.connector.connect()
        """
        if not connection_url.startswith('snowflake://'):
            raise ValueError(
                "Invalid Snowflake URL format. Expected "
                "snowflake://username:password@account/database/schema?warehouse=warehouse_name"
            )

        parsed = urlparse(connection_url)

        if not parsed.username:
            raise ValueError("Snowflake URL must include username")

        username = parsed.username
        password = parsed.password or ""

        if not parsed.hostname:
            raise ValueError("Snowflake URL must include account")
        account = parsed.hostname

        path_parts = [p for p in parsed.path.split('/') if p]
        if len(path_parts) < 1:
            raise ValueError("Snowflake URL must include database name")

        database = path_parts[0]
        schema = path_parts[1] if len(path_parts) > 1 else "PUBLIC"

        query_params = parse_qs(parsed.query)
        warehouse = query_params.get('warehouse', ['COMPUTE_WH'])[0]

        # Validate all identifiers
        SnowflakeLoader._validate_identifier(database, "database")
        SnowflakeLoader._validate_identifier(schema, "schema")
        SnowflakeLoader._validate_identifier(warehouse, "warehouse")

        conn_params: Dict[str, Any] = {
            'user': username,
            'account': account,
            'database': database,
            'schema': schema,
            'warehouse': warehouse,
            'login_timeout': 30,
            'network_timeout': 60,
        }

        # Check for key-pair authentication
        private_key_b64 = query_params.get('private_key', [None])[0]
        if private_key_b64:
            passphrase = query_params.get('private_key_passphrase', [None])[0]
            passphrase_bytes = passphrase.encode() if passphrase else None

            try:
                # Handle both standard and URL-safe base64 (browsers may
                # convert '+' to spaces when URL-encoding query params)
                cleaned_b64 = private_key_b64.replace(' ', '+')
                pem_bytes = base64.b64decode(cleaned_b64)
                private_key = serialization.load_pem_private_key(
                    pem_bytes,
                    password=passphrase_bytes,
                    backend=default_backend(),
                )
                conn_params['private_key'] = private_key.private_bytes(
                    encoding=serialization.Encoding.DER,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            except Exception as e:
                raise ValueError(f"Failed to load private key: {e}") from e
        else:
            conn_params['password'] = password

        return conn_params

    @staticmethod
    async def load(prefix: str, connection_url: str) -> AsyncGenerator[
        tuple[bool, str], None
    ]:
        """
        Load the graph data from a Snowflake database into the graph database.

        Args:
            connection_url: Snowflake connection URL in format:
              snowflake://username:password@account/database/schema?warehouse=warehouse_name

        Returns:
            Tuple[bool, str]: Success status and message
        """
        try:
            # Parse connection URL
            conn_params = SnowflakeLoader._parse_snowflake_url(connection_url)

            # Connect to Snowflake database
            conn = snowflake.connector.connect(**conn_params)
            cursor = conn.cursor(DictCursor)

            # Get database and schema name
            db_name = conn_params['database']
            # Snowflake stores unquoted identifiers in UPPERCASE;
            # INFORMATION_SCHEMA lookups require the canonical form.
            schema_name = conn_params['schema'].upper()

            # Get all table information
            yield True, "Extracting table information..."
            entities = SnowflakeLoader.extract_tables_info(cursor, db_name, schema_name)

            # Get all relationship information
            yield True, "Extracting relationship information..."
            relationships = SnowflakeLoader.extract_relationships(cursor, db_name, schema_name)

            # Close database connection
            cursor.close()
            conn.close()

            # Load data into graph
            yield True, "Loading data into graph..."
            await load_to_graph(f"{prefix}_{db_name}", entities, relationships,
                         db_name=db_name, db_url=connection_url)

            yield True, (f"Snowflake schema loaded successfully. "
                         f"Found {len(entities)} tables.")

        except snowflake.connector.Error as e:
            logging.error("Snowflake error: %s", e)
            yield False, f"Snowflake error: {e}"
        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.error("Error loading Snowflake schema: %s", e)
            yield False, f"Failed to load Snowflake database schema: {e}"

    @staticmethod
    def extract_tables_info(cursor, db_name: str, schema_name: str) -> Dict[str, Any]:
        """
        Extract table and column information from Snowflake database.

        Args:
            cursor: Database cursor
            db_name: Database name
            schema_name: Schema name

        Returns:
            Dict containing table information
        """
        # Validate identifiers to prevent SQL injection
        SnowflakeLoader._validate_identifier(db_name, "database name")
        SnowflakeLoader._validate_identifier(schema_name, "schema name")

        entities = {}

        # Get all tables in the schema
        # Use quoted identifiers for database name, parameterize schema_name
        quoted_db = SnowflakeLoader._quote_identifier(db_name)
        cursor.execute(f"""
            SELECT TABLE_NAME, COMMENT
            FROM {quoted_db}.INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = %s
            AND TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_NAME;
        """, (schema_name,))

        tables = cursor.fetchall()

        for table_info in tqdm.tqdm(tables, desc="Extracting table information"):
            table_name = table_info['TABLE_NAME']
            table_comment = table_info['COMMENT']

            # Get column information for this table
            columns_info = SnowflakeLoader.extract_columns_info(
                cursor, db_name, schema_name, table_name
            )

            # Get foreign keys for this table
            foreign_keys = SnowflakeLoader.extract_foreign_keys(
                cursor, db_name, schema_name, table_name
            )

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
    def extract_columns_info(  # pylint: disable=too-many-locals
        cursor, db_name: str, schema_name: str, table_name: str
    ) -> Dict[str, Any]:
        """
        Extract column information for a specific table.

        Args:
            cursor: Database cursor
            db_name: Database name
            schema_name: Schema name
            table_name: Name of the table

        Returns:
            Dict containing column information
        """
        # Validate identifiers to prevent SQL injection
        SnowflakeLoader._validate_identifier(db_name, "database name")
        SnowflakeLoader._validate_identifier(schema_name, "schema name")
        SnowflakeLoader._validate_identifier(table_name, "table name")

        quoted_db = SnowflakeLoader._quote_identifier(db_name)

        cursor.execute(f"""
            SELECT
                COLUMN_NAME,
                DATA_TYPE,
                IS_NULLABLE,
                COLUMN_DEFAULT,
                COMMENT
            FROM {quoted_db}.INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s
            AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION;
        """, (schema_name, table_name))

        columns = cursor.fetchall()
        columns_info = {}

        # Get primary key information using Snowflake's SHOW command
        quoted_table = SnowflakeLoader._quote_identifier(table_name)
        quoted_schema = SnowflakeLoader._quote_identifier(schema_name)
        cursor.execute(f"SHOW PRIMARY KEYS IN TABLE {quoted_db}.{quoted_schema}.{quoted_table}")
        primary_keys = {row['column_name'] for row in cursor.fetchall()}

        # Get foreign key columns using Snowflake's SHOW IMPORTED KEYS
        cursor.execute(f"SHOW IMPORTED KEYS IN TABLE {quoted_db}.{quoted_schema}.{quoted_table}")
        foreign_keys_cols = {row['fk_column_name'] for row in cursor.fetchall()}

        for col_info in columns:
            col_name = col_info['COLUMN_NAME']
            data_type = col_info['DATA_TYPE']
            is_nullable = col_info['IS_NULLABLE']
            column_default = col_info['COLUMN_DEFAULT']
            column_comment = col_info['COMMENT']

            # Determine key type
            if col_name in primary_keys:
                key_type = 'PRIMARY KEY'
            elif col_name in foreign_keys_cols:
                key_type = 'FOREIGN KEY'
            else:
                key_type = 'NONE'

            # Generate column description
            description_parts = []
            if column_comment:
                description_parts.append(column_comment)
            else:
                description_parts.append(f"Column {col_name} of type {data_type}")

            if key_type != 'NONE':
                description_parts.append(f"({key_type})")

            if is_nullable == 'NO':
                description_parts.append("(NOT NULL)")

            if column_default is not None:
                description_parts.append(f"(Default: {column_default})")

            # Extract sample values for the column (stored separately, not in description)
            sample_values = SnowflakeLoader.extract_sample_values_for_column(
                cursor, table_name, col_name
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
    def extract_foreign_keys(
        cursor, db_name: str, schema_name: str, table_name: str
    ) -> List[Dict[str, str]]:
        """
        Extract foreign key information for a specific table.

        Args:
            cursor: Database cursor
            db_name: Database name
            schema_name: Schema name
            table_name: Name of the table

        Returns:
            List of foreign key dictionaries
        """
        # Validate identifiers to prevent SQL injection
        SnowflakeLoader._validate_identifier(db_name, "database name")
        SnowflakeLoader._validate_identifier(schema_name, "schema name")
        SnowflakeLoader._validate_identifier(table_name, "table name")

        quoted_db = SnowflakeLoader._quote_identifier(db_name)
        quoted_schema = SnowflakeLoader._quote_identifier(schema_name)
        quoted_table = SnowflakeLoader._quote_identifier(table_name)

        # Use Snowflake's SHOW IMPORTED KEYS for foreign key information
        cursor.execute(f"SHOW IMPORTED KEYS IN TABLE {quoted_db}.{quoted_schema}.{quoted_table}")

        foreign_keys = []
        for fk_info in cursor.fetchall():
            foreign_keys.append({
                'constraint_name': fk_info['fk_name'],
                'column': fk_info['fk_column_name'],
                'referenced_table': fk_info['pk_table_name'],
                'referenced_column': fk_info['pk_column_name']
            })

        return foreign_keys

    @staticmethod
    def extract_relationships(
        cursor, db_name: str, schema_name: str
    ) -> Dict[str, List[Dict[str, str]]]:
        """
        Extract all relationship information from the database.

        Args:
            cursor: Database cursor
            db_name: Database name
            schema_name: Schema name

        Returns:
            Dict containing relationship information
        """
        # Validate identifiers to prevent SQL injection
        SnowflakeLoader._validate_identifier(db_name, "database name")
        SnowflakeLoader._validate_identifier(schema_name, "schema name")

        quoted_db = SnowflakeLoader._quote_identifier(db_name)
        quoted_schema = SnowflakeLoader._quote_identifier(schema_name)

        # Use Snowflake's SHOW IMPORTED KEYS for each table to get relationships
        cursor.execute(f"""
            SELECT TABLE_NAME
            FROM {quoted_db}.INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = %s
            AND TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_NAME;
        """, (schema_name,))
        tables = [row['TABLE_NAME'] for row in cursor.fetchall()]

        relationships = {}
        for tbl in tables:
            SnowflakeLoader._validate_identifier(tbl, "table name")
            quoted_table = SnowflakeLoader._quote_identifier(tbl)
            cursor.execute(
                f"SHOW IMPORTED KEYS IN TABLE {quoted_db}.{quoted_schema}.{quoted_table}"
            )
            for rel_info in cursor.fetchall():
                constraint_name = rel_info['fk_name']

                if constraint_name not in relationships:
                    relationships[constraint_name] = []

                relationships[constraint_name].append({
                    'from': rel_info['fk_table_name'],
                    'to': rel_info['pk_table_name'],
                    'source_column': rel_info['fk_column_name'],
                    'target_column': rel_info['pk_column_name'],
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
        if first_word in SnowflakeLoader.SCHEMA_MODIFYING_OPERATIONS:
            # Additional pattern matching for more precise detection
            for pattern in SnowflakeLoader.SCHEMA_PATTERNS:
                if re.match(pattern, normalized_query, re.IGNORECASE):
                    return True, first_word

            # If it's a known DDL operation but doesn't match specific patterns,
            # still consider it schema-modifying (better safe than sorry)
            return True, first_word

        return False, ""

    @staticmethod
    async def refresh_graph_schema(graph_id: str, db_url: str) -> Tuple[bool, str]:
        """
        Refresh the graph schema by clearing existing data and reloading from the database.

        Args:
            graph_id: The graph ID to refresh
            db_url: Database connection URL

        Returns:
            Tuple of (success, message)
        """
        try:
            logging.info("Schema modification detected. Refreshing graph schema.")

            # Import here to avoid circular imports
            from api.extensions import db  # pylint: disable=import-error,import-outside-toplevel

            # Clear existing graph data
            # Drop current graph before reloading
            graph = db.select_graph(graph_id)
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
            success = False
            message = ""
            async for progress_tuple in SnowflakeLoader.load(prefix, db_url):
                success, message = progress_tuple

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
        Execute a SQL query on the Snowflake database and return the results.

        Args:
            sql_query: The SQL query to execute
            db_url: Snowflake connection URL in format:
                    snowflake://username:password@account/database/schema?warehouse=warehouse_name

        Returns:
            List of dictionaries containing the query results
        """
        try:
            # Parse connection URL
            conn_params = SnowflakeLoader._parse_snowflake_url(db_url)

            # Bound login, network waits and server-side statement runtime.
            # ``_parse_snowflake_url`` hardcodes login_timeout/network_timeout,
            # so these must be assigned — setdefault would be a no-op and the
            # configured values would never apply.
            conn_params["login_timeout"] = Config.DB_CONNECT_TIMEOUT
            conn_params["network_timeout"] = Config.DB_STATEMENT_TIMEOUT
            session_parameters = dict(conn_params.get("session_parameters") or {})
            session_parameters.setdefault(
                "STATEMENT_TIMEOUT_IN_SECONDS", Config.DB_STATEMENT_TIMEOUT
            )
            conn_params["session_parameters"] = session_parameters

            # Connect to Snowflake database
            conn = snowflake.connector.connect(**conn_params)
            cursor = conn.cursor(DictCursor)

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
                        key: SnowflakeLoader._serialize_value(value)
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

            # Close database connection
            cursor.close()
            conn.close()

            return result_list

        except snowflake.connector.Error as e:
            # Rollback in case of error
            if 'conn' in locals():
                conn.rollback()
                cursor.close()
                conn.close()
            logging.error("Snowflake query execution error: %s", e)
            raise SnowflakeQueryError(f"Snowflake query execution error: {str(e)}") from e
        except Exception as e:
            # Rollback in case of error
            if 'conn' in locals():
                conn.rollback()
                cursor.close()
                conn.close()
            logging.error("Error executing SQL query: %s", e)
            raise SnowflakeQueryError(f"Error executing SQL query: {str(e)}") from e
