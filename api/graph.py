""" Module to handle the graph data loading into the database. """
import json
import logging
from typing import List, Tuple
from litellm import completion
from pydantic import BaseModel
from api.config import Config
from api.extensions import db

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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

def find(
    graph_id: str,
    queries_history: List[str]
) -> Tuple[bool, List[dict]]:
    """ Find the tables and columns relevant to the user's query. """
    
    graph = db.select_graph(graph_id)
    user_query = queries_history[-1]
    previous_queries = queries_history[:-1]

    db_description = graph.query("""
        MATCH (d:Database)
        RETURN d.description
        """
    ).result_set[0][0]
    logging.info(f"Calling to an LLM to find relevant tables and columns for the query: {user_query}")
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
                                    ],
                                    temperature=0,
                                   )

    json_str = completion_result.choices[0].message.content

    # Parse JSON string and convert to Pydantic model
    json_data = json.loads(json_str)
    descriptions = Descriptions(**json_data)
    logging.info(f"Find tables based on: {descriptions.tables_descriptions}")
    tables_des = _find_tables(graph, descriptions.tables_descriptions)
    logging.info(f"Find tables based on columns: {descriptions.columns_descriptions}")
    tables_by_columns_des = _find_tables_by_columns(graph, descriptions.columns_descriptions)

    # table names for sphere and route extraction
    base_tables_names = [table[0] for table in tables_des]
    logging.info("Extracting tables by sphere")
    tables_by_sphere = _find_tables_sphere(graph, base_tables_names)
    logging.info(f"Extracting tables by connecting routes {base_tables_names}")
    tables_by_route, _ = find_connecting_tables(graph, base_tables_names)
    combined_tables = _get_unique_tables(tables_des + tables_by_columns_des + tables_by_route + tables_by_sphere)
    
    return True, combined_tables, db_description, [tables_des, tables_by_columns_des, tables_by_route, tables_by_sphere]

def _find_tables(graph, descriptions: List[TableDescription]) -> List[dict]:

    result = []
    for table in descriptions:

        # Get the table node from the graph
        embedding_result = Config.EMBEDDING_MODEL.embed(table.description)
        query_result = graph.query("""
                    CALL db.idx.vector.queryNodes(
                        'Table',
                        'embedding',
                        3,
                        vecf32($embedding)
                    ) YIELD node, score
                    MATCH (node)-[:BELONGS_TO]-(columns)
                    RETURN node.name, node.description, node.foreign_keys, collect({
                        columnName: columns.name,
                        description: columns.description,
                        dataType: columns.type,
                        keyType: columns.key,
                        nullable: columns.nullable
                    })
                    """,
                    {
                        'embedding': embedding_result[0]
                    })

        for node in query_result.result_set:
            if node not in result:
                result.append(node)
    
    return result

def _find_tables_sphere(graph, tables: List[str]) -> List[dict]:
    result = []
    for table_name in tables:
        query_result = graph.query("""
                    MATCH (node:Table {name: $name})
                    MATCH (node)-[:BELONGS_TO]-(column)-[:REFERENCES]-()-[:BELONGS_TO]-(table_ref)
                    WITH table_ref
                    MATCH (table_ref)-[:BELONGS_TO]-(columns)
                    RETURN table_ref.name, table_ref.description, table_ref.foreign_keys, collect({
                        columnName: columns.name,
                        description: columns.description,
                        dataType: columns.type,
                        keyType: columns.key,
                        nullable: columns.nullable
                    })
                    """,
                    {
                        'name': table_name
                    })
        for node in query_result.result_set:
            if node not in result:
                result.append(node)

    return result


def _find_tables_by_columns(graph, descriptions: List[ColumnDescription]) -> List[dict]:

    result = []
    for column in descriptions:

        # Get the table node from the graph
        embedding_result = Config.EMBEDDING_MODEL.embed(column.description)
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
                    table.foreign_keys,
                    collect({
                        columnName: columns.name,
                        description: columns.description,
                        dataType: columns.type,
                        keyType: columns.key,
                        nullable: columns.nullable
                    })
                    """,
                    {
                        'embedding': embedding_result[0]
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
        try:
            if table_name not in unique_tables:
                table_info[3] = [dict(od) for od in table_info[3]]
                table_info[2] = 'Foreign keys: ' + table_info[2]
                unique_tables[table_name] = table_info
        except:
            print(f"Error: {table_info}")
    
    # Return the values (the unique table info lists)
    return list(unique_tables.values())


def find_connecting_tables(graph, table_names: List[str]) -> Tuple[List[dict], List[str]]:
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
    result = []
    # Check all possible pairs of tables
    for i in range(len(table_names)):
        for j in range(i + 1, len(table_names)):  # This ensures i != j
            try:
                table1 = table_names[i]
                table2 = table_names[j]
                # Query to find all tables in the shortest paths between the pair
                query = """
                MATCH (a:Table {name: $table1}), (b:Table {name: $table2})  
                WITH a, b
                MATCH p=allShortestPaths((a)-[r*..9]-(b))
                RETURN nodes(p) as nodes
                """
                try:
                    paths = graph.query(query, {'table1': table1, 'table2': table2}, timeout=50).result_set
                except Exception as e:
                    print(f"Error querying graph: {e}")
                    continue
                if not paths:
                    continue
                # Extract table names from the paths
                for path in paths:
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
            except Exception as e:
                print(f"Error processing tables {table1} and {table2}: {e}")
                continue

    query_result = graph.query("""UNWIND $ids AS id 
                MATCH (n:Table)-[:BELONGS_TO]-(columns) 
                WHERE id(n)=id 
                RETURN n.name, n.description, n.foreign_keys, collect({
                        columnName: columns.name,
                        description: columns.description,
                        dataType: columns.type,
                        keyType: columns.key,
                        nullable: columns.nullable
                    })""", {'ids': list(all_connecting_tables_id)})
    for node in query_result.result_set:
            if node not in result:
                result.append(node)

    print(f"Connecting tables: {all_connecting_tables}")
    return result, list(all_connecting_tables)