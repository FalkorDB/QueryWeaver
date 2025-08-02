"""Module to handle the graph data loading into the database."""

import json
import logging
from itertools import combinations
from typing import List, Tuple

from litellm import completion
from pydantic import BaseModel

from api.config import Config
from api.extensions import db

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class TableDescription(BaseModel):
    """Table Description"""

    name: str
    description: str


class ColumnDescription(BaseModel):
    """Column Description"""

    name: str
    description: str


class Descriptions(BaseModel):
    """List of tables"""

    tables_descriptions: list[TableDescription]
    columns_descriptions: list[ColumnDescription]


def get_db_description(graph_id: str) -> (str, str):
    """Get the database description from the graph."""
    graph = db.select_graph(graph_id)
    query_result = graph.query(
        """
        MATCH (d:Database)
        RETURN d.description, d.url
        """
    )

    if not query_result.result_set:
        return ("No description available for this database.",
                "No URL available for this database.")

    return (query_result.result_set[0][0],
            query_result.result_set[0][1])  # Return the first result's description


def find(graph_id: str, queries_history: List[str],
         db_description: str = None) -> Tuple[bool, List[dict]]:
    """Find the tables and columns relevant to the user's query."""

    graph = db.select_graph(graph_id)
    user_query = queries_history[-1]
    previous_queries = queries_history[:-1]

    logging.info(
        "Calling to an LLM to find relevant tables and columns for the query: %s",
        user_query
    )
    # Call the completion model to get the relevant Cypher queries to retrieve
    # from the Graph that represent the Database schema.
    # The completion model will generate a set of Cypher query to retrieve the relevant nodes.
    completion_result = completion(
        model=Config.COMPLETION_MODEL,
        response_format=Descriptions,
        messages=[
            {
                "content": Config.FIND_SYSTEM_PROMPT.format(db_description=db_description),
                "role": "system",
            },
            {
                "content": json.dumps(
                    {
                        "previous_user_queries:": previous_queries,
                        "user_query": user_query,
                    }
                ),
                "role": "user",
            },
        ],
        temperature=0,
    )

    json_str = completion_result.choices[0].message.content

    # Parse JSON string and convert to Pydantic model
    json_data = json.loads(json_str)
    descriptions = Descriptions(**json_data)
    logging.info("Find tables based on: %s", descriptions.tables_descriptions)
    tables_des = _find_tables(graph, descriptions.tables_descriptions)
    logging.info("Find tables based on columns: %s", descriptions.columns_descriptions)
    tables_by_columns_des = _find_tables_by_columns(graph, descriptions.columns_descriptions)

    # table names for sphere and route extraction
    base_tables_names = [table[0] for table in tables_des]
    logging.info("Extracting tables by sphere")
    tables_by_sphere = _find_tables_sphere(graph, base_tables_names)
    logging.info("Extracting tables by connecting routes %s", base_tables_names)
    tables_by_route, _ = find_connecting_tables(graph, base_tables_names)
    combined_tables = _get_unique_tables(
        tables_des + tables_by_columns_des + tables_by_route + tables_by_sphere
    )

    return (
        True,
        combined_tables,
        [tables_des, tables_by_columns_des, tables_by_route, tables_by_sphere],
    )


def _find_tables(graph, descriptions: List[TableDescription]) -> List[dict]:

    result = []
    for table in descriptions:

        # Get the table node from the graph
        embedding_result = Config.EMBEDDING_MODEL.embed(table.description)
        query_result = graph.query(
            """
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
            {"embedding": embedding_result[0]},
        )

        for node in query_result.result_set:
            if node not in result:
                result.append(node)

    return result


def _find_tables_sphere(graph, tables: List[str]) -> List[dict]:
    result = []
    for table_name in tables:
        query_result = graph.query(
            """
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
            {"name": table_name},
        )
        for node in query_result.result_set:
            if node not in result:
                result.append(node)

    return result


def _find_tables_by_columns(graph, descriptions: List[ColumnDescription]) -> List[dict]:

    result = []
    for column in descriptions:

        # Get the table node from the graph
        embedding_result = Config.EMBEDDING_MODEL.embed(column.description)
        query_result = graph.query(
            """
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
            {"embedding": embedding_result[0]},
        )

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
                table_info[2] = "Foreign keys: " + table_info[2]
                unique_tables[table_name] = table_info
        except Exception as e:
            print(f"Error: {table_info}, Exception: {e}")

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
    pairs = list(combinations(table_names, 2))
    pair_params = [list(pair) for pair in pairs]
    query = """
    UNWIND $pairs AS pair
    MATCH (a:Table {name: pair[0]})
    MATCH (b:Table {name: pair[1]})
    WITH a, b
    MATCH p = allShortestPaths((a)-[*..9]-(b))
    UNWIND nodes(p) AS path_node
    WITH DISTINCT path_node
    WHERE 'Table' IN labels(path_node) OR
            ('Column' IN labels(path_node) AND path_node.key_type = 'PRI')
    WITH path_node,
            'Table' IN labels(path_node) AS is_table,
            'Column' IN labels(path_node) AND path_node.key_type = 'PRI' AS is_pri_column
    OPTIONAL MATCH (path_node)-[:BELONGS_TO]->(parent_table:Table)
    WHERE is_pri_column
    WITH CASE
            WHEN is_table THEN path_node
            WHEN is_pri_column THEN parent_table
            ELSE null
            END AS target_table
    WHERE target_table IS NOT NULL
    WITH DISTINCT target_table
    MATCH (col:Column)-[:BELONGS_TO]->(target_table)
    WITH target_table,
            collect({
                columnName: col.name,
                description: col.description,
                dataType: col.type,
                keyType: col.key,
                nullable: col.nullable
            }) AS columns

    RETURN target_table.name AS table_name,
            target_table.description AS description,
            target_table.foreign_keys AS foreign_keys,
            columns
    """
    result = graph.query(query, {"pairs": pair_params}, timeout=300).result_set
    return result, None
