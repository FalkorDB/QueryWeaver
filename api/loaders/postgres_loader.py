"""PostgreSQL loader for loading database schemas into FalkorDB graphs."""

import re
import datetime
import decimal
import logging
from typing import AsyncGenerator, Dict, Any, List, Tuple

import psycopg2
from psycopg2 import sql
import tqdm

from api.loaders.base_loader import BaseLoader  # pylint: disable=import-error
from api.loaders.graph_loader import load_to_graph  # pylint: disable=import-error

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class PostgreSQLQueryError(Exception):
    """Exception raised when PostgreSQL query execution fails."""


class PostgreSQLConnectionError(Exception):
    """Exception raised when PostgreSQL connection fails."""


class PostgresLoader(BaseLoader):
    """
    Loader for PostgreSQL databases that connects and extracts schema information.
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
        PostgreSQL implementation using ORDER BY RANDOM() for random sampling.
        """
        query = sql.SQL("""
            SELECT {col}
            FROM (
                SELECT DISTINCT {col}
                FROM {table}
                WHERE {col} IS NOT NULL
            ) AS distinct_vals
            ORDER BY RANDOM()
            LIMIT %s;
        """).format(
            col=sql.Identifier(col_name),
            table=sql.Identifier(table_name)
        )
        cursor.execute(query, (sample_size,))
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
        if value is None:
            return None
        return value

    @staticmethod
    async def load(prefix: str, connection_url: str) -> AsyncGenerator[tuple[bool, str], None]:
        """
        Load the graph data from a PostgreSQL database into the graph database.

        Args:
            connection_url: PostgreSQL connection URL in format:
                          postgresql://username:password@host:port/database

        Returns:
            Tuple[bool, str]: Success status and message
        """
        try:
            # Connect to PostgreSQL database
            conn = psycopg2.connect(connection_url)
            cursor = conn.cursor()

            # Extract database name from connection URL
            db_name = connection_url.split('/')[-1]
            if '?' in db_name:
                db_name = db_name.split('?')[0]

            # Get all table information
            yield True, "Extracting table information..."
            entities = PostgresLoader.extract_tables_info(cursor)

            yield True, "Extracting relationship information..."
            # Get all relationship information
            relationships = PostgresLoader.extract_relationships(cursor)

            # Close database connection
            cursor.close()
            conn.close()

            yield True, "Loading data into graph..."
            # Load data into graph
            await load_to_graph(f"{prefix}_{db_name}", entities, relationships,
                         db_name=db_name, db_url=connection_url)

            yield True, (f"PostgreSQL schema loaded successfully. "
                         f"Found {len(entities)} tables.")

        except psycopg2.Error as e:
            logging.error("PostgreSQL connection error: %s", e)
            yield False, "Failed to connect to PostgreSQL database"
        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.error("Error loading PostgreSQL schema: %s", e)
            yield False, "Failed to load PostgreSQL database schema"

    @staticmethod
    def extract_tables_info(cursor) -> Dict[str, Any]:
        """
        Extract table and column information from PostgreSQL database.

        Args:
            cursor: Database cursor

        Returns:
            Dict containing table information
        """
        entities = {}

        # Get all tables in public schema
        cursor.execute("""
            SELECT table_name, table_comment
            FROM information_schema.tables t
            LEFT JOIN (
                SELECT schemaname, tablename, description as table_comment
                FROM pg_tables pt
                JOIN pg_class pc ON pc.relname = pt.tablename
                JOIN pg_description pd ON pd.objoid = pc.oid AND pd.objsubid = 0
                WHERE pt.schemaname = 'public'
            ) tc ON tc.tablename = t.table_name
            WHERE t.table_schema = 'public'
            AND t.table_type = 'BASE TABLE'
            ORDER BY t.table_name;
        """)

        tables = cursor.fetchall()

        for table_name, table_comment in tqdm.tqdm(tables, desc="Extracting table information"):
            table_name = table_name.strip()

            # Get column information for this table
            columns_info = PostgresLoader.extract_columns_info(cursor, table_name)

            # Get foreign keys for this table
            foreign_keys = PostgresLoader.extract_foreign_keys(cursor, table_name)

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
    def extract_columns_info(cursor, table_name: str) -> Dict[str, Any]:
        """
        Extract column information for a specific table.

        Args:
            cursor: Database cursor
            table_name: Name of the table

        Returns:
            Dict containing column information
        """
        cursor.execute("""
            SELECT
                c.column_name,
                c.data_type,
                c.is_nullable,
                c.column_default,
                CASE
                    WHEN pk.column_name IS NOT NULL THEN 'PRIMARY KEY'
                    WHEN fk.column_name IS NOT NULL THEN 'FOREIGN KEY'
                    ELSE 'NONE'
                END as key_type,
                COALESCE(pgd.description, '') as column_comment
            FROM information_schema.columns c
            LEFT JOIN (
                SELECT ku.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage ku
                    ON tc.constraint_name = ku.constraint_name
                WHERE tc.table_name = %s
                AND tc.constraint_type = 'PRIMARY KEY'
            ) pk ON pk.column_name = c.column_name
            LEFT JOIN (
                SELECT ku.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage ku
                    ON tc.constraint_name = ku.constraint_name
                WHERE tc.table_name = %s
                AND tc.constraint_type = 'FOREIGN KEY'
            ) fk ON fk.column_name = c.column_name
            LEFT JOIN pg_class pc ON pc.relname = c.table_name
            LEFT JOIN pg_attribute pa ON pa.attrelid = pc.oid AND pa.attname = c.column_name
            LEFT JOIN pg_description pgd ON pgd.objoid = pc.oid AND pgd.objsubid = pa.attnum
            WHERE c.table_name = %s
            AND c.table_schema = 'public'
            ORDER BY c.ordinal_position;
        """, (table_name, table_name, table_name))

        columns = cursor.fetchall()
        columns_info = {}

        for col_name, data_type, is_nullable, column_default, key_type, column_comment in columns:
            col_name = col_name.strip()

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

            if column_default:
                description_parts.append(f"(Default: {column_default})")

            # Extract sample values for the column (stored separately, not in description)
            sample_values = PostgresLoader.extract_sample_values_for_column(
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
    def extract_foreign_keys(cursor, table_name: str) -> List[Dict[str, str]]:
        """
        Extract foreign key information for a specific table.

        Args:
            cursor: Database cursor
            table_name: Name of the table

        Returns:
            List of foreign key dictionaries
        """
        cursor.execute("""
            SELECT
                tc.constraint_name,
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
                AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_name = %s
            AND tc.table_schema = 'public';
        """, (table_name,))

        foreign_keys = []
        for constraint_name, column_name, foreign_table, foreign_column in cursor.fetchall():
            foreign_keys.append({
                'constraint_name': constraint_name.strip(),
                'column': column_name.strip(),
                'referenced_table': foreign_table.strip(),
                'referenced_column': foreign_column.strip()
            })

        return foreign_keys

    @staticmethod
    def extract_relationships(cursor) -> Dict[str, List[Dict[str, str]]]:
        """
        Extract all relationship information from the database.

        Args:
            cursor: Database cursor

        Returns:
            Dict containing relationship information
        """
        cursor.execute("""
            SELECT
                tc.table_name,
                tc.constraint_name,
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
                AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_schema = 'public'
            ORDER BY tc.table_name, tc.constraint_name;
        """)

        relationships = {}
        for (table_name, constraint_name, column_name,
             foreign_table, foreign_column) in cursor.fetchall():
            table_name = table_name.strip()
            constraint_name = constraint_name.strip()

            if constraint_name not in relationships:
                relationships[constraint_name] = []

            relationships[constraint_name].append({
                'from': table_name,
                'to': foreign_table.strip(),
                'source_column': column_name.strip(),
                'target_column': foreign_column.strip(),
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
        if first_word in PostgresLoader.SCHEMA_MODIFYING_OPERATIONS:
            # Additional pattern matching for more precise detection
            for pattern in PostgresLoader.SCHEMA_PATTERNS:
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
            success, message = await PostgresLoader.load(prefix, db_url)

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
        Execute a SQL query on the PostgreSQL database and return the results.

        Args:
            sql_query: The SQL query to execute
            db_url: PostgreSQL connection URL in format:
                    postgresql://username:password@host:port/database

        Returns:
            List of dictionaries containing the query results
        """
        try:
            # Connect to PostgreSQL database
            conn = psycopg2.connect(db_url)
            cursor = conn.cursor()

            # Execute the SQL query
            cursor.execute(sql_query)

            # Check if the query returns results (SELECT queries)
            if cursor.description is not None:
                # This is a SELECT query or similar that returns rows
                columns = [desc[0] for desc in cursor.description]
                results = cursor.fetchall()
                result_list = []
                for row in results:
                    # Serialize each value to ensure JSON compatibility
                    serialized_row = {
                        columns[i]: PostgresLoader._serialize_value(row[i])
                        for i in range(len(columns))
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

        except psycopg2.Error as e:
            # Rollback in case of error
            if 'conn' in locals():
                conn.rollback()
                cursor.close()
                conn.close()
            raise PostgreSQLConnectionError(f"PostgreSQL query execution error: {str(e)}") from e
        except Exception as e:
            # Rollback in case of error
            if 'conn' in locals():
                conn.rollback()
                cursor.close()
                conn.close()
            raise PostgreSQLQueryError(f"Error executing SQL query: {str(e)}") from e
