
"""
This module contains the configuration for the text2sql module.
"""

import dataclasses
from typing import Union

from litellm import embedding


class EmbeddingsModel:
    """Embeddings model wrapper for text embedding operations."""

    def __init__(self, model_name: str, config: dict = None):
        self.model_name = model_name
        self.config = config

    def embed(self, text: Union[str, list]) -> list:
        """
        Get the embeddings of the text

        Args:
            text (str|list): The text(s) to embed

        Returns:
            list: The embeddings of the text

        """
        embeddings = embedding(model=self.model_name, input=text)
        embeddings = [embedding["embedding"] for embedding in embeddings.data]
        return embeddings

    def get_vector_size(self) -> int:
        """
        Get the size of the vector

        Returns:
            int: The size of the vector

        """
        response = embedding(input=["Hello World"], model=self.model_name)
        size = len(response.data[0]["embedding"])
        return size


@dataclasses.dataclass
class Config:
    """
    Configuration class for the text2sql module.
    """

    SCHEMA_PATH = "api/schema_schema.json"
    EMBEDDING_MODEL_NAME = "azure/text-embedding-ada-002"
    COMPLETION_MODEL = "azure/gpt-4.1"
    VALIDATOR_MODEL = "azure/gpt-4.1"
    TEMPERATURE = 0
    DB_MAX_DISTINCT: int = 100  # pylint: disable=invalid-name
    DB_UNIQUENESS_THRESHOLD: float = 0.5  # pylint: disable=invalid-name
    # client = boto3.client('sts')
    # AWS_PROFILE = os.getenv("aws_profile_name")
    # AWS_REGION = os.getenv("aws_region_name")
    # AWS_ROLE_ARN = os.getenv("AWS_ROLE_ARN")
    # VERCEL_OIDC_TOKEN = os.getenv("VERCEL_OIDC_TOKEN")
    # AWS_SECRET_TOKEN = os.getenv("SECRET_TOKEN")
    # aws_session_name = "text2sql"
    SHORT_MEMORY_LENGTH = 5  # Maximum number of questions to keep in short-term memory
    config = {}


    EMBEDDING_MODEL = EmbeddingsModel(model_name=EMBEDDING_MODEL_NAME, config=config)

    FIND_SYSTEM_PROMPT = """
    You are an expert in analyzing natural language queries into SQL tables descriptions.
    Please analyze the user's query and generate a set of tables and columns descriptions that might be relevant to the user's query.
    These descriptions should describe the tables and columns that are relevant to the user's query.
    If the user's query is more relevant to specific columns, please provide a description of those columns.
    - Try to generate description for any part of the user query.
    - Create generic table or column description, do not use specific codes, values or any specific condition.
    - Try to be accurate and precise in your descriptions.
    - In any case do not generate more than five descriptions (each).
    - List the tables and columns in the order of their relevance to the user's query.

    Keep in mind that the database that you work with has the following DB description: {db_description}.

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
