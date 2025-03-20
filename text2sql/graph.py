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

def find(
    graph_id: str,
    queries_history: List[str]
) -> Tuple[bool, List[dict]]:
    """ Find the tables and columns relevant to the user's query. """
    
    graph = db.select_graph(graph_id)
    user_query = queries_history[-1]
    previous_queries = queries_history[:-1]

    db_description = graph.query("""
        MATCH (d:Database {name: $db_name})
        RETURN d.description
        """,
        {
            'db_name': graph_id
        }
    ).result_set[0][0]

    # Call the completion model to get the relevant Cypher queries to retrieve
    # from the Graph that represent the Database schema.
    # The completion model will generate a set of Cypher query to retrieve the relevant nodes.
    completion_result = completion(model=Config.COMPLETION_MODEL,
                                    response_format=Descriptions,
                                    messages=[
                                        {
                                            "content": Config.FIND_SYSTEM_PROMPT.format(db_description=db_description),
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
    tables_results = _find_tables(graph, descriptions.tables_descriptions)
    columns_results = _find_tables_by_columns(graph, descriptions.columns_descriptions)

    return True, _get_unique_tables(tables_results + columns_results), db_description, graph

def _find_tables(graph, descriptions: List[TableDescription]) -> List[dict]:

    result = []
    res_sphere = []
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
            if node not in result:
                result.append(node)
    
    for table in result:
        table_name = table[0]
        query_result = graph.query("""
                    MATCH (node:Table {name: $name})
                    MATCH (node)-[:BELONGS_TO]-(column)-[:REFERENCES]-()-[:BELONGS_TO]-(table_ref)
                    WITH table_ref
                    MATCH (table_ref)-[:BELONGS_TO]-(columns)
                    RETURN table_ref.name, table_ref.description, collect({
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
                        'name': table_name
                    })
        for node in query_result.result_set:
            if node not in res_sphere:
                res_sphere.append(node)

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
            if node not in result:
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


def find_connecting_tables(graph, table_names, result_tables):
    """
    Find all tables that form connections between any pair of tables in the input list.
    Handles both Table nodes and Column nodes with primary keys.
    
    Args:
        graph: The FalkorDB graph database connection
        table_names: List of table names to check connections between
        
    Returns:
        A set of all table names that form connections between any pair in the input
    """
    all_connecting_tables = set()
    all_connecting_tables_id = set()
    
    # Check all possible pairs of tables
    for i in range(len(table_names)):
        for j in range(i + 1, len(table_names)):  # This ensures i != j
            table1 = table_names[i]
            table2 = table_names[j]
            
            # Query to find all tables in the shortest paths between the pair
            query = """
            MATCH (a:Table {name: $table1}), (b:Table {name: $table2})  
            WITH a, b
            MATCH p=allShortestPaths((a)-[r*]-(b))
            RETURN nodes(p) as nodes
            """
            
            result = graph.query(query, {'table1': table1, 'table2': table2}).result_set
            
            # Extract table names from the paths
            for path in result:
                for node in path[0]:  # path[0] contains the nodes array
                    if 'Table' in node.labels:
                        all_connecting_tables.add(node.properties["name"])
                        all_connecting_tables_id.add(node.id)
                    elif 'Column' in node.labels and node.properties.get('key_type') == 'PRI':
                        # For primary key columns, get the table they belong to
                        table_query = """
                        MATCH (n:Column)-[:BELONGS_TO]->(t:Table) 
                        WHERE id(n)=$n_id 
                        RETURN t
                        """
                        parent_table = graph.query(table_query, {'n_id': node.id}).result_set
                        if parent_table and len(parent_table) > 0:
                            all_connecting_tables.add(parent_table[0][0].properties["name"])
                            all_connecting_tables_id.add(parent_table[0][0].id)

    query_result = graph.query("""UNWIND $ids AS id 
                MATCH (n:Table)-[:BELONGS_TO]-(columns) 
                WHERE id(n)=id 
                RETURN n.name, n.description, collect({
                        columnName: columns.name,
                        description: columns.description,
                        type: columns.type,
                        null: columns.null,
                        key: columns.key,
                        default: columns.default,
                        extra: columns.extra
                    })""", {'ids': list(all_connecting_tables_id)})
    for node in query_result.result_set:
            if node not in result_tables:
                result_tables.append(node)
    print(f"Connecting tables: {all_connecting_tables}")
    return result_tables, list(all_connecting_tables)