import json
from litellm import completion, embedding
from text2sql.graph import find, find_connecting_tables
from text2sql.config import Config
from typing import List, Tuple, Dict, Any

class AnalysisAgent():
    def __init__(self):
        pass

    def get_analysis(self, user_query: str, combined_tables: list, db_description: str) -> dict:
        formatted_schema = self._format_schema(combined_tables)
        prompt = self._build_prompt(user_query, formatted_schema, db_description)
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

    def _build_prompt(self, user_input: str, formatted_schema: str, db_description: str) -> str:
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
        7. Ambiguities can be two or more column with same semantic meaning that can be used in the query
        8. **IMPORTANT** When the user_query ask about members look for one of the memeber tables and use 'Join' clause!


        Provide your response as valid, parseable JSON only.
        """
        return prompt


class RelevancyAgent():
    def __init__(self):
        pass

    def get_answer(self, user_question: str, database_schema: dict) -> dict:
        completion_result = completion(
            model=Config.COMPLETION_MODEL,
            messages=[
                {
                    "content": RELEVANCY_PROMPT.format(QUESTION_PLACEHOLDER=user_question, SCHEMA_PLACEHOLDER=json.dumps(database_schema)),
                    "role": "user"
                }
            ],
            temperature=0,
            aws_profile_name=Config.AWS_PROFILE,
            aws_region_name=Config.AWS_REGION,
        )
        
        answer = completion_result.choices[0].message.content
        return _parse_response(answer)


RELEVANCY_PROMPT = """
You are an expert assistant tasked with determining whether the user’s question aligns with a given database schema and whether the question is appropriate. You receive two inputs:

The user’s question: {QUESTION_PLACEHOLDER}
The detected database schema (all relevant tables, columns, and their descriptions): {SCHEMA_PLACEHOLDER}
Please follow these instructions:

Understand the question in the context of the database schema.
• Ask yourself: “Does this question relate to the data or concepts described in the schema?”
• Don't answer questions that related to yourself.
• Don't answer questions that related to personal information.
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


class FollowUpAgent():
    def __init__(self):
        pass

    def get_answer(self, user_question: str, conversation_hist: list, database_schema: dict) -> dict:
        completion_result = completion(
            model=Config.COMPLETION_MODEL,
            messages=[
                {
                    "content": FOLLOW_UP_PROMPT.format(QUESTION=user_question, HISTORY=conversation_hist, SCHEMA=json.dumps(database_schema)),
                    "role": "user"
                }
            ],
            response_format={"type": "json_object"},
            temperature=0,
            aws_profile_name=Config.AWS_PROFILE,
            aws_region=Config.AWS_REGION,
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



class TaxonomyAgent():
    def __init__(self):
        pass

    def get_answer(self, question: str, sql: str) -> str:
        messages = [
            {
                "content": TAXONOMY_PROMPT.format(QUESTION=question, SQL=sql),
                "role": "user"
            }
        ]
        completion_result = completion(
            model=Config.COMPLETION_MODEL,
            messages=messages,
            temperature=0,
            aws_profile_name=Config.AWS_PROFILE,
            aws_region=Config.AWS_REGION,
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