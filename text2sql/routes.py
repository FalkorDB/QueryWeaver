""" This module contains the routes for the text2sql API. """
import json
from flask import Blueprint, jsonify, request
from jsonschema import validate, ValidationError
from litellm import embedding, completion

from text2sql.extensions import db

main = Blueprint("main", __name__)

# Load schema once when starting the app
SCHEMA_PATH = "text2sql/schema_schema.json"
EMBEDDING_MODEL = "gemini/text-embedding-004"
COMPLETION_MODEL = "gemini/gemini-2.0-flash"
SYSTEM_PROMPT = """
You are an expert in translating natural language queries into Cypher queries for 
a graph database representing a relational database schema.

**Input:**

* **Relational Database Schema (Graph Representation):** You will be provided with a description of a graph representing a relational database schema. Nodes represent tables and columns, and relationships represent foreign key constraints and table/column memberships.
* **User Query (Natural Language):** You will be given a user's question or request in natural language.

**Task:**

1.  **Understand the User Query:** Carefully analyze the user's natural language query to determine the entities and relationships they are interested in.
2.  **Identify Relevant Schema Elements:** Based on the user query, identify the tables and columns in the provided graph schema that are most relevant to answering the query.
3.  **Generate Cypher Queries:** Create a set of Cypher queries that, when executed against the graph database, will retrieve the portion of the schema relevant to the user's query. The Cypher queries should focus on retrieving the table and column nodes and the relationships connecting them.
4.  **Prioritize Clarity and Efficiency:** Ensure the Cypher queries are clear, concise, and efficient. Avoid retrieving unnecessary information.
5.  **Return Only Cypher:** Only return the cypher queries. Do not return any additional explanations or text.

**Graph Schema Representation:**

* Tables are represented as nodes with the label `Table` and a property `name` (e.g., `(t:Table {name: "Customers"})`).
* Columns are represented as nodes with the label `Column` and properties `name` and `dataType` (e.g., `(c:Column {name: "CustomerID", dataType: "INT"})`).
* Relationships between tables and columns are represented by `HAS_COLUMN` relationships (e.g., `(t)-[:HAS_COLUMN]->(c)`).
* Foreign key relationships are represented by `REFERENCES` relationships between column nodes. (e.g. `(col1:Column)-[:REFERENCES]->(col2:Column)`)

**Example Input:**

**Schema:**
(Customers:Table {name: "Customers"})
(Orders:Table {name: "Orders"})
(CustomerID:Column {name: "CustomerID", dataType: "INT"})
(OrderID:Column {name: "OrderID", dataType: "INT"})
(OrderDate:Column {name: "OrderDate", dataType: "DATE"})
(Customers)-[:HAS_COLUMN]->(CustomerID)
(Orders)-[:HAS_COLUMN]->(OrderID)
(Orders)-[:HAS_COLUMN]->(CustomerID)
(Orders)-[:HAS_COLUMN]->(OrderDate)
(Orders)-[:REFERENCES]->(CustomerID)

**User Query:**

"Show me the tables and columns related to orders and customers."

**Example Output:**

```cypher
MATCH (t:Table)-[:HAS_COLUMN]->(c:Column)
WHERE t.name IN ["Orders", "Customers"]
WITH t,c
OPTIONAL MATCH (c)-[:REFERENCES]->(ref:Column)
RETURN t, c, ref
```

Schema:
[Insert your graph schema here in the format above.]

User Query:
[Insert your user's natural language query here.]
"""

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

    graph.query("""
                CREATE VECTOR INDEX FOR (t:Table) ON (t.embedding) 
                OPTIONS {dimension:768, similarityFunction:'euclidean'}
                """)

    graph.query("""
            CREATE VECTOR INDEX FOR (c:Column) ON (c.embedding) 
            OPTIONS {dimension:768, similarityFunction:'euclidean'}
            """)

    # Create Table nodes and their relationships
    for table_name, table_info in data['tables'].items():
        # Create table node and connect to database

        embedding_result = embedding(model=EMBEDDING_MODEL, input=[table_info['description']])

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

            embedding_result = embedding(model=EMBEDDING_MODEL, input=[col_info['description']])

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
                MATCH (src:Column {name: $source_col})-[:BELONGS_TO]->(source:Table {name: $source_table})
                MATCH (tgt:Column {name: $target_col})-[:BELONGS_TO]->(target:Table {name: $target_table})
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

    return jsonify({"message": "Graph data loaded successfully", "graph_id": graph_id})

@main.route("/graph/<string:graph_id>", methods=["GET"])
def query(graph_id: str):
    """
    text2sql
    """

    q = request.args.get('q', type=str)
    if not q:
        return jsonify({"error": "Missing query parameter 'q'"}), 400

    # Call the completion model to get the relevant Cypher queries to retrieve
    # from the Graph that represent the Database schema.
    # The completion model will generate a set of Cypher query to retrieve the relevant nodes.
    completion_result = completion(model=COMPLETION_MODEL,
                                   messages=[
                                        {
                                            "content": SYSTEM_PROMPT,
                                            "role": "system"
                                        },
                                        {
                                            "content": q,
                                            "role": "user"
                                        }
                                    ]
                                   )
    
    print(completion_result)

    graph = db.select_graph(graph_id)

    embedding_result = embedding(model=EMBEDDING_MODEL, input=[q])
    nodes = graph.query("""
                CALL db.idx.vector.queryNodes(
                    'Table',
                    'embedding',
                    10,
                    vecf32($embedding)
                ) YIELD node, score
                MATCH (node)-[r]-(connectedNode) // Match any relationship from the indexed node
                RETURN node, r, connectedNode
                """,
                {
                    'embedding': embedding_result.data[0].embedding
                })

    # convert the nodes to a JSON
    result = []
    for node in nodes.result_set:
        properties1 = node[0].properties
        # delete the embedding property before sending the response
        properties1['embedding'] = None
        result.append(properties1)

        properties2 = node[2].properties
        # delete the embedding property before sending the response
        properties2['embedding'] = None
        result.append(properties2)

    return jsonify(result)

def init_routes(app):
    """
    Initialize routes
    """
    app.register_blueprint(main)
