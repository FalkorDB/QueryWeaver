import tqdm
from api.config import Config
from api.extensions import db
from api.utils import generate_db_description
import json

def load_to_graph(graph_id: str, entities: dict, relationships: dict, batch_size: int=100, db_name: str="TBD") -> None:
    """
    Load the graph data into the database.
    It gets the Graph name as an argument and expects
    
    Input:
    - entities: A dictionary containing the entities and their attributes.
    - relationships: A dictionary containing the relationships between entities.
    - batch_size: The size of the batch for embedding.
    - db_name: The name of the database.
    """
    graph = db.select_graph(graph_id)
    embedding_model = Config.EMBEDDING_MODEL
    vec_len = embedding_model.get_vector_size()

    try: 
        # Create vector indices
        graph.query("""
            CREATE VECTOR INDEX FOR (t:Table) ON (t.embedding) 
            OPTIONS {dimension:$size, similarityFunction:'euclidean'}
        """,
        {
            'size': vec_len
        })
        
        graph.query("""
            CREATE VECTOR INDEX FOR (c:Column) ON (c.embedding) 
            OPTIONS {dimension:$size, similarityFunction:'euclidean'}
        """,
        {
            'size': vec_len
        })
        graph.query("CREATE INDEX FOR (p:Table) ON (p.name)")
    except Exception as e:
        print(f"Error creating vector indices: {str(e)}")

    
        
    db_des = generate_db_description(
        db_name=db_name,
        table_names=list(entities.keys())
    )
    graph.query(
        """
        CREATE (d:Database {
            name: $db_name,
            description: $description
        })
        """,
        {
            'db_name': db_name,
            'description': db_des
        }
    )

            
    for table_name, table_info in tqdm.tqdm(entities.items(), desc="Creating Graph Table Nodes"):
        table_desc = table_info['description']
        embedding_result = embedding_model.embed(table_desc)

        # Create table node
        graph.query(
            """
            CREATE (t:Table {
                name: $table_name, 
                description: $description,
                embedding: vecf32($embedding),
                foreign_keys: $foreign_keys
            })
            """,
            {
                'table_name': table_name,
                'description': table_desc,
                'embedding': embedding_result[0],
                'foreign_keys': json.dumps(table_info['foreign_keys'])
            }
        )


        # Batch embeddings for table columns
        # TODO: Check if the embedding model and description are correct (without 2 sources of truth)
        batch_flag = True
        col_descriptions = table_info.get('col_descriptions')
        if col_descriptions is None:
            batch_flag = False
        else:
            try:
                embed_columns = []
                for batch in tqdm.tqdm(
                        [col_descriptions[i:i + batch_size] for i in range(0, len(col_descriptions), batch_size)],
                        desc=f"Creating embeddings for {table_name} columns",):
                    
                    embedding_result = embedding_model.embed(batch)
                    embed_columns.extend(embedding_result)
            except Exception as e:
                print(f"Error creating embeddings: {str(e)}")
                batch_flag = False
        
        # Create column nodes
        for idx, (col_name, col_info) in tqdm.tqdm(enumerate(table_info['columns'].items()), desc=f"Creating Graph Columns for {table_name}", total=len(table_info['columns'])):
            if not batch_flag:
                embed_columns = []
                embedding_result = embedding_model.embed(col_info['description'])
                embed_columns.extend(embedding_result)
                idx = 0

            graph.query(
                """
                MATCH (t:Table {name: $table_name})
                CREATE (c:Column {
                    name: $col_name,
                    type: $type,
                    nullable: $nullable,
                    key_type: $key,
                    description: $description,
                    embedding: vecf32($embedding)
                })-[:BELONGS_TO]->(t)
                """,
                {
                    'table_name': table_name,
                    'col_name': col_name,
                    'type': col_info.get('type', 'unknown'),
                    'nullable': col_info.get('null', 'unknown'),
                    'key': col_info.get('key', 'unknown'),
                    'description': col_info['description'],
                    'embedding': embed_columns[idx]
                }
            )
            
    # Create relationships
    for rel_name, table_info in tqdm.tqdm(relationships.items(), desc="Creating Graph Table Relationships"):
        for rel in table_info:
            source_table = rel['from']
            source_field = rel['source_column']
            target_table = rel['to']
            target_field = rel['target_column']
            note = rel.get('note', '')
            
            # Create relationship if both tables and columns exist
            try:
                graph.query(
                    """
                    MATCH (src:Column {name: $source_col})
                        -[:BELONGS_TO]->(source:Table {name: $source_table})
                    MATCH (tgt:Column {name: $target_col})
                        -[:BELONGS_TO]->(target:Table {name: $target_table})
                    CREATE (src)-[:REFERENCES {
                        rel_name: $rel_name,
                        note: $note
                    }]->(tgt)
                    """,
                    {
                        'source_col': source_field,
                        'target_col': target_field,
                        'source_table': source_table,
                        'target_table': target_table,
                        'rel_name': rel_name,
                        'note': note
                    }
                )
            except Exception as e:
                print(f"Warning: Could not create relationship: {str(e)}")
                continue