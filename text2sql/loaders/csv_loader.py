from typing import Tuple, Dict, List
import io
import pandas as pd
import tqdm
from collections import defaultdict
from litellm import embedding
from text2sql.config import Config
from text2sql.loaders.base_loadr import BaseLoader
from text2sql.extensions import db


class CSVLoader(BaseLoader):

    @staticmethod
    def load(graph_id: str, data) -> Tuple[bool, str]:
        """
        Load the data dictionary CSV file into the graph database.
        
        Args:
            graph_id: The ID of the graph to load the data into
            data: CSV file
            
        Returns:
            Tuple of (success, message)
        """
        try:
            # Parse CSV data using pandas for better handling of large files
            df = pd.read_csv(io.StringIO(data), encoding='utf-8')

            # Check if required columns exist
            required_columns = ['Schema', 'Domain', 'Field', 'Type', 'Description', 'Related', 'Cardinality']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                return False, f"Missing required columns in CSV: {', '.join(missing_columns)}"
            
            # Get the graph
            graph = db.select_graph(graph_id)
            
            # Create vector indices
            graph.query("""
                CREATE VECTOR INDEX FOR (t:Table) ON (t.embedding) 
                OPTIONS {dimension:768, similarityFunction:'euclidean'}
            """)
            
            graph.query("""
                CREATE VECTOR INDEX FOR (c:Column) ON (c.embedding) 
                OPTIONS {dimension:768, similarityFunction:'euclidean'}
            """)
            
            # Process data by grouping by Schema and Domain to identify tables
            # Group by Schema and Domain to get tables
            tables = defaultdict(lambda: {
                'description': '',
                'columns': {},
                'relationships': []
            })
            
            # First pass: Organize data into tables
            for _, row in tqdm.tqdm(df.iterrows(), total=len(df), desc="Organizing data"):
                schema = row['Schema']
                domain = row['Domain']
                table_name = f"{schema}.{domain}"
                
                # Set table description (use Domain Description if available)
                if 'Domain Description' in row and not pd.isna(row['Domain Description']) and not tables[table_name]['description']:
                    tables[table_name]['description'] = row['Domain Description']
                
                # Add column information
                field = row['Field']
                if not pd.isna(field):
                    field_type = row['Type'] if not pd.isna(row['Type']) else 'STRING'
                    field_desc = row['Description'] if not pd.isna(row['Description']) else ''
                    nullable = True  # Default to nullable since we don't have explicit null info
                    
                    tables[table_name]['columns'][field] = {
                        'type': field_type,
                        'description': field_desc,
                        'null': nullable,
                        'key': 'PRI' if field.lower().endswith('_id') else '',  # Assumption: *_id fields are primary keys
                        'default': '',
                        'extra': ''
                    }
                
                # Add relationship information if available
                if not pd.isna(row['Related']) and not pd.isna(row['Cardinality']):
                    source_field = field
                    target_table = row['Related']
                    cardinality = row['Cardinality']
                    
                    # Assuming the related field is the first part of the related table name
                    if '.' in target_table:
                        schema_domain = target_table.split('.')
                        if len(schema_domain) == 2:
                            target_schema, target_domain = schema_domain
                            tables[table_name]['relationships'].append({
                                'source_field': source_field,
                                'target_table': target_table,
                                'target_field': f"{target_domain}_id",  # Assumption: target field is domain_id
                                'cardinality': cardinality
                            })
            
            # Second pass: Create table nodes
            for table_name, table_info in tqdm.tqdm(tables.items(), desc="Creating Table nodes"):
                # Skip if no columns (probably just a reference)
                if not table_info['columns']:
                    continue
                
                # Generate embedding for table description
                table_desc = table_info['description']
                # embedding_result = embedding(
                #     model=Config.EMBEDDING_MODEL,
                #     input=[table_desc if table_desc else table_name]
                # )
                
                                        # embedding: vecf32($embedding)

                # Create table node
                graph.query(
                    """
                    CREATE (t:Table {
                        name: $table_name, 
                        description: $description
                    })
                    """,
                    {
                        'table_name': table_name,
                        'description': table_desc,
                        # 'embedding': embedding_result.data[0].embedding
                    }
                )
                
                # Create column nodes
                for col_name, col_info in tqdm.tqdm(table_info['columns'].items(), desc=f"Creating columns for {table_name}"):
                    # embedding_result = embedding(
                    #     model=Config.EMBEDDING_MODEL,
                    #     input=[col_info['description'] if col_info['description'] else col_name]
                    # )
                    
                    
                    #                              # embedding: vecf32($embedding)

                    graph.query(
                        """
                        MATCH (t:Table {name: $table_name})
                        CREATE (c:Column {
                            name: $col_name,
                            type: $type,
                            nullable: $nullable,
                            key_type: $key,
                            default_value: $default,
                            extra: $extra,
                            description: $description
                        })-[:BELONGS_TO]->(t)
                        """,
                        {
                            'table_name': table_name,
                            'col_name': col_name,
                            'type': col_info['type'],
                            'nullable': col_info['null'],
                            'key': col_info['key'],
                            'default': col_info['default'],
                            'extra': col_info['extra'],
                            'description': col_info['description'],
                            # 'embedding': embedding_result.data[0].embedding
                        }
                    )
            
            # Third pass: Create relationships
            for table_name, table_info in tqdm.tqdm(tables.items(), desc="Creating relationships"):
                for rel in table_info['relationships']:
                    source_field = rel['source_field']
                    target_table = rel['target_table']
                    target_field = rel['target_field']
                    cardinality = rel['cardinality']
                    
                    # Create constraint name
                    constraint_name = f"fk_{table_name.replace('.', '_')}_{source_field}_to_{target_table.replace('.', '_')}"
                    
                    # Create relationship if both tables and columns exist
                    try:
                        graph.query(
                            """
                            MATCH (src:Column {name: $source_col})
                                -[:BELONGS_TO]->(source:Table {name: $source_table})
                            MATCH (tgt:Column {name: $target_col})
                                -[:BELONGS_TO]->(target:Table {name: $target_table})
                            CREATE (src)-[:REFERENCES {
                                constraint_name: $fk_name,
                                cardinality: $cardinality
                            }]->(tgt)
                            """,
                            {
                                'source_col': source_field,
                                'source_table': table_name,
                                'target_col': target_field,
                                'target_table': target_table,
                                'fk_name': constraint_name,
                                'cardinality': cardinality
                            }
                        )
                    except Exception as e:
                        print(f"Warning: Could not create relationship: {str(e)}")
                        continue
            
            return True, "Data dictionary loaded successfully into graph"
            
        except Exception as e:
            return False, f"Error loading CSV: {str(e)}"


if __name__ == "__main__":
    # Example usage
    loader = CSVLoader()
    success, message = loader.load("my_graph", "Data Dictionary.csv")
    print(message)