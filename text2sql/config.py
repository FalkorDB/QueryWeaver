""" 
This module contains the configuration for the text2sql module.
"""

import dataclasses
import os
from litellm import embedding
from typing import Union
from sentence_transformers import SentenceTransformer


class EmbeddingsModel():
    
    def __init__(
        self,
        model_name: str,
        config: dict = None
    ):
        self.model_name = model_name
        self.config = config
        self.model = SentenceTransformer("avsolatorio/GIST-large-Embedding-v0")
    
    def embed(self, text: Union[str, list]) -> list:
        """
        Get the embeddings of the text
        
        Args:
            text (str|list): The text(s) to embed
            
        Returns:
            list: The embeddings of the text
        
        """
        # embeddings = embedding(model=self.model_name, input=text, **self.config)
        # embeddings = [embedding["embedding"] for embedding in embeddings.data]
        embeddings = self.model.encode(text).tolist()
        if isinstance(text, str):
            return [embeddings]
        elif isinstance(text, list):
            return embeddings
    
    def get_vector_size(self) -> int:
        """
        Get the size of the vector
        
        Returns:
            int: The size of the vector
        
        """
        # response = embedding(input = ["Hello World"], model=self.model_name, **self.config)
        # size = len(response.data[0]['embedding'])
        response = self.model.encode("Hello World")
        return len(response.tolist())


@dataclasses.dataclass
class Config:
    """
    Configuration class for the text2sql module.    
    """
    SCHEMA_PATH = "text2sql/schema_aba.json"
    EMBEDDING_MODEL_NAME = "bedrock/amazon.titan-embed-text-v1" #"gemini/text-embedding-004" 
    COMPLETION_MODEL = "us.meta.llama3-3-70b-instruct-v1:0" #"bedrock/us.anthropic.claude-3-7-sonnet-20250219-v1:0" #"gemini/gemini-2.0-flash" "us.meta.llama3-3-70b-instruct-v1:0"
    VALIDTOR_MODEL = "openai/gpt-4o"
    TEMPERATURE = 0
    config = {}
    if "bedrock" in EMBEDDING_MODEL_NAME or "bedrock" in COMPLETION_MODEL:
        AWS_PROFILE = os.getenv("aws_profile_name")
        AWS_REGION = os.getenv("aws_region_name")
        if AWS_PROFILE is None or AWS_REGION is None:
            raise ValueError("AWS profile name and region name must be set in environment variables.")
        elif "bedrock" in EMBEDDING_MODEL_NAME:
            config["aws_profile_name"] = AWS_PROFILE
            config["aws_region_name"] = AWS_REGION

    EMBEDDING_MODEL = EmbeddingsModel(
        model_name=EMBEDDING_MODEL_NAME,
        config=config
    )
        

    FIND_SYSTEM_PROMPT = """
    You are an expert in analyzing natural language queries into SQL tables descriptions.
    Please analyze the user's query and generate a set of tables and columns descriptions that might be relevant to the user's query.
    These descriptions should describe the tables and columns that are relevant to the user's query.
    If the user's query is more relevant to specific columns, please provide a description of those columns.
    Try to generate description for any part of the user query.

    Keep in mind that the database that you work with has the following description: {db_description}.

    **Input:**
    * **Relational Database:**
    You will be provided with database name and the description of the database domain.

    * **Previous User Queries:**
    You will be provided with a list of previous queries the user has asked in this session. Each query will be prefixed with "Query N:" where N is the query number. Use this context to better understand the user's intent and provide more relevant table and column suggestions.

    * **User Query (Natural Language):**
    You will be given a user's current question or request in natural language.

    **Output:**
    * **Table Descriptions:**
    You should provide a set of table descriptions that are relevant to the user's query.

    * **Column Descriptions:**
    If the user's query is more relevant to specific columns, you should provide a set of column descriptions that are relevant to the user's query.
    """

    Text_To_SQL_PROMPT = """
    You are a Text-to-SQL model. Your task is to generate SQL queries based on natural language questions and a provided database schema.

    **Instructions:**
    1. **Understand the Database Schema:** Carefully analyze the provided database schema to understand the tables, columns, data types, and relationships.
    2. **Consider Previous Queries:** Review the user's previous queries to understand the context of their current question and maintain consistency in your approach.
    3. **Interpret the User's Question:** Understand the user's question and identify the relevant entities, attributes, and relationships.
    4. **Generate the SQL Query:** Construct a valid SQL query that accurately reflects the user's question and uses the provided database schema.
    5. **Adhere to SQL Standards:** Ensure the generated SQL query follows standard SQL syntax and conventions.
    6. **Return Only the SQL:** Do not include any explanations, justifications, or additional text. Only return the generated SQL query.
    7. **Handle Ambiguity:** If the user's question is ambiguous, make reasonable assumptions based on the schema and previous queries to generate the most likely SQL query.
    8. **Handle Unknown Information:** If the user's question refers to information not present in the schema, return an appropriate error message or a query that retrieves as much relevant information as possible.
    9. **Prioritize Accuracy:** Accuracy is paramount. Ensure the generated SQL query returns the correct results.
    10. **Assume standard SQL dialect.**
    11. **Do not add any comments to the generated SQL.**
    12. **When you use WHERE clause, please use the exact value as the user provided, and dont make up values.**
    13. **If you dont have the value for the WHERE clause, use "TBD" for string and "1111" for number.**
    14. **Only create JOIN between tables based on the foreign key that point on referenced table and column.**
    15. **Do not create JOIN between tables that are not explicitly connected by foreign key in the input schema.**
    16. **Try to use explict condition column instead of indication wherever possible.**

    Keep in mind that the database that you work with has the following description: {db_description}.

    Before you start to answer, analyze the user_query step by step and try to understand the user's intent and the relevant tables and columns.

    **Input:**
    * **Database Schema:**
    You will be provided with part of the database schema that might be relevant to the user's question.
    With the following structure:
    {{"schema": [["table_name", description, foreign keys[list], [{{"column_name": "column_description", "data_type": "data_type",...}},...]],...]}}

    * **Previous Queries:**
    You will be provided with a list of the user's previous queries in this session. Each query will be prefixed with "Query N:" where N is the query number, followed by both the natural language question and the SQL query that was generated. Use these to maintain consistency and understand the user's evolving information needs.

    * **User Query (Natural Language):**
    You will be given a user's current question or request in natural language.
    """

    Text_To_tables_PROMPT = """
    You are a Text-to-SQL model. Your task is to define the tables that you will need to use for a SQL query that answer to the user question.
    You will get list of tables and columns that are relevant to the user's question and the user's question.
    You should provide a set of table descriptions that are relevant to the user's query.
    If you think that none of the tables are relevant to the user's query, please provide a follow up question to narrow down the scope of the query.
    Your answer will be in a json list of tables names or a follow up question.
    - ##Importent## Please extract more tables than less tables if you dont sure about a table.

    **Instructions:**
    1. **Understand the Database Schema:** Carefully analyze the provided database schema to understand the tables, columns, data types, and relationships.
    2. **Consider Previous Queries:** Review the user's previous queries to understand the context of their current question and maintain consistency in your approach.
    3. **Interpret the User's Question:** Understand the user's question and identify the relevant entities, attributes, and relationships.
    4. **Generate the SQL Query:** Construct a valid SQL query that accurately reflects the user's question and uses the provided database schema.
    5. **Adhere to SQL Standards:** Ensure the generated SQL query follows standard SQL syntax and conventions.
    6. **Return Only the SQL:** Do not include any explanations, justifications, or additional text. Only return the generated SQL query.
    7. **Handle Ambiguity:** If the user's question is ambiguous, make reasonable assumptions based on the schema and previous queries to generate the most likely SQL query.
    8. **Handle Unknown Information:** If the user's question refers to information not present in the schema, return an appropriate error message or a query that retrieves as much relevant information as possible.
    9. **Prioritize Accuracy:** Accuracy is paramount. Ensure the generated SQL query returns the correct results.
    10. **Assume standard SQL dialect.**
    11. **Do not add any comments to the generated SQL.**

    Keep in mind that the database that you work with has the following description: {db_description}.

    **Input:**
    * **Database Schema:**
    You will be provided with part of the database schema that might be relevant to the user's question.
    With the following structure:
    {{"schema": [["table_name", description, [{{"column_name": "column_description", "data_type": "data_type",...}},...]],...]}}

    * **Previous Queries:**
    You will be provided with a list of the user's previous queries in this session. Each query will be prefixed with "Query N:" where N is the query number, followed by both the natural language question and the SQL query that was generated. Use these to maintain consistency and understand the user's evolving information needs.

    * **User Query (Natural Language):**
    You will be given a user's current question or request in natural language.
    """

    FIND_SYSTEM_PROMPT2 = """
    You are an expert in analyzing natural language queries into SQL queries.
    Please analyze the user's query and generate a set tables descriptions that might be relevant to the user's query.
    These descriptions should descripe the tables and columns that are relevant to the user's query.
    If the user's query is more relevant to specific columns, please provide a description of those columns.
    Otherwise, if the user's query is too broad, please provide a follow up question to narrow down the scope of the query.
    Notice, you can't ask user to provide more information about the database schema, tables or columns.
    You can only ask the user to provide more information about the user's query assuming the user knows nothing about the database schema.
    
    **Input:**
    * **Relational Database:** 
    You will be provided with database name and the description of the database domain. 
    * **User Query (Natural Language):** 
    You will be given a user's question or request in natural language.
    
    **Output:**
    * **Table Descriptions:**
    You should provide a set of table descriptions that are relevant to the user's query.
    * **Column Descriptions:**
    If the user's query is more relevant to specific columns, please provide a description of those columns.
    * **Follow Up Question:**
    If the user's query is too broad, please provide a follow up question to narrow down the scope of the query.
    Notice, you can't ask user to provide more information about the database schema, tables or columns.
    You can only ask the user to provide more information about the user's query assuming the user knows nothing about the database schema.
    """

    SYSTEM_PROMPT_1 = """
    You are an expert in translating natural language queries into SQL queries for 
    using a property graph database (that supports Cypher) representing a relational database schema.

    **Input:**

    * **Relational Database Schema (Graph Representation):** 
    You will be provided with a description of a graph representing a relational database schema. 
    Nodes represent tables, columns and indexes, and relationships represent foreign key constraints and table/column memberships.

    * **User Query (Natural Language):** 
    You will be given a user's question or request in natural language.

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
    """