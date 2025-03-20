from typing import Tuple
import json
import tqdm
from jsonschema import ValidationError, validate
from litellm import embedding
from text2sql.config import Config
from text2sql.loaders.base_loadr import BaseLoader
from text2sql.extensions import db
from text2sql.utils import generate_db_description

try:
    with open(Config.SCHEMA_PATH, 'r', encoding='utf-8') as f:
        schema = json.load(f)
except FileNotFoundError as exc:
    raise FileNotFoundError(f"Schema file not found: {Config.SCHEMA_PATH}") from exc
except json.JSONDecodeError as exc:
    raise ValueError(f"Invalid schema JSON: {str(exc)}") from exc

class JSONLoader(BaseLoader):

    @staticmethod
    def load(graph_id: str, data) -> Tuple[bool, str]:
        """
        Load the graph data into the database.
        It gets the Graph name as an argument and expects
        a JSON payload with the following structure: txt2sql/schema_schema.json
        """

        # Validate the JSON with the schema should return a bad request if the payload is not valid
        try:
            validate(data, schema)
        except ValidationError as exc:
            return False, str(exc)

        graph = db.select_graph(graph_id)

        db_des = generate_db_description(
            db_name=data['database'],
            table_names=list(data['tables'].keys())
        )

        graph.query(
            """
            CREATE (d:Database {
                name: $db_name,
                description: $description
            })
            """,
            {
                'db_name': data['database'],
                'description': db_des
            }
        )
        try:
            graph.query("""
                        CREATE VECTOR INDEX FOR (t:Table) ON (t.embedding) 
                        OPTIONS {dimension:768, similarityFunction:'euclidean'}
                        """)

            graph.query("""
                    CREATE VECTOR INDEX FOR (c:Column) ON (c.embedding) 
                    OPTIONS {dimension:768, similarityFunction:'euclidean'}
                    """)
        except Exception as e:
                print(f"Error creating vector indices: {str(e)}")

        # Create Table nodes and their relationships
        for table_name, table_info in tqdm.tqdm(data['tables'].items(), "Create Table nodes"):
            # Create table node and connect to database
            embedding_result = embedding(
                model=Config.EMBEDDING_MODEL,
                input=[table_info['description']]
            )

            graph.query(
                """
                CREATE (t:Table {
                    name: $table_name, 
                    description: $description, 
                    embedding: vecf32($embedding)
                })
                """,
                {
                    'table_name': table_name,
                    'description': table_info['description'],
                    'embedding': embedding_result.data[0].embedding
                }
            )

            # Create Column nodes
            for col_name, col_info in tqdm.tqdm(table_info['columns'].items(), "Create Column nodes"):

                embedding_result = embedding(
                    model=Config.EMBEDDING_MODEL,
                    input=[col_info['description']]
                )

                graph.query(
                    """
                    MATCH (t:Table {name: $table_name})
                    CREATE (c:Column {
                        name: $col_name,
                        description: $description,
                        embedding: vecf32($embedding)
                    })-[:BELONGS_TO]->(t)
                    """,
                    {
                        'table_name': table_name,
                        'col_name': col_name,
                        'description': col_info['description'],
                        'embedding': embedding_result.data[0].embedding
                    }
                )

        for table_name, table_info in tqdm.tqdm(data['tables'].items(), "Create Table relationships"):
            # Create Foreign Key relationships
            for fk_name, fk_info in tqdm.tqdm(table_info['foreign_keys'].items(), "Create Foreign Key relationships"):
                graph.query(
                    """
                    MATCH (src:Column {name: $source_col})
                        -[:BELONGS_TO]->(source:Table {name: $source_table}
                    )
                    MATCH (tgt:Column {name: $target_col})
                        -[:BELONGS_TO]->(target:Table {name: $target_table}
                    )
                    CREATE (src)-[:REFERENCES {constraint_name: $fk_name}]->(tgt)
                    """,
                    {
                        'source_col': fk_info['column'],
                        'source_table': table_name,
                        'target_col': fk_info['referenced_column'],
                        'target_table': fk_info['referenced_table'],
                        'fk_name': fk_name
                    }
                )

        return True, "Graph loaded successfully"