"""Module to handle the graph data loading into the database."""

import asyncio
import json
import logging
from itertools import combinations
from typing import Any, Dict, List, Tuple

from litellm import completion
from pydantic import BaseModel

from api.config import Config
from api.extensions import db


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


class TableDescription(BaseModel):
    """Represents a table description with name and description."""

    name: str
    description: str


class ColumnDescription(BaseModel):
    """Represents a column description with name and description."""

    name: str
    description: str


class Descriptions(BaseModel):
    """Container for table and column descriptions."""

    tables_descriptions: List[TableDescription]
    columns_descriptions: List[ColumnDescription]


async def get_db_description(graph_id: str) -> Tuple[str, str]:
    """
    Get the database description from the graph.
    
    Args:
        graph_id: The identifier for the graph.
        
    Returns:
        A tuple containing the database description and URL.
    """
    graph = db.select_graph(graph_id)
    query_result = await graph.query(
        """
        MATCH (d:Database)
        RETURN d.description, d.url
        """
    )

    if not query_result.result_set:
        return (
            "No description available for this database.",
            "No URL available for this database."
        )

    result = query_result.result_set[0]
    return result[0], result[1]

async def _query_graph(
    graph,
    query: str,
    params: Dict[str, Any] = None,
    timeout: int = 120
) -> List[Any]:
    """
    Run a graph query asynchronously and return the result set.

    Args:
        graph: The graph database instance.
        query: The query string to execute.
        params: Optional parameters for the query.
        timeout: Query timeout in seconds.

    Returns:
        The result set from the query.
    """
    result = await graph.query(query, params or {}, timeout=timeout)
    return result.result_set


async def _embed_and_query(
    graph,
    description: str,
    query: str
) -> List[Dict[str, Any]]:
    """
    Embed a description, run the query, and return unique results.

    Args:
        graph: The graph database instance.
        description: The description to embed.
        query: The query string to execute.

    Returns:
        List of query results.
    """
    embedding_result = Config.EMBEDDING_MODEL.embed(description)
    rows = await _query_graph(
        graph,
        query,
        {"embedding": embedding_result[0]},
    )
    return rows

async def _find_tables(
    graph,
    descriptions: List[TableDescription]
) -> List[Dict[str, Any]]:
    """
    Find tables based on table descriptions.

    Args:
        graph: The graph database instance.
        descriptions: List of table descriptions to search for.

    Returns:
        List of matching table information.
    """
    query = """
        CALL db.idx.vector.queryNodes('Table','embedding',3,vecf32($embedding))
        YIELD node, score
        MATCH (node)-[:BELONGS_TO]-(columns)
        RETURN node.name, node.description, node.foreign_keys, collect({
            columnName: columns.name,
            description: columns.description,
            dataType: columns.type,
            keyType: columns.key,
            nullable: columns.nullable
        })
    """
    tasks = [
        _embed_and_query(graph, table.description, query)
        for table in descriptions
    ]
    results = await asyncio.gather(*tasks)
    return [row for rows in results for row in rows]


async def _find_tables_by_columns(
    graph,
    descriptions: List[ColumnDescription]
) -> List[Dict[str, Any]]:
    """
    Find tables based on column descriptions.

    Args:
        graph: The graph database instance.
        descriptions: List of column descriptions to search for.

    Returns:
        List of matching table information.
    """
    query = """
        CALL db.idx.vector.queryNodes('Column','embedding',3,vecf32($embedding))
        YIELD node, score
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
    """
    tasks = [
        _embed_and_query(graph, col.description, query)
        for col in descriptions
    ]
    results = await asyncio.gather(*tasks)
    return [row for rows in results for row in rows]


async def _find_tables_sphere(
    graph,
    tables: List[str]
) -> List[Dict[str, Any]]:
    """
    Find tables in the sphere of influence of given tables.

    Args:
        graph: The graph database instance.
        tables: List of table names to find connections for.

    Returns:
        List of connected table information.
    """
    query = """
        MATCH (node:Table {name: $name})
        MATCH (node)-[:BELONGS_TO]-(column)-[:REFERENCES]-()-[:BELONGS_TO]-(table_ref)
        WITH table_ref
        MATCH (table_ref)-[:BELONGS_TO]-(columns)
        RETURN table_ref.name, table_ref.description, table_ref.foreign_keys,
               collect({
                   columnName: columns.name,
                   description: columns.description,
                   dataType: columns.type,
                   keyType: columns.key,
                   nullable: columns.nullable
               })
    """
    tasks = [_query_graph(graph, query, {"name": name}) for name in tables]
    results = await asyncio.gather(*tasks)
    return [row for rows in results for row in rows]


async def _find_connecting_tables(
    graph,
    table_names: List[str]
) -> List[Dict[str, Any]]:
    """
    Find all tables that form connections between pairs of tables.

    Args:
        graph: The graph database instance.
        table_names: List of table names to find connections between.

    Returns:
        List of connecting table information.
    """
    pairs = [list(pair) for pair in combinations(table_names, 2)]
    if not pairs:
        return []
    
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
    RETURN target_table.name, target_table.description, target_table.foreign_keys, columns
    """
    result = await _query_graph(graph, query, {"pairs": pairs}, timeout=300)
    return result


async def find(
    graph_id: str,
    queries_history: List[str],
    db_description: str = None
) -> List[Dict[str, Any]]:
    """
    Find the tables and columns relevant to the user's query.

    Args:
        graph_id: The identifier for the graph database.
        queries_history: List of previous queries, with the last one being current.
        db_description: Optional description of the database.

    Returns:
        Combined list of relevant tables.
    """
    graph = db.select_graph(graph_id)
    user_query = queries_history[-1]
    previous_queries = queries_history[:-1]

    logging.info(
        "Calling LLM to find relevant tables/columns for query: %s",
        user_query
    )

    completion_result = completion(
        model=Config.COMPLETION_MODEL,
        response_format=Descriptions,
        messages=[
            {
                "role": "system",
                "content": Config.FIND_SYSTEM_PROMPT.format(
                    db_description=db_description
                )
            },
            {
                "role": "user",
                "content": json.dumps({
                    "previous_user_queries": previous_queries,
                    "user_query": user_query
                })
            },
        ],
        temperature=0,
    )

    json_data = json.loads(completion_result.choices[0].message.content)
    descriptions = Descriptions(**json_data)

    tables_des = await _find_tables(graph, descriptions.tables_descriptions)
    tasks = [
        _find_tables_by_columns(graph, descriptions.columns_descriptions),
        _find_tables_sphere(graph, [t[0] for t in tables_des]),
        _find_connecting_tables(graph, [t[0] for t in tables_des])
    ]
    tables_by_columns_des, tables_by_sphere, tables_by_route = await asyncio.gather(
        *tasks
    )

    combined_tables = _get_unique_tables(
        tables_des + tables_by_columns_des + tables_by_route + tables_by_sphere
    )

    return combined_tables


def _get_unique_tables(tables_list: List[List[Any]]) -> List[List[Any]]:
    """
    Remove duplicate tables from the combined results.

    Args:
        tables_list: List of table information lists.

    Returns:
        List of unique table information.
    """
    # Dictionary to store unique tables with the table name as the key
    unique_tables = {}

    for table_info in tables_list:
        table_name = table_info[0]  # The first element is the table name

        # Only add if this table name hasn't been seen before
        try:
            if table_name not in unique_tables:
                # Convert ordered dictionaries to regular dictionaries
                table_info[3] = [dict(od) for od in table_info[3]]
                # Format foreign keys description
                table_info[2] = f"Foreign keys: {table_info[2]}"
                unique_tables[table_name] = table_info
        except (IndexError, TypeError) as e:
            logging.error("Error processing table info %s: %s", table_info, e)

    # Return the values (the unique table info lists)
    return list(unique_tables.values())
