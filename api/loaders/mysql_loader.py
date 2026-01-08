"""MySQL loader for loading database schemas into FalkorDB graphs."""

import datetime
import decimal
import logging
import re
from typing import AsyncGenerator, Dict, Any, List, Tuple

import tqdm
import pymysql
from pymysql.cursors import DictCursor


from api.loaders.base_loader import BaseLoader
from api.loaders.graph_loader import load_to_graph


class MySQLQueryError(Exception):
    """Exception raised for MySQL query execution errors."""


class MySQLConnectionError(Exception):
    """Exception raised for MySQL connection errors."""

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class MySQLLoader(BaseLoader):
    """
    Loader for MySQL databases that connects and extracts schema information.
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
    def _execute_sample_query(
        cursor, table_name: str, col_name: str, sample_size: int = 3
    ) -> List[Any]:
        """
        Execute query to get random sample values for a column.
        MySQL implementation using ORDER BY RAND() for random sampling.
        """
        query = f"""
            SELECT DISTINCT `{col_name}`
            FROM `{table_name}`
            WHERE `{col_name}` IS NOT NULL
            ORDER BY RAND()
            LIMIT %s;
        """
        cursor.execute(query, (sample_size,))

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
        if value is None:
            return None
        return value

    @staticmethod
    def _parse_mysql_url(connection_url: str) -> Dict[str, str]:
        """
        Parse MySQL connection URL into components.

        Args:
            connection_url: MySQL connection URL in format:
                          mysql://username:password@host:port/database

        Returns:
            Dict with connection parameters
        """
        # Remove mysql:// prefix
        if connection_url.startswith('mysql://'):
            url = connection_url[8:]
        else:
            raise ValueError(
                "Invalid MySQL URL format. Expected "
                "mysql://username:password@host:port/database"
            )

        # Parse components
        if '@' not in url:
            raise ValueError("MySQL URL must include username and host")

        credentials, host_db = url.split('@', 1)

        if ':' in credentials:
            username, password = credentials.split(':', 1)
        else:
            username = credentials
            password = ""

        if '/' not in host_db:
            raise ValueError("MySQL URL must include database name")

        host_port, database = host_db.split('/', 1)

        # Handle query parameters
        if '?' in database:
            database = database.split('?')[0]

        if ':' in host_port:
            host, port = host_port.split(':', 1)
            port = int(port)
        else:
            host = host_port
            port = 3306

        return {
            'host': host,
            'port': port,
            'user': username,
            'password': password,
            'database': database
        }

    @staticmethod
    async def load(prefix: str, connection_url: str) -> AsyncGenerator[tuple[bool, str], None]:
        """
        Load the graph data from a MySQL database into the graph database.

        Args:
            connection_url: MySQL connection URL in format:
                          mysql://username:password@host:port/database

        Returns:
            Tuple[bool, str]: Success status and message
        """
        try:
            # Parse connection URL
            conn_params = MySQLLoader._parse_mysql_url(connection_url)

            # Connect to MySQL database
            conn = pymysql.connect(**conn_params)
            cursor = conn.cursor(DictCursor)

            # Get database name
            db_name = conn_params['database']

            # Get all table information
            yield True, "Extracting table information..."
            entities = MySQLLoader.extract_tables_info(cursor, db_name)

            # Get all relationship information
            yield True, "Extracting relationship information..."
            relationships = MySQLLoader.extract_relationships(cursor, db_name)

            # Close database connection
            cursor.close()
            conn.close()

            # Load data into graph
            yield True, "Loading data into graph..."
            await load_to_graph(f"{prefix}_{db_name}", entities, relationships,
                         db_name=db_name, db_url=connection_url)

            yield True, (f"MySQL schema loaded successfully. "
                         f"Found {len(entities)} tables.")

        except pymysql.MySQLError as e:
            logging.error("MySQL connection error: %s", e)
            yield False, "Failed to connect to MySQL database"
        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.error("Error loading MySQL schema: %s", e)
            yield False, "Failed to load MySQL database schema"

    @staticmethod
    def extract_tables_info(cursor, db_name: str) -> Dict[str, Any]:
        """
        Extract table and column information from MySQL database.

        Args:
            cursor: Database cursor
            db_name: Database name

        Returns:
            Dict containing table information
        """
        entities = {}

        # Get all tables in the database
        cursor.execute("""
            SELECT table_name, table_comment
            FROM information_schema.tables
            WHERE table_schema = %s
            AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        """, (db_name,))

        tables = cursor.fetchall()

        for table_info in tqdm.tqdm(tables, desc="Extracting table information"):
            table_name = table_info['TABLE_NAME']
            table_comment = table_info['TABLE_COMMENT']

            # Get column information for this table
            columns_info = MySQLLoader.extract_columns_info(cursor, db_name, table_name)

            # Get foreign keys for this table
            foreign_keys = MySQLLoader.extract_foreign_keys(cursor, db_name, table_name)

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
    def extract_columns_info(cursor, db_name: str, table_name: str) -> Dict[str, Any]:
        """
        Extract column information for a specific table.

        Args:
            cursor: Database cursor
            db_name: Database name
            table_name: Name of the table

        Returns:
            Dict containing column information
        """
        cursor.execute("""
            SELECT
                column_name,
                data_type,
                is_nullable,
                column_default,
                column_key,
                column_comment
            FROM information_schema.columns
            WHERE table_schema = %s
            AND table_name = %s
            ORDER BY ordinal_position;
        """, (db_name, table_name))

        columns = cursor.fetchall()
        columns_info = {}

        for col_info in columns:
            col_name = col_info['COLUMN_NAME']
            data_type = col_info['DATA_TYPE']
            is_nullable = col_info['IS_NULLABLE']
            column_default = col_info['COLUMN_DEFAULT']
            column_key = col_info['COLUMN_KEY']
            column_comment = col_info['COLUMN_COMMENT']

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
            sample_values = MySQLLoader.extract_sample_values_for_column(
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
    def extract_foreign_keys(cursor, db_name: str, table_name: str) -> List[Dict[str, str]]:
        """
        Extract foreign key information for a specific table.

        Args:
            cursor: Database cursor
            db_name: Database name
            table_name: Name of the table

        Returns:
            List of foreign key dictionaries
        """
        cursor.execute("""
            SELECT
                constraint_name,
                column_name,
                referenced_table_name,
                referenced_column_name
            FROM information_schema.key_column_usage
            WHERE table_schema = %s
            AND table_name = %s
            AND referenced_table_name IS NOT NULL
            ORDER BY constraint_name, ordinal_position;
        """, (db_name, table_name))

        foreign_keys = []
        for fk_info in cursor.fetchall():
            foreign_keys.append({
                'constraint_name': fk_info['CONSTRAINT_NAME'],
                'column': fk_info['COLUMN_NAME'],
                'referenced_table': fk_info['REFERENCED_TABLE_NAME'],
                'referenced_column': fk_info['REFERENCED_COLUMN_NAME']
            })

        return foreign_keys

    @staticmethod
    def extract_relationships(cursor, db_name: str) -> Dict[str, List[Dict[str, str]]]:
        """
        Extract all relationship information from the database.

        Args:
            cursor: Database cursor
            db_name: Database name

        Returns:
            Dict containing relationship information
        """
        cursor.execute("""
            SELECT
                table_name,
                constraint_name,
                column_name,
                referenced_table_name,
                referenced_column_name
            FROM information_schema.key_column_usage
            WHERE table_schema = %s
            AND referenced_table_name IS NOT NULL
            ORDER BY table_name, constraint_name;
        """, (db_name,))

        relationships = {}
        for rel_info in cursor.fetchall():
            constraint_name = rel_info['CONSTRAINT_NAME']

            if constraint_name not in relationships:
                relationships[constraint_name] = []

            relationships[constraint_name].append({
                'from': rel_info['TABLE_NAME'],
                'to': rel_info['REFERENCED_TABLE_NAME'],
                'source_column': rel_info['COLUMN_NAME'],
                'target_column': rel_info['REFERENCED_COLUMN_NAME'],
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
        if first_word in MySQLLoader.SCHEMA_MODIFYING_OPERATIONS:
            # Additional pattern matching for more precise detection
            for pattern in MySQLLoader.SCHEMA_PATTERNS:
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
            success, message = await MySQLLoader.load(prefix, db_url)

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
        Execute a SQL query on the MySQL database and return the results.

        Args:
            sql_query: The SQL query to execute
            db_url: MySQL connection URL in format:
                    mysql://username:password@host:port/database

        Returns:
            List of dictionaries containing the query results
        """
        try:
            # Parse connection URL
            conn_params = MySQLLoader._parse_mysql_url(db_url)

            # Connect to MySQL database
            conn = pymysql.connect(**conn_params)
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
                        key: MySQLLoader._serialize_value(value)
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

        except pymysql.MySQLError as e:
            # Rollback in case of error
            if 'conn' in locals():
                conn.rollback()
                cursor.close()
                conn.close()
            logging.error("MySQL query execution error: %s", e)
            raise MySQLQueryError(f"MySQL query execution error: {str(e)}") from e
        except Exception as e:
            # Rollback in case of error
            if 'conn' in locals():
                conn.rollback()
                cursor.close()
                conn.close()
            logging.error("Error executing SQL query: %s", e)
            raise MySQLQueryError(f"Error executing SQL query: {str(e)}") from e
