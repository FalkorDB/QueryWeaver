"""Analysis agent for analyzing user queries and generating database analysis."""

from typing import List
from litellm import completion
from api.config import Config
from .utils import BaseAgent, parse_response


class AnalysisAgent(BaseAgent):
    # pylint: disable=too-few-public-methods
    """Agent for analyzing user queries and generating database analysis."""


    def get_analysis(
        self,
        user_query: str,
        combined_tables: list,
        db_description: str,
        instructions: str = None,
    ) -> dict:
        """Get analysis of user query against database schema."""
        formatted_schema = self._format_schema(combined_tables)
        prompt = self._build_prompt(
            user_query, formatted_schema, db_description, instructions
        )
        self.messages.append({"role": "user", "content": prompt})
        completion_result = completion(
            model=Config.COMPLETION_MODEL,
            messages=self.messages,
            temperature=0,
            top_p=1,
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
            table_name = table_info[0]
            table_description = table_info[1]
            foreign_keys = table_info[2]
            columns = table_info[3]

            # Format table header
            table_str = f"Table: {table_name} - {table_description}\n"

            # Format columns using the updated OrderedDict structure
            for column in columns:
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
                column_str = (f"  - {col_name} ({col_type},{key_info},{col_key},"
                             f"{nullable}): {col_description}")
                table_str += column_str + "\n"

            # Format foreign keys
            if isinstance(foreign_keys, dict) and foreign_keys:
                table_str += "  Foreign Keys:\n"
                for fk_name, fk_info in foreign_keys.items():
                    column = fk_info.get("column", "")
                    ref_table = fk_info.get("referenced_table", "")
                    ref_column = fk_info.get("referenced_column", "")
                    table_str += (
                        f"  - {fk_name}: {column} references {ref_table}.{ref_column}\n"
                    )

            formatted_schema.append(table_str)

        return "\n".join(formatted_schema)

    def _build_prompt(
        self, user_input: str, formatted_schema: str, db_description: str, instructions
    ) -> str:
        """
        Build the prompt for Claude to analyze the query.

        Args:
            user_input: The natural language query from the user
            formatted_schema: Formatted database schema

        Returns:
            The formatted prompt for Claude
        """
        prompt = f"""
            You must strictly follow the instructions below. Deviations will result in a penalty to your confidence score.

            MANDATORY RULES:
            - Always explain if you cannot fully follow the instructions.
            - Always reduce the confidence score if instructions cannot be fully applied.
            - Never skip explaining missing information, ambiguities, or instruction issues.
            - Respond ONLY in strict JSON format, without extra text.
            - If the query relates to a previous question, you MUST take into account the previous question and its answer, and answer based on the context and information provided so far.

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
            - If you CANNOT apply instructions in the SQL, explain why under
              "instructions_comments", "explanation" and reduce your confidence.
            - Penalize confidence appropriately if any part of the instructions is unmet.
            - When there several tables that can be used to answer the question,
              you can combine them in a single SQL query.

            Provide your output ONLY in the following JSON structure:

            ```json
            {{
                "is_sql_translatable": true or false,
                "instructions_comments": ("Comments about any part of the instructions, "
                                         "especially if they are unclear, impossible, "
                                         "or partially met"),
                "explanation": ("Detailed explanation why the query can or cannot be "
                               "translated, mentioning instructions explicitly and "
                               "referencing conversation history if relevant"),
                "sql_query": ("High-level SQL query (you must to applying instructions "
                             "and use previous answers if the question is a continuation)"),
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
            5. Confirm if necessary joins are possible.
            6. Consider if complex calculations are feasible in SQL.
            7. Identify multiple interpretations if they exist.
            8. Strictly apply instructions; explain and penalize if not possible.
            9. If the question is a follow-up, resolve references using the
               conversation history and previous answers.

            Again: OUTPUT ONLY VALID JSON. No explanations outside the JSON block. """
        return prompt
