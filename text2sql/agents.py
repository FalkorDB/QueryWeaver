import json
from litellm import completion, embedding
from text2sql.graph import find, find_connecting_tables
from text2sql.config import Config


def get_completion(message):
    completion_result = completion(
            model=Config.COMPLETION_MODEL,
            messages=[
                {
                    "content": message,
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

class base_agent:
    def __init__(self, args):
        pass


class aiming_agent(base_agent):
    def __init__(self, args):
        super().__init__(args)  # Call parent class constructor
        
        # Store arguments as instance variables
        self.args = args
        self.result = args.get('result')
        self.queries_history = args.get('queries_history')
        self.db_description = args.get('db_description')
        self.graph = args.get('graph')
        self.Config = args.get('Config')
        
        # Initialize class attributes
        self.connection_tables = None
        
    def find_connections(self):
        """Find connections between tables based on user query."""
        # Check if we have the necessary data to proceed
        if not (self.queries_history and self.result):
            return None, None
            
        user_content = json.dumps({
            "schema": self.result,
            "previous_queries": self.queries_history[:-1],
            "user_query": self.queries_history[-1]
        })
        
        # Using the imported completion function
        completion_result = completion(
            model=self.Config.COMPLETION_MODEL,
            messages=[
                {
                    "content": self.Config.Text_To_tables_PROMPT.format(db_description=self.db_description),
                    "role": "system"
                },
                {
                    "content": user_content,
                    "role": "user"
                }
            ],
            response_format={"type": "json_object"},
            temperature=0
        )
        
        focus_tables = completion_result.choices[0].message.content
        table_list = json.loads(focus_tables)
        
        # Using the imported find_connecting_tables function
        self.result, self.connection_tables = find_connecting_tables(self.graph, table_list, self.result)
        return self.result, self.connection_tables
    

class RelevancyAgent(base_agent):
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
            response_format={"type": "json_object"},
            temperature=0,
            aws_profile_name=Config.AWS_PROFILE,
            aws_region_name=Config.AWS_REGION,
        )
        
        answer = completion_result.choices[0].message.content
        return json.loads(answer)


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



class FollowUpAgent(base_agent):
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



class TaxonomyAgent(base_agent):
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