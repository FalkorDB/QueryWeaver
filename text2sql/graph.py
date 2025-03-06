""" Module to handle the graph data loading into the database. """
import json
from typing import List, Optional, Tuple
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

def  find(
    graph_id: str,
    queries_history: List[str]
) -> Tuple[bool, List[dict]]:
    """ Find the tables and columns relevant to the user's query. """
    
    user_query = queries_history[-1]
    previous_queries = queries_history[:-1]

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
                                            "content": json.dumps({
                                                "previous_user_queries:": previous_queries,
                                                "user_query": user_query
                                            }),
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
    graph = db.select_graph(graph_id)
    tables_results = _find_tables(graph, descriptions.tables_descriptions)
    columns_results = _find_tables_by_columns(graph, descriptions.columns_descriptions)

    return True, _get_unique_tables(tables_results + columns_results)

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
                    RETURN 
                    table.name, 
                    table.description, 
                    collect({
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

def _get_unique_tables(tables_list):
    # Dictionary to store unique tables with the table name as the key
    unique_tables = {}
    
    for table_info in tables_list:
        table_name = table_info[0]  # The first element is the table name
        
        # Only add if this table name hasn't been seen before
        if table_name not in unique_tables:
            unique_tables[table_name] = table_info
    
    # Return the values (the unique table info lists)
    return list(unique_tables.values())