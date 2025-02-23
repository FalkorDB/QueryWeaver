""" Module to handle the graph data loading into the database. """
import json
from typing import List, Optional, Tuple
from xmlrpc.client import Boolean
from jsonschema import ValidationError, validate
from litellm import completion, embedding
from pydantic import BaseModel
from text2sql.config import Config
from text2sql.extensions import db

class TableDescription(BaseModel):
    """ Table Description """
    name: str
    description: str

class ColumnDescription(BaseModel):
    """ Column Description """
    name: str
    description: str

class Descriptions(BaseModel):
    """ List of tables """
    tables_descriptions: list[TableDescription]
    columns_descriptions: list[ColumnDescription]
    followup_questions: list[str]

try:
    with open(Config.SCHEMA_PATH, 'r', encoding='utf-8') as f:
        schema = json.load(f)
except FileNotFoundError as exc:
    raise FileNotFoundError(f"Schema file not found: {Config.SCHEMA_PATH}") from exc
except json.JSONDecodeError as exc:
    raise ValueError(f"Invalid schema JSON: {str(exc)}") from exc

def load_graph(graph_id: str, data) -> Tuple[Boolean, str]:
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
        for col_name, col_info in table_info['columns'].items():

            embedding_result = embedding(
                model=Config.EMBEDDING_MODEL,
                input=[col_info['description']]
            )

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

def find(
    graph_id: str,
    query: str,
    _history: Optional[List[str]] = None
) -> Tuple[Boolean, List[dict]]:
    """ Find the tables and columns relevant to the user's query. """

    graph = db.select_graph(graph_id)

    # Call the completion model to get the relevant Cypher queries to retrieve
    # from the Graph that represent the Database schema.
    # The completion model will generate a set of Cypher query to retrieve the relevant nodes.
    completion_result = completion(model=Config.COMPLETION_MODEL,
                                    response_format=Descriptions,
                                    messages=[
                                        {
                                            "content": Config.FIND_SYSTEM_PROMPT,
                                            "role": "system"
                                        },
                                        {
                                            "content": query,
                                            "role": "user"
                                        }
                                    ]
                                   )

    json_str = completion_result.choices[0].message.content

    # Parse JSON string and convert to Pydantic model
    json_data = json.loads(json_str)
    descriptions = Descriptions(**json_data)

    if len(descriptions.followup_questions) > 0:
        return True, [{"followup_questions": descriptions.followup_questions}]

    result = _find_tables(graph, descriptions.tables_descriptions)
    result = _find_tables_by_columns(graph, descriptions.columns_descriptions)

    return True, result

def _find_tables(graph, descriptions: List[TableDescription]) -> List[dict]:

    result = []
    for table in descriptions:

        # Get the table node from the graph
        embedding_result = embedding(model=Config.EMBEDDING_MODEL, input=[table.description])
        query_result = graph.query("""
                    CALL db.idx.vector.queryNodes(
                        'Table',
                        'embedding',
                        3,
                        vecf32($embedding)
                    ) YIELD node, score
                    MATCH (node)<-[r:BELONGS_TO]-(columns)
                    WITH node.name as tableName,  
                    collect({
                        columnName: columns.name,
                        description: columns.description,
                        type: columns.type,
                        null: columns.null,
                        key: columns.key,
                        default: columns.default,
                        extra: columns.extra
                    }) as columnsList
                    RETURN {
                        [tableName]: {
                            description: node.description,
                            columns: reduce(acc = {}, col in columnsList | 
                                acc + {
                                    [col.columnName]: {
                                        description: col.description,
                                        type: col.type,
                                        null: col.null,
                                        key: col.key,
                                        default: col.default,
                                        extra: col.extra
                                    }
                                }
                            )
                        }
                    } as result
                    """,
                    {
                        'embedding': embedding_result.data[0].embedding
                    })

        # convert the nodes to a JSON
        for nodes in query_result.result_set:
            for node in nodes:
                properties = node.properties
                # delete the embedding property before sending the response
                properties.pop('embedding', None)
                result.append(properties)

    return result

def _find_tables_by_columns(graph, descriptions: List[ColumnDescription]) -> List[dict]:

    result = []
    for column in descriptions:

        # Get the table node from the graph
        embedding_result = embedding(model=Config.EMBEDDING_MODEL, input=[column.description])
        query_result = graph.query("""
                    CALL db.idx.vector.queryNodes(
                        'Column',
                        'embedding',
                        3,
                        vecf32($embedding)
                    ) YIELD column, score
                    MATCH (node)<-[r:BELONGS_TO]-(columns)
                    WITH node.name as tableName,  
                    collect({
                        columnName: columns.name,
                        description: columns.description,
                        type: columns.type,
                        null: columns.null,
                        key: columns.key,
                        default: columns.default,
                        extra: columns.extra
                    }) as columnsList
                    RETURN {
                        [tableName]: {
                            description: node.description,
                            columns: reduce(acc = {}, col in columnsList | 
                                acc + {
                                    [col.columnName]: {
                                        description: col.description,
                                        type: col.type,
                                        null: col.null,
                                        key: col.key,
                                        default: col.default,
                                        extra: col.extra
                                    }
                                }
                            )
                        }
                    } as result
                    """,
                    {
                        'embedding': embedding_result.data[0].embedding
                    })

        # convert the nodes to a JSON
        for nodes in query_result.result_set:
            for node in nodes:
                properties = node.properties
                # delete the embedding property before sending the response
                properties.pop('embedding', None)
                result.append(properties)

    return result
