"""Analysis agent for analyzing user queries and generating database analysis."""

from typing import List
from litellm import completion
from api.config import Config
from .utils import BaseAgent, parse_response


class AnalysisAgent(BaseAgent):
    # pylint: disable=too-few-public-methods
    """Agent for analyzing user queries and generating database analysis."""


    def get_analysis(  # pylint: disable=too-many-arguments, too-many-positional-arguments
        self,
        user_query: str,
        combined_tables: list,
        db_description: str,
        instructions: str | None = None,
        memory_context: str | None = None,
        database_type: str | None = None,
    ) -> dict:
        """Get analysis of user query against database schema."""
        formatted_schema = self._format_schema(combined_tables)
        # Add system message with database type if not already present
        if not self.messages or self.messages[0].get("role") != "system":
            self.messages.insert(0, {
                "role": "system",
                "content": (
                    f"You are a SQL expert. TARGET DATABASE: "
                    f"{database_type.upper() if database_type else 'UNKNOWN'}"
                )
            })

        prompt = self._build_prompt(
            user_query, formatted_schema, db_description,
            instructions, memory_context, database_type
        )
        self.messages.append({"role": "user", "content": prompt})
        completion_result = completion(
            model=Config.COMPLETION_MODEL,
            messages=self.messages,
            temperature=0,
        )

        response = completion_result.choices[0].message.content
        analysis = parse_response(response)
        if isinstance(analysis["ambiguities"], list):
            analysis["ambiguities"] = [
                item.replace("-", " ") for item in analysis["ambiguities"]
            ]
            analysis["ambiguities"] = "- " + "- ".join(analysis["ambiguities"])
        if isinstance(analysis["missing_information"], list):
            analysis["missing_information"] = [
                item.replace("-", " ") for item in analysis["missing_information"]
            ]
            analysis["missing_information"] = "- " + "- ".join(
                analysis["missing_information"]
            )
        self.messages.append({"role": "assistant", "content": analysis["sql_query"]})
        return analysis

    def _format_schema(self, schema_data: List) -> str:
        """
        Format the schema data into a readable format for the prompt.

        Args:
            schema_data: Schema in the structure [...]

        Returns:
            Formatted schema as a string
        """
        formatted_schema = []

        for table_info in schema_data:
            table_str = self._format_single_table(table_info)
            formatted_schema.append(table_str)

        return "\n".join(formatted_schema)

    def _format_single_table(self, table_info: List) -> str:
        """
        Format a single table's information.

        Args:
            table_info: Table information in the structure 
                       [name, description, foreign_keys, columns]

        Returns:
            Formatted table string
        """
        table_name = table_info[0]
        table_description = table_info[1]
        foreign_keys = table_info[2]
        columns = table_info[3]

        # Format table header
        table_str = f"Table: {table_name} - {table_description}\n"

        # Format columns
        table_str += self._format_table_columns(columns)

        # Format foreign keys
        table_str += self._format_foreign_keys(foreign_keys)

        return table_str

    def _format_table_columns(self, columns: List) -> str:
        """
        Format table columns information.

        Args:
            columns: List of column dictionaries

        Returns:
            Formatted columns string
        """
        columns_str = ""
        for column in columns:
            column_str = self._format_single_column(column)
            columns_str += column_str + "\n"
        return columns_str

    def _format_single_column(self, column: dict) -> str:
        """
        Format a single column's information.

        Args:
            column: Column dictionary with metadata

        Returns:
            Formatted column string
        """
        col_name = column.get("columnName", "")
        col_type = column.get("dataType", None)
        col_description = column.get("description", "")
        col_key = column.get("keyType", None)
        nullable = column.get("nullable", False)

        key_info = (
            ", PRIMARY KEY"
            if col_key == "PRI"
            else ", FOREIGN KEY" if col_key == "FK" else ""
        )
        return (f"  - {col_name} ({col_type},{key_info},{col_key},"
               f"{nullable}): {col_description}")

    def _format_foreign_keys(self, foreign_keys: dict) -> str:
        """
        Format foreign keys information.

        Args:
            foreign_keys: Dictionary of foreign key information

        Returns:
            Formatted foreign keys string
        """
        if not isinstance(foreign_keys, dict) or not foreign_keys:
            return ""

        fk_str = "  Foreign Keys:\n"
        for fk_name, fk_info in foreign_keys.items():
            column = fk_info.get("column", "")
            ref_table = fk_info.get("referenced_table", "")
            ref_column = fk_info.get("referenced_column", "")
            fk_str += f"  - {fk_name}: {column} references {ref_table}.{ref_column}\n"

        return fk_str

    def _build_prompt(   # pylint: disable=too-many-arguments, too-many-positional-arguments, disable=line-too-long
        self, user_input: str, formatted_schema: str,
        db_description: str, instructions, memory_context: str | None = None,
        database_type: str | None = None,
    ) -> str:
        """
        Build the prompt for Claude to analyze the query.

        Args:
            user_input: The natural language query from the user
            formatted_schema: Formatted database schema
            db_description: Description of the database
            instructions: Custom instructions for the query
            memory_context: User and database memory context from previous interactions
            database_type: Target database type (sqlite, postgresql, mysql, etc.)

        Returns:
            The formatted prompt for Claude
        """

        # Include memory context in the prompt if available
        memory_section = ""
        if memory_context and memory_context.strip():
            memory_section = f"""
            <memory_context>
            The following information contains relevant context from previous interactions:
            
            {memory_context.strip()}
            
            Use this context to:
            1. Better understand the user's preferences and working style
            2. Leverage previous learnings about this database
            3. Learn from SUCCESSFUL QUERIES patterns and apply similar approaches
            4. Avoid FAILED QUERIES patterns and the errors they caused
            5. Provide more personalized and context-aware SQL generation
            6. Consider any patterns or preferences the user has shown in past interactions
            </memory_context>
            """

        prompt = f"""
            You must strictly follow the instructions below. Deviations will result in a penalty to your confidence score.

            TARGET DATABASE: {database_type.upper() if database_type else 'UNKNOWN'}

            MANDATORY RULES:
            - Always explain if you cannot fully follow the instructions.
            - Always reduce the confidence score if instructions cannot be fully applied.
            - Never skip explaining missing information, ambiguities, or instruction issues.
            - Respond ONLY in strict JSON format, without extra text.
            - If the query relates to a previous question, you MUST take into account the previous question and its answer, and answer based on the context and information provided so far.
            - CRITICAL: When table or column names contain special characters (especially dashes/hyphens like '-'), you MUST wrap them in double quotes for PostgreSQL (e.g., "table-name") or backticks for MySQL (e.g., `table-name`). This is NON-NEGOTIABLE.

            If the user is asking a follow-up or continuing question, use the conversation history and previous answers to resolve references, context, or ambiguities. Always base your analysis on the cumulative context, not just the current question.

            Your output JSON MUST contain all fields, even if empty (e.g., "missing_information": []).

            ---

            Now analyze the user query based on the provided inputs:

            <database_description>
            {db_description}
            </database_description>

            <instructions>
            {instructions}
            </instructions>

            <database_schema>
            {formatted_schema}
            </database_schema>
            {memory_section}
            <conversation_history>
            {self.messages}
            </conversation_history>

            <user_query>
            {user_input}
            </user_query>

            ---

            Your task:

            - Analyze the query's translatability into SQL according to the instructions.
            - Apply the instructions explicitly.
            - You MUST NEVER use application-level identifiers that are email-based or encoded emails.
            - Penalize confidence appropriately if any part of the instructions is unmet.
            - When there several tables that can be used to answer the question, you can combine them in a single SQL query.
            - Use the memory context to inform your SQL generation, considering user preferences and previous database interactions.
            - For personal queries ("I", "my", "me", "I have"), FIRST check if user identification exists in memory context (user name, previous personal queries, etc.) before determining translatability.
            - NEVER assume general/company-wide interpretations for personal pronouns when NO user context is available.

            PERSONAL QUESTIONS HANDLING:
            - Personal queries using "I", "my", "me", "I have", "I own", etc. are valid database queries only if user identification is present (user name, user ID, organization, etc.).
            - FIRST check memory context and schema for user identifiers (user_id, customer_id, manager_id, etc.) and user name/identity information.
            - If memory context contains user identification (like user name, employee name, or previous successful personal queries), then personal queries ARE translatable.
            - If user identification is missing for personal queries AND not found in memory context, add "User identification required for personal query" to missing_information.
            - CRITICAL: If missing personalization information is a significant part of the user query (e.g., the query is primarily about "my orders", "my account", "my data", "employees I have", "how many X do I have") AND no user identification exists in memory context or schema, set "is_sql_translatable" to false.
            - DO NOT assume general/company-wide interpretations for personal pronouns when NO user context is available.
            - Mark as translatable if sufficient user context exists in memory context to identify the specific user, even for primarily personal queries.
            - If a query depends on personal context (e.g., "my", "me", "birthday", "account", "orders") 
                and the required information (user_id, birthday, etc.) is missing in memory context or schema:
                    - Set "is_sql_translatable" to false
                    - Add the required information to "missing_information"
                    - Leave "sql_query" as an empty string ("")
                    - Do NOT fabricate placeholders (e.g., <USER_ID>, <USER_BIRTHDAY>, <PLACEHOLDER>)

            Provide your output ONLY in the following JSON structure:

            ```json
            {{
                "is_sql_translatable": true or false,
                "query_analysis": "OUTPUT: <exact SELECT columns required by the question (no extra columns); if the question says 'list/show all' but does not name columns, select minimal identifying columns>.\\nOUTPUT GRAIN: <state only if explicitly requested; otherwise write N/A>.\\nMETRIC: <write the exact metric expression only if explicitly requested/defined; otherwise N/A (direct column retrieval)>.\\nGRAIN CHECK: <MATCH|MISMATCH|N/A>.\\nAGGREGATION DECISION: <NONE|SUM|AVG|COUNT|MIN|MAX> (NONE unless explicitly requested).\\nRANKING/LIMIT: <ORDER BY ... LIMIT ... | NONE>.\\nFILTERS: <predicates explicitly justified by the question> (each predicate must be a concrete SQL condition using =, >, <, BETWEEN, IN; do NOT use LIKE/contains unless explicitly requested).",
                "explanation": ("Detailed explanation why the query can or cannot be "
                               "translated, mentioning instructions explicitly and "
                               "referencing conversation history if relevant"),
                "sql_query": ("ONE valid SQL query for the target database that follows "
                             "all rules above (use previous answers only if the question "
                             "is a continuation)"),
                "tables_used": ["list", "of", "tables", "used", "in", "the", "query",
                               "with", "the", "relationships", "between", "them"],
                "missing_information": ["list", "of", "missing", "information"],
                "ambiguities": ["list", "of", "ambiguities"],
                "confidence": integer between 0 and 100
            }}

            Evaluation Guidelines:

            1. Verify if all requested information exists in the schema.
            2. Check if the query's intent is clear enough for SQL translation.
            3. Identify any ambiguities in the query or instructions.
            4. List missing information explicitly if applicable.
            5. When critical information is missing make the is_sql_translatable false and add it to missing_information.
            6. Confirm if necessary joins are possible.
            7. If similar query have been failed before, learn the error and try to avoid it.
            8. Consider if complex calculations are feasible in SQL.
            9. Identify multiple interpretations if they exist.
            10. If the question is a follow-up, resolve references using the
               conversation history and previous answers.
            11. Use memory context to provide more personalized and informed SQL generation.
            12. Learn from successful query patterns in memory context and avoid failed approaches.
            13. For personal queries, FIRST check memory context for user identification. If user identity is found in memory context (user name, previous personal queries, etc.), the query IS translatable.
            14. CRITICAL PERSONALIZATION CHECK: If missing user identification/personalization is a significant or primary component of the query (e.g., "show my orders", "my account balance", "my recent purchases", "how many employees I have", "products I own") AND no user identification is available in memory context or schema, set "is_sql_translatable" to false. However, if memory context contains user identification (like user name or previous successful personal queries), then personal queries ARE translatable even if they are the primary component of the query.

            Again: OUTPUT ONLY VALID JSON. No explanations outside the JSON block. """  # pylint: disable=line-too-long
        return prompt
