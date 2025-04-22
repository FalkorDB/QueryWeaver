from typing import Tuple, Dict, List
import io
import pandas as pd
import tqdm
from collections import defaultdict
from litellm import embedding
from app.loaders.base_loadr import BaseLoader
from app.extensions import db
from app.loaders.graph_loader import load_to_graph


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

            db_name = """Abacus Domain Model 25.3.5
The Abacus Domain Model is a physical manifestation of the hierarchical object model that Abacus Insights uses to store data. (It is not a relational database.) It is a foundational aspect of
the Abacus Insights Platform, interacting with data ingestion, consumption, and data management. The domain model will continue to evolve with the addition of new data sources and
connectors.
The Abacus Domain Model is organized into schemas, which group related domains. We implement each domain as a broad structure with minimal nesting. The model avoids inheritance and
deep nesting to minimize complexity and optimize performance."""

            
            # Process data by grouping by Schema and Domain to identify tables
            # Group by Schema and Domain to get tables
            tables = defaultdict(lambda: {
                'description': '',
                'columns': {},
                # 'relationships': [],
                'col_descriptions': []
            })

            rel_table = defaultdict(lambda: {
                'primary_key_table': '',
                'fk_tables': []
            })
            relationships = {}
            # First pass: Organize data into tables
            for idx, row in tqdm.tqdm(df.iterrows(), total=len(df), desc="Organizing data"):
                schema = row['Schema']
                domain = row['Domain']

                table_name = f"{schema}.{domain}"
                
                # Set table description (use Domain Description if available)
                if 'Domain Description' in row and not pd.isna(row['Domain Description']) and not tables[table_name]['description']:
                    tables[table_name]['description'] = row['Domain Description']
                
                # Add column information
                field = row['Field']
                field_type = row['Type'] if not pd.isna(row['Type']) else 'STRING'
                field_desc = row['Description'] if not pd.isna(row['Description']) else field
                    
                nullable = True  # Default to nullable since we don't have explicit null info
                if not pd.isna(field):
                    tables[table_name]['col_descriptions'].append(field_desc)
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
                        # cardinality = row['Cardinality']
                        if table_name not in relationships:
                            relationships[table_name] = []
                        relationships[table_name].append({"from": table_name,
                                                    "to": target_table,
                                                    "source_column": source_field,
                                                    "target_column": df.to_dict("records")[idx+1]['Array Field'] if not pd.isna(df.to_dict("records")[idx+1]['Array Field']) else '',
                                                    "note": ""})
                        
                        # tables[table_name]['relationships'].append({
                        #     'source_field': source_field,
                        #     'target_table': target_table,
                        #     'cardinality': cardinality,
                        #     'target_field': df.to_dict("records")[idx+1]['Array Field'] if not pd.isna(df.to_dict("records")[idx+1]['Array Field']) else ''
                        # })
                        tables[target_table]["description"] = field_desc

                else:
                    field = row['Array Field']
                    field_desc = field_desc if not pd.isna(field_desc) else field
                    # if len(tables[target_table]['col_descriptions']) == 0:
                    #     tables[table_name]['relationships'][-1]['target_field'] = field
                    tables[target_table]['col_descriptions'].append(field_desc)
                    tables[target_table]['columns'][field] = {
                        'type': field_type,
                        'description': field_desc,
                        'null': nullable,
                        'key': 'PRI' if field.lower().endswith('_id') else '',  # Assumption: *_id fields are primary keys
                        'default': '',
                        'extra': ''
                    }
                if field.endswith('_id'):
                    if len(tables[table_name]['columns']) == 1 and field.endswith('_id'):
                        suspected_primary_key = field[:-3]
                        if suspected_primary_key in domain:
                            rel_table[field]['primary_key_table'] = table_name
                        else:
                            rel_table[field]['fk_tables'].append(table_name)
                    else:
                        rel_table[field]['fk_tables'].append(table_name)

            for key, tables_info in tqdm.tqdm(rel_table.items(), desc="Creating relationships from names"):
                if len(tables_info['fk_tables']) > 0:
                    fk_tables = list(set(tables_info['fk_tables']))
                    if len(tables_info['primary_key_table']) > 0:
                        for table in fk_tables:
                            if table not in relationships:
                                relationships[table_name] = []
                            relationships[table].append({"from": table,
                                                    "to": tables_info['primary_key_table'],
                                                    "source_column": key,
                                                    "target_column": key,
                                                    "note": 'many-one'})
                    else:
                        for table_1 in fk_tables:
                            for table_2 in fk_tables:
                                if table_1 != table_2:
                                    if table_1 not in relationships:
                                        relationships[table_1] = []
                                    relationships[table_1].append({"from": table_1,
                                                                "to": table_2,
                                                                "source_column": key,
                                                                "target_column": key,
                                                                "note": 'many-many'})
            
            load_to_graph(graph_id, tables, relationships, db_name=db_name)
            return True, "Data dictionary loaded successfully into graph"
            
        except Exception as e:
            return False, f"Error loading CSV: {str(e)}"
                    # else:
                    #     # For case 2: when no primary key table exists, connect all FK tables to each other
                    #     graph.query(
                    #                 """
                    #                 CREATE (src: Column {name: $col, cardinality: $cardinality})
                    #                 """,
                    #                 {
                    #                     'col': key,
                    #                     'cardinality': 'many-many'
                    #                 }
                    #             )
                    #     for i in range(len(fk_tables)):
                    #         graph.query(
                    #             """
                    #             MATCH (src:Column {name: $source_col})
                    #                 -[:BELONGS_TO]->(source:Table {name: $source_table})
                    #             MATCH (tgt:Column {name: $target_col, cardinality: $cardinality})
                    #             CREATE (src)-[:REFERENCES {
                    #                 constraint_name: $fk_name,
                    #                 cardinality: $cardinality
                    #             }]->(tgt)
                    #             """,
                    #             {
                    #                 'source_col': key,
                    #                 'target_col': key,
                    #                 'source_table': fk_tables[i],
                    #                 'fk_name': key,
                    #                 'cardinality': 'many-many'
                    #             }
                    #         )

#             # Second pass: Create table nodes
#             for table_name, table_info in tqdm.tqdm(tables.items(), desc="Creating Table nodes"):
#                 # Skip if no columns (probably just a reference)
#                 if not table_info['columns']:
#                     continue
                
#                 # Generate embedding for table description
#                 table_desc = table_info['description']
#                 embedding_result = client.models.embed_content(
#                                         model="text-embedding-004",
#                                         contents=[table_desc if table_desc else table_name],
#                                     )

#                 # Create table node
#                 graph.query(
#                     """
#                     CREATE (t:Table {
#                         name: $table_name, 
#                         description: $description,
#                         embedding: vecf32($embedding)
#                     })
#                     """,
#                     {
#                         'table_name': table_name,
#                         'description': table_desc,
#                         'embedding': embedding_result.embeddings[0].values
#                     }
#                 )
#                 try:
#                     embed_columns = []
#                     batch_size = 50
#                     col_descriptions = table_info['col_descriptions']
#                     for batch in tqdm.tqdm(
#                             [col_descriptions[i:i + batch_size] for i in range(0, len(col_descriptions), batch_size)],
#                             desc=f"Creating embeddings for {table_name}"):
                        
#                         embedding_result = embedding(model='bedrock/cohere.embed-english-v3', input=batch[:95], aws_profile_name=Config.AWS_PROFILE, aws_region_name=Config.AWS_REGION)
#                         embed_columns.extend([emb.values for emb in embedding_result.embeddings])
#                 except Exception as e:
#                     print(f"Error creating embeddings: {str(e)}")
            
#                 # Create column nodes
#                 for idx, (col_name, col_info) in tqdm.tqdm(enumerate(table_info['columns'].items()), desc=f"Creating columns for {table_name}", total=len(table_info['columns'])):
#                     # embedding_result = embedding(
#                     #     model=Config.EMBEDDING_MODEL,
#                     #     input=[col_info['description'] if col_info['description'] else col_name]
#                     # )
                    
#                     ## Temp
#                     # agent_tax = TaxonomyAgent()
#                     # tax = agent_tax.get_answer(col_name, col_info)
#                     #                              # 
#                     graph.query(
#                         """
#                         MATCH (t:Table {name: $table_name})
#                         CREATE (c:Column {
#                             name: $col_name,
#                             type: $type,
#                             nullable: $nullable,
#                             key_type: $key,
#                             default_value: $default,
#                             extra: $extra,
#                             description: $description,
#                             embedding: vecf32($embedding)
#                         })-[:BELONGS_TO]->(t)
#                         """,
#                         {
#                             'table_name': table_name,
#                             'col_name': col_name,
#                             'type': col_info['type'],
#                             'nullable': col_info['null'],
#                             'key': col_info['key'],
#                             'default': col_info['default'],
#                             'extra': col_info['extra'],
#                             'description': col_info['description'],
#                             'embedding': embed_columns[idx]
#                         }
#                     )
            
#             # Third pass: Create relationships
#             for table_name, table_info in tqdm.tqdm(tables.items(), desc="Creating relationships"):
#                 for rel in table_info['relationships']:
#                     source_field = rel['source_field']
#                     target_table = rel['target_table']
#                     cardinality = rel['cardinality']
#                     target_field = rel['target_field']#list(tables[tables[table_name]['relationships'][-1]['target_table']]['columns'].keys())[0]
#                     # Create constraint name
#                     constraint_name = f"fk_{table_name.replace('.', '_')}_{source_field}_to_{target_table.replace('.', '_')}"
                    
#                     # Create relationship if both tables and columns exist
#                     try:
#                         graph.query(
#                             """
#                             MATCH (src:Column {name: $source_col})
#                                 -[:BELONGS_TO]->(source:Table {name: $source_table})
#                             MATCH (tgt:Column {name: $target_col})
#                                 -[:BELONGS_TO]->(target:Table {name: $target_table})
#                             CREATE (src)-[:REFERENCES {
#                                 constraint_name: $fk_name,
#                                 cardinality: $cardinality
#                             }]->(tgt)
#                             """,
#                             {
#                                 'source_col': source_field,
#                                 'target_col': target_field,
#                                 'source_table': table_name,
#                                 'target_table': target_table,
#                                 'fk_name': constraint_name,
#                                 'cardinality': cardinality
#                             }
#                         )
#                     except Exception as e:
#                         print(f"Warning: Could not create relationship: {str(e)}")
#                         continue
#             for key, tables_info in tqdm.tqdm(rel_table.items(), desc="Creating relationships from names"):
#                 if len(tables_info['fk_tables']) > 0:
#                     fk_tables = list(set(tables_info['fk_tables']))
#                     if len(tables_info['primary_key_table']) > 0:
#                         for table in fk_tables:
#                             graph.query(
#                                 """
#                                 MATCH (src:Column {name: $source_col})
#                                     -[:BELONGS_TO]->(source:Table {name: $source_table})
#                                 MATCH (tgt:Column {name: $target_col})
#                                     -[:BELONGS_TO]->(target:Table {name: $target_table})
#                                 CREATE (src)-[:REFERENCES {
#                                     constraint_name: $fk_name,
#                                     cardinality: $cardinality
#                                 }]->(tgt)
#                                 """,
#                                 {
#                                     'source_col': key,
#                                     'target_col': key,
#                                     'source_table': table,
#                                     'target_table': tables_info['primary_key_table'],
#                                     'fk_name': key,
#                                     'cardinality': 'many-one'
#                                 }
#                             )
#                     else:
#                         # For case 2: when no primary key table exists, connect all FK tables to each other
#                         graph.query(
#                                     """
#                                     CREATE (src: Column {name: $col, cardinality: $cardinality})
#                                     """,
#                                     {
#                                         'col': key,
#                                         'cardinality': 'many-many'
#                                     }
#                                 )
#                         for i in range(len(fk_tables)):
#                             graph.query(
#                                 """
#                                 MATCH (src:Column {name: $source_col})
#                                     -[:BELONGS_TO]->(source:Table {name: $source_table})
#                                 MATCH (tgt:Column {name: $target_col, cardinality: $cardinality})
#                                 CREATE (src)-[:REFERENCES {
#                                     constraint_name: $fk_name,
#                                     cardinality: $cardinality
#                                 }]->(tgt)
#                                 """,
#                                 {
#                                     'source_col': key,
#                                     'target_col': key,
#                                     'source_table': fk_tables[i],
#                                     'fk_name': key,
#                                     'cardinality': 'many-many'
#                                 }
#                             )

        #     load_to_graph(graph_id, entities, relationships, db_name="ERP system")
        #     return True, "Data dictionary loaded successfully into graph"
            
        # except Exception as e:
        #     return False, f"Error loading CSV: {str(e)}"


# if __name__ == "__main__":
#     # Example usage
#     loader = CSVLoader()
#     success, message = loader.load("my_graph", "Data Dictionary.csv")
#     print(message)