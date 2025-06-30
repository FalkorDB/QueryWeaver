import json
from typing import Any, Dict, List

from litellm import completion

from api.config import Config


class AnalysisAgent:
    def __init__(self, queries_history: list, result_history: list):
        if result_history is None:
            self.messages = []
        else:
            self.messages = []
            for query, result in zip(queries_history[:-1], result_history):
                self.messages.append({"role": "user", "content": query})
                self.messages.append({"role": "assistant", "content": result})

    def get_analysis(
        self,
        user_query: str,
        combined_tables: list,
        db_description: str,
        instructions: str = None,
    ) -> dict:
        formatted_schema = self._format_schema(combined_tables)
        prompt = self._build_prompt(user_query, formatted_schema, db_description, instructions)
        self.messages.append({"role": "user", "content": prompt})
        completion_result = completion(
            model=Config.COMPLETION_MODEL,
            messages=self.messages,
            temperature=0,
            top_p=1,
        )

        response = completion_result.choices[0].message.content
        analysis = _parse_response(response)
        if isinstance(analysis["ambiguities"], list):
            analysis["ambiguities"] = [item.replace("-", " ") for item in analysis["ambiguities"]]
            analysis["ambiguities"] = "- " + "- ".join(analysis["ambiguities"])
        if isinstance(analysis["missing_information"], list):
            analysis["missing_information"] = [
                item.replace("-", " ") for item in analysis["missing_information"]
            ]
            analysis["missing_information"] = "- " + "- ".join(analysis["missing_information"])
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
                    f", PRIMARY KEY"
                    if col_key == "PRI"
                    else f", FOREIGN KEY" if col_key == "FK" else ""
                )
                column_str = f"  - {col_name} ({col_type},{key_info},{col_key},{nullable}): {col_description}"
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
            - If you CANNOT apply instructions in the SQL, explain why under "instructions_comments", "explanation" and reduce your confidence.
            - Penalize confidence appropriately if any part of the instructions is unmet.
            - When there several tables that can be used to answer the question, you can combine them in a single SQL query.

            Provide your output ONLY in the following JSON structure:

            ```json
            {{
                "is_sql_translatable": true or false,
                "instructions_comments": "Comments about any part of the instructions, especially if they are unclear, impossible, or partially met",
                "explanation": "Detailed explanation why the query can or cannot be translated, mentioning instructions explicitly and referencing conversation history if relevant",
                "sql_query": "High-level SQL query (you must to applying instructions and use previous answers if the question is a continuation)",
                "tables_used": ["list", "of", "tables", "used", "in", "the", "query", "with", "the", "relationships", "between", "them"],
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
            9. If the question is a follow-up, resolve references using the conversation history and previous answers.

            Again: OUTPUT ONLY VALID JSON. No explanations outside the JSON block. """
        return prompt


class RelevancyAgent:
    def __init__(self, queries_history: list, result_history: list):
        if result_history is None:
            self.messages = []
        else:
            self.messages = []
            for query, result in zip(queries_history[:-1], result_history):
                self.messages.append({"role": "user", "content": query})
                self.messages.append({"role": "assistant", "content": result})

    def get_answer(self, user_question: str, database_desc: dict) -> dict:
        self.messages.append(
            {
                "role": "user",
                "content": RELEVANCY_PROMPT.format(
                    QUESTION_PLACEHOLDER=user_question,
                    DB_PLACEHOLDER=json.dumps(database_desc),
                ),
            }
        )
        completion_result = completion(
            model=Config.COMPLETION_MODEL,
            messages=self.messages,
            temperature=0,
        )

        answer = completion_result.choices[0].message.content
        self.messages.append({"role": "assistant", "content": answer})
        return _parse_response(answer)


RELEVANCY_PROMPT = """
You are an expert assistant tasked with determining whether the user’s question aligns with a given database description and whether the question is appropriate. You receive two inputs:

The user’s question: {QUESTION_PLACEHOLDER}
The database description: {DB_PLACEHOLDER}
Please follow these instructions:

Understand the question in the context of the database.
• Ask yourself: “Does this question relate to the data or concepts described in the database description?”
• Common tables that can be found in most of the systems considered "On-topic" even if it not explict in the database description.
• Don't answer questions that related to yourself.
• Don't answer questions that related to personal information unless it related to data in the schemas.
• Questions about the user's (first person) defined as "personal" and is Off-topic.
• Questions about yourself defined as "personal" and is Off-topic.

Determine if the question is:
• On-topic and appropriate:
– If so, provide a JSON response in the following format:
{{
"status": "On-topic",
"reason": "Brief explanation of why it is on-topic and appropriate."
"suggestions": []
}}

• Off-topic:
– If the question does not align with the data or use cases implied by the schema, provide a JSON response:
{{
"status": "Off-topic",
"reason": "Short reason explaining why it is off-topic.",
"suggestions": [
"An alternative, high-level question about the schema..."
]
}}

• Inappropriate:
– If the question is offensive, illegal, or otherwise violates content guidelines, provide a JSON response:
{{
"status": "Inappropriate",
"reason": "Short reason why it is inappropriate.",
"suggestions": [
"Suggested topics that would be more appropriate..."
]
}}

Ensure your response is concise, polite, and helpful.
"""


class FollowUpAgent:
    def __init__(self):
        pass

    def get_answer(
        self, user_question: str, conversation_hist: list, database_schema: dict
    ) -> dict:
        completion_result = completion(
            model=Config.COMPLETION_MODEL,
            messages=[
                {
                    "content": FOLLOW_UP_PROMPT.format(
                        QUESTION=user_question,
                        HISTORY=conversation_hist,
                        SCHEMA=json.dumps(database_schema),
                    ),
                    "role": "user",
                }
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )

        answer = completion_result.choices[0].message.content
        return json.loads(answer)


FOLLOW_UP_PROMPT = """You are an expert assistant that receives two inputs:

1. The user’s question: {QUESTION}
2. The history of his questions: {HISTORY}
3. A detected database schema (all relevant tables, columns, and their descriptions): {SCHEMA}

Your primary goal is to decide if the user’s questions can be addressed using the existing schema or if new or additional data is required.
Any thing that can be calculated from the provided tables is define the status Data-focused.
Please follow these steps:

1. Understand the user’s question in the context of the provided schema.
• Determine whether the question directly relates to the tables, columns, or concepts in the schema or needed more information about the filtering.

2. If the question relates to the existing schema:
• Provide a concise JSON response indicating:
{{
"status": "Data-focused",
"reason": "Brief explanation why this question is answerable with the given schema."
"followUpQuestion": ""
}}
• If relevant, note any additional observations or suggested follow-up.

3. If the question cannot be answered solely with the given schema or if there seems to be missing context:
• Ask clarifying questions to confirm the user’s intent or to gather any necessary information.
• Use a JSON format such as:
{{
"status": "Needs more data",
"reason": "Reason why the current schema is insufficient.",
"followUpQuestion": "Single question to clarify user intent or additional data needed, can be a specific value..."

}}

4. Ensure your response is concise, polite, and helpful. When asking clarifying questions, be specific and guide the user toward providing the missing details so you can effectively address their query."""


class TaxonomyAgent:
    def __init__(self):
        pass

    def get_answer(self, question: str, sql: str) -> str:
        messages = [
            {
                "content": TAXONOMY_PROMPT.format(QUESTION=question, SQL=sql),
                "role": "user",
            }
        ]
        completion_result = completion(
            model=Config.COMPLETION_MODEL,
            messages=messages,
            temperature=0,
        )

        answer = completion_result.choices[0].message.content
        return answer


TAXONOMY_PROMPT = """You are an advanced taxonomy generator. For a pair of question and SQL query provde a single clarification question to the user.
* For any SQL query that contain WHERE clause, provide a clarification question to the user about the generated value.
* Your question can contain more than one clarification related to WHERE clause.
* Please asked only about the clarifications that you need and not extand the answer.
* Please ask in a polite, humen, and concise manner.
* Do not meantion any tables or columns in your ouput!.
* If you dont need any clarification, please answer with "I don't need any clarification."
* The user didnt saw the SQL queryor the tables, so please understand this position and ask the clarification in that way he have the relevent information to answer.
* When you ask the user to confirm a value, please provide the value in your answer.
* Mention only question about values and dont mention the SQL query or the tables in your answer.

Please create the clarification question step by step.

Question:
{QUESTION}

SQL:
{SQL}

For example:
question: "How many diabetic patients are there?"
SQL: "SELECT COUNT(*) FROM patients WHERE disease_code = 'E11'"
Your output: "The diabitic desease code is E11? If not, please provide the correct diabitic desease code.

The question to the user:"
"""


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
        json_start = response.find("{")
        json_end = response.rfind("}") + 1
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
            "error": str(response),
        }
