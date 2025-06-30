from typing import Tuple, Dict, Any, List
import psycopg2
import tqdm
from api.loaders.base_loader import BaseLoader
from api.loaders.graph_loader import load_to_graph


class PostgresLoader(BaseLoader):
    """
    Loader for PostgreSQL databases that connects and extracts schema information.
    """

    @staticmethod
    def load(connection_url: str) -> Tuple[bool, str]:
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
            entities = PostgresLoader.extract_tables_info(cursor)
            
            # Get all relationship information
            relationships = PostgresLoader.extract_relationships(cursor)
            
            # Close database connection
            cursor.close()
            conn.close()
            
            # Load data into graph
            load_to_graph(db_name, entities, relationships, db_name=db_name)
            
            return True, f"PostgreSQL schema loaded successfully. Found {len(entities)} tables."
            
        except psycopg2.Error as e:
            return False, f"PostgreSQL connection error: {str(e)}"
        except Exception as e:
            return False, f"Error loading PostgreSQL schema: {str(e)}"

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
            
            columns_info[col_name] = {
                'type': data_type,
                'null': is_nullable,
                'key': key_type,
                'description': ' '.join(description_parts),
                'default': column_default
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
        for table_name, constraint_name, column_name, foreign_table, foreign_column in cursor.fetchall():
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
