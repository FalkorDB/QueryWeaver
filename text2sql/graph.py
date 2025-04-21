""" Module to handle the graph data loading into the database. """
import os
import json
from typing import List, Tuple, Dict, Any
from litellm import completion
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
        MATCH (d:Database)
        RETURN d.description
        """
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
                                    ],
                                    temperature=0,
                                    aws_profile_name=Config.AWS_PROFILE,
                                    aws_region_name=Config.AWS_REGION,
                                   )

    json_str = completion_result.choices[0].message.content

    # Parse JSON string and convert to Pydantic model
    json_data = json.loads(json_str)
    descriptions = Descriptions(**json_data)

    tables_des = _find_tables(graph, descriptions.tables_descriptions)
    tables_by_columns_des = _find_tables_by_columns(graph, descriptions.columns_descriptions)

    # table names for sphere and route extraction
    base_tables_names = [table[0] for table in tables_des]
    tables_by_sphere = _find_tables_sphere(graph, base_tables_names)
    tables_by_route, _ = find_connecting_tables(graph, base_tables_names) #list(set(base_tables_names + column_tables_names))
    combined_tables = _get_unique_tables(tables_des + tables_by_columns_des + tables_by_route + tables_by_sphere)
    formatted_schema = _format_schema(combined_tables)
    prompt = _build_prompt(user_query, formatted_schema, db_description)
    completion_result = completion(model=Config.COMPLETION_MODEL,
                                messages=[
                                    {
                                        "content": prompt,
                                        "role": "user"
                                    }
                                ],
                                temperature=0,
                                aws_profile_name=Config.AWS_PROFILE,
                                aws_region_name=Config.AWS_REGION,
                                )
    
    response = completion_result.choices[0].message.content
    analysis = _parse_response(response)
    return True, combined_tables, db_description, [tables_des, tables_by_columns_des, tables_by_route, tables_by_sphere], formatted_schema

def _find_tables(graph, descriptions: List[TableDescription]) -> List[dict]:

    result = []
    for table in descriptions:

        # Get the table node from the graph
        # embedding_result = embedding(model=Config.EMBEDDING_MODEL_NAME, input=[table.description], aws_profile_name=Config.AWS_PROFILE, aws_region_name=Config.AWS_REGION) # model.encode(table.description) #
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
                        type: columns.key_type,
                        key: columns.key
                    })
                    """,
                    {
                        'embedding': embedding_result[0] #.data[0].embedding #embedding_result.tolist() #embedding_result.data[0].embedding
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
                        type: columns.type,
                        key: columns.key
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
        # embedding_result = embedding(model=Config.EMBEDDING_MODEL_NAME, input=[column.description], aws_profile_name=Config.AWS_PROFILE, aws_region_name=Config.AWS_REGION)
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
                        type: columns.type,
                        key: columns.key
                    })
                    """,
                    {
                        'embedding': embedding_result[0] #.data[0].embedding #embedding_result.tolist() #embedding_result.data[0].embedding
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
                # prompt = "match (a:Table {name:$table1}), (b:Table {name:$table2}) WITH a, b MATCH p = (a)-[*1..6]-(b) RETURN nodes(p) LIMIT 1"
                # try:
                #     con = graph.query(prompt, {'table1': table1, 'table2': table2}, timeout=5).result_set
                # except Exception as e:
                #     print(f"Error querying graph: {e}")
                #     continue
                # if not con:
                #     continue
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
                        type: columns.type,
                        key: columns.key
                    })""", {'ids': list(all_connecting_tables_id)})
    for node in query_result.result_set:
            if node not in result:
                result.append(node)

    print(f"Connecting tables: {all_connecting_tables}")
    return result, list(all_connecting_tables)


def _format_schema(schema_data: List) -> str:
    """
    Format the schema data into a readable format for the prompt.
    
    Args:
        schema_data: Schema in the structure [...]
        
    Returns:
        Formatted schema as a string
    """
    formatted_schema = []
    
    for table_info in schema_data:
        table_name = table_info[0]
        table_description = table_info[1]
        foreign_keys = table_info[2]
        columns = table_info[3]
        
        # Format table header
        table_str = f"Table: {table_name} - {table_description}\n"
        
        # Format columns using the updated OrderedDict structure
        for column in columns:
            col_name = column.get("columnName", "")
            col_type = column.get("type", "")
            col_description = column.get("description", "")
            col_key = column.get("key", None)
            
            key_info = f", PRIMARY KEY" if col_key == "PK" else f", FOREIGN KEY" if col_key == "FK" else ""
            column_str = f"  - {col_name} ({col_type}{key_info}): {col_description}"
            table_str += column_str + "\n"
        
        # Format foreign keys
        if isinstance(foreign_keys, dict) and foreign_keys:
            table_str += "  Foreign Keys:\n"
            for fk_name, fk_info in foreign_keys.items():
                column = fk_info.get("column", "")
                ref_table = fk_info.get("referenced_table", "")
                ref_column = fk_info.get("referenced_column", "")
                table_str += f"  - {fk_name}: {column} references {ref_table}.{ref_column}\n"
        
        formatted_schema.append(table_str)
    
    return "\n".join(formatted_schema)

def _parse_response(response: str) -> Dict[str, Any]:
    """
    Parse Claude's response to extract the analysis.
    
    Args:
        response: Claude's response string
        
    Returns:
        Parsed analysis results
    """
    try:
        # Extract JSON from the response
        json_start = response.find('{')
        json_end = response.rfind('}') + 1
        json_str = response[json_start:json_end]
        
        # Parse the JSON
        analysis = json.loads(json_str)
        return analysis
    except (json.JSONDecodeError, ValueError) as e:
        # Fallback if JSON parsing fails
        return {
            "is_sql_translatable": False,
            "confidence": 0,
            "explanation": f"Failed to parse response: {str(e)}",
            "error": str(response)
        }

def _build_prompt(user_input: str, formatted_schema: str, db_description: str) -> str:
    """
    Build the prompt for Claude to analyze the query.
    
    Args:
        user_input: The natural language query from the user
        formatted_schema: Formatted database schema
        
    Returns:
        The formatted prompt for Claude
    """
    prompt = f"""
    <database_description>
    {db_description}
    </database_description>

    <database_schema>
    {formatted_schema}
    </database_schema>

    <user_query>
    {user_input}
    </user_query>

    You are an expert in database systems and natural language processing. Your task is to determine if the user query above can be translated into a valid SQL query given the database schema provided.

    Please analyze the query carefully and respond in the following JSON format:

    ```json
    {{
        "is_sql_translatable": true/false,
        "confidence": 0-100,
        "explanation": "Your explanation of why the query can or cannot be translated to SQL",
        "missing_information": ["list", "of", "missing", "information"] (if applicable),
        "ambiguities": ["list", "of", "ambiguities"] (if applicable),
        "potential_sql_structure": "High-level SQL structure (if applicable)"
    }}
    ```

    Your analysis should consider:
    1. Whether the query asks for information that exists in the database schema
    2. Whether the query's intent is clear enough to be expressed in SQL
    3. Whether there are any ambiguities that make SQL translation difficult
    4. Whether any required information is missing to form a complete SQL query
    5. Whether the necessary joins can be established using available foreign keys
    6. If there are multiple possible interpretations of the query

    Provide your response as valid, parseable JSON only.
    """
    return prompt