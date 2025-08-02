"""Taxonomy agent for taxonomy classification of questions and SQL queries."""

from litellm import completion
from api.config import Config


TAXONOMY_PROMPT = """You are an advanced taxonomy generator. For a pair of question and SQL query \
provde a single clarification question to the user.
* For any SQL query that contain WHERE clause, provide a clarification question to the user about the \
generated value.
* Your question can contain more than one clarification related to WHERE clause.
* Please asked only about the clarifications that you need and not extand the answer.
* Please ask in a polite, humen, and concise manner.
* Do not meantion any tables or columns in your ouput!.
* If you dont need any clarification, please answer with "I don't need any clarification."
* The user didnt saw the SQL queryor the tables, so please understand this position and ask the \
clarification in that way he have the relevent information to answer.
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


class TaxonomyAgent:
    # pylint: disable=too-few-public-methods
    """Agent for taxonomy classification of questions and SQL queries."""

    def __init__(self):
        """Initialize the taxonomy agent."""

    def get_answer(self, question: str, sql: str) -> str:
        """Get taxonomy classification for a question and SQL pair."""
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
