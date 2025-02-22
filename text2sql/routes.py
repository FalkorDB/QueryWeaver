import json
import os 
from flask import Blueprint, jsonify, request
from jsonschema import validate, ValidationError
from litellm import embedding

from text2sql.extensions import db

os.environ['GEMINI_API_KEY'] = 'AIzaSyB23NqqMWzEcojAqgLmEhc2xxkuSPBBwys'

main = Blueprint("main", __name__)

# Load schema once when starting the app
SCHEMA_PATH = "text2sql/schema_schema.json"

try:
    with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
        schema = json.load(f)
except FileNotFoundError as exc:
    raise FileNotFoundError(f"Schema file not found: {SCHEMA_PATH}") from exc
except json.JSONDecodeError as exc:
    raise ValueError(f"Invalid schema JSON: {str(exc)}") from exc

@main.route("/")
def home():
    """
    Home route
    """
    return jsonify({"message": "Welcome to My Flask App!"})

@main.route("/graphs/<string:graph_id>", methods=["POST"])
def load(graph_id: str):
    """
    This route is used to load the graph data into the database.
    It gets the Graph name as an argument and expects
    a JSON payload with the following structure: txt2sql/schema_schema.json
    """
    data = request.get_json()

    # Validate the JSON with the schema should return a bad request if the payload is not valid
    try:
        validate(data, schema)
    except ValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    graph = db.select_graph(graph_id)

    # Create Table nodes and their relationships
    for table_name, table_info in data['tables'].items():
        # Create table node and connect to database
        
        embedding_result = embedding(model='gemini/text-embedding-004', input=[table_info['description']])
        
        graph.query(
            """
            CREATE (t:Table {name: $table_name, description: $description, embedding: vecf32($embedding)})
            """,
            {
                'table_name': table_name,
                'description': table_info['description'],
                'embedding': embedding_result.data[0].embedding
            }
        )

        # Create Column nodes
        for col_name, col_info in table_info['columns'].items():
            
            embedding_result = embedding(model='gemini/text-embedding-004', input=[col_info['description']])

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
                    description: $description,
                    embedding: vecf32($embedding)
                })-[:BELONGS_TO]->(t)
                """,
                {
                    'table_name': table_name,
                    'col_name': col_name,
                    'type': col_info['type'],
                    'nullable': col_info['null'],
                    'key': col_info['key'],
                    'default': str(col_info['default']) if col_info['default'] is not None else '',
                    'extra': col_info['extra'],
                    'description': col_info['description'],
                    'embedding': embedding_result.data[0].embedding
                }
            )

        # Create Index nodes
        for idx_name, idx_info in table_info['indexes'].items():
            # Create index node
            graph.query(
                """
                MATCH (t:Table {name: $table_name})
                CREATE (i:Index {
                    name: $idx_name,
                    unique: $unique,
                    type: $idx_type
                })-[:BELONGS_TO]->(t)
                """,
                {
                    'table_name': table_name,
                    'idx_name': idx_name,
                    'unique': idx_info['unique'],
                    'idx_type': idx_info['type']
                }
            )

            # Connect index to its columns
            for col in idx_info['columns']:
                graph.query(
                    """
                    MATCH (i:Index {name: $idx_name})-[:BELONGS_TO]->(t:Table {name: $table_name})
                    MATCH (c:Column {name: $col_name})-[:BELONGS_TO]->(t)
                    CREATE (i)-[:INCLUDES {
                        sequence: $seq,
                        sub_part: $sub_part
                    }]->(c)
                    """,
                    {
                        'idx_name': idx_name,
                        'table_name': table_name,
                        'col_name': col['name'],
                        'seq': col['seq_in_index'],
                        'sub_part': col['sub_part'] if col['sub_part'] is not None else ''
                    }
                )

        # Create Foreign Key relationships
        for fk_name, fk_info in table_info['foreign_keys'].items():
            graph.query(
                """
                MATCH (src:Column {name: $src_col})-[:BELONGS_TO]->(src_table:Table {name: $src_table})
                MATCH (tgt:Column {name: $tgt_col})-[:BELONGS_TO]->(tgt_table:Table {name: $tgt_table})
                CREATE (src)-[:REFERENCES {constraint_name: $fk_name}]->(tgt)
                """,
                {
                    'src_col': fk_info['column'],
                    'src_table': table_name,
                    'tgt_col': fk_info['referenced_column'],
                    'tgt_table': fk_info['referenced_table'],
                    'fk_name': fk_name
                }
            )

    return jsonify({"message": "Graph data loaded successfully", "graph_id": graph_id})

def init_routes(app):
    """
    Initialize routes
    """
    app.register_blueprint(main)
