""" Module to handle the graph data loading into the database. """
import json
import re
from typing import List, Optional, Tuple
import xml.etree.ElementTree as ET
from xmlrpc.client import Boolean
import tqdm
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
    # followup_questions: list[str]

try:
    with open(Config.SCHEMA_PATH, 'r', encoding='utf-8') as f:
        schema = json.load(f)
except FileNotFoundError as exc:
    raise FileNotFoundError(f"Schema file not found: {Config.SCHEMA_PATH}") from exc
except json.JSONDecodeError as exc:
    raise ValueError(f"Invalid schema JSON: {str(exc)}") from exc


def load_xml_graph(graph_id: str, data) -> Tuple[Boolean, str]:
    """ Load XML ODATA schema into a Graph. """

    try:
        # Parse the OData schema
        entities, relationships = _parse_odata_schema(data)
    except ET.ParseError:
        return False, "Invalid XML content"

    # Generate Cypher queries
    entities_queries, relationships_queries = _generate_cypher_queries(entities, relationships)

    graph = db.select_graph(graph_id)

    # Run the Create entities Cypher queries
    for query in tqdm.tqdm(entities_queries, "Creating entities"):
        graph.query(query)

    # Run the Create relationships Cypher queries
    for query in tqdm.tqdm(relationships_queries, "Creating relationships"):
        graph.query(query)

    return True, "Graph loaded successfully"

def _parse_odata_schema(data) -> Tuple[dict, dict]:
    """
    This function parses the OData schema and returns entities and relationships.
    """
    entities = {}
    relationships = {}

    root = ET.fromstring(data)

    # Define namespaces
    namespaces = {
        'edmx': "http://docs.oasis-open.org/odata/ns/edmx",
        'edm': "http://docs.oasis-open.org/odata/ns/edm"
    }

    schema_element = root.find(".//edmx:DataServices/edm:Schema", namespaces)
    if schema_element is None:
        raise ET.ParseError("Schema element not found")
        
    entity_types = schema_element.findall("edm:EntityType", namespaces)
    for entity_type in tqdm.tqdm(entity_types, "Parsing OData schema"):
        entity_name = entity_type.get("Name")
        entities[entity_name] = {prop.get("Name"): prop.get("Type") for prop in entity_type.findall("edm:Property", namespaces)}
        description = entity_type.findall("edm:Annotation", namespaces)
        if len(description) == 1:
            entities[entity_name]["description"] = description[0].get("String").replace("'", "\\'")

        for rel in entity_type.findall("edm:NavigationProperty", namespaces):
            if rel.get("Name") not in relationships:
                relationships[rel.get("Name")] = []    
            relationships[rel.get("Name")].append({
                "from": entity_name,
                "to": re.findall("Priority.OData.(\\w+)\\b", rel.get("Type"))[0]
            })

    return entities, relationships

def _generate_cypher_queries(entities, relationships):
    """
    This function generates Cypher queries for entities and relationships.
    """
    entities_queries = []
    relationships_queries = []

    for entity_name, props in tqdm.tqdm(entities.items(), "Generating create entity Cypher queries"):
        query = "CREATE (n:Table {{"
        query += f"name: '{entity_name}', "
        query += ", ".join([f"{key}: '{value}'" for key, value in props.items()])
        query += "})"
        entities_queries.append(query)

    for relationship_name, relationships in tqdm.tqdm(relationships.items(), "Generating create relationship Cypher queries"):
        for relationship in relationships:
            query = f"""MATCH (a:Table {{ name:{relationship["from"] }}}),
            (b:Table {{ name: {relationship["to"]} }})
            CREATE (a)-[r:REFERENCES]->(b)
            SET r.name = '{relationship_name}'
            """
            relationships_queries.append(query)

    return entities_queries, relationships_queries

def load_json_graph(graph_id: str, data) -> Tuple[Boolean, str]:
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

    # if len(descriptions.followup_questions) > 0:
    #     return True, [{"followup_questions": descriptions.followup_questions}]

    tables_results = _find_tables(graph, descriptions.tables_descriptions)
    columns_results = _find_tables_by_columns(graph, descriptions.columns_descriptions)

    return True, (tables_results + columns_results)

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
                    MATCH (node)-[:BELONGS_TO]-(columns)
                    RETURN node.name, node.description, collect({
                        columnName: columns.name,
                        description: columns.description,
                        type: columns.type,
                        null: columns.null,
                        key: columns.key,
                        default: columns.default,
                        extra: columns.extra
                    })
                    """,
                    {
                        'embedding': embedding_result.data[0].embedding
                    })

        for node in query_result.result_set:
            result.append(node)

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
                    ) YIELD node, score
                    MATCH (node)-[:BELONGS_TO]-(table)-[:BELONGS_TO]-(columns)
                    RETURN table.name, table.description, collect({
                        columnName: columns.name,
                        description: columns.description,
                        type: columns.type,
                        null: columns.null,
                        key: columns.key,
                        default: columns.default,
                        extra: columns.extra
                    })
                    """,
                    {
                        'embedding': embedding_result.data[0].embedding
                    })

        for node in query_result.result_set:
            result.append(node)

    return result
