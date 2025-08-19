"""Relevancy agent for determining relevancy of queries to database schema."""

import json
from litellm import completion
from api.config import Config
from .utils import BaseAgent, parse_response


RELEVANCY_PROMPT = """
You are an expert assistant tasked with determining whether the user's question aligns with a given database description and whether the question is appropriate. You receive two inputs:

The user's question: {QUESTION_PLACEHOLDER}
The database description: {DB_PLACEHOLDER}
Please follow these instructions:

Understand the question in the context of the database.
• Ask yourself: "Does this question relate to the data or concepts described in the database description?"
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


class RelevancyAgent(BaseAgent):
    # pylint: disable=too-few-public-methods
    """Agent for determining relevancy of queries to database schema."""

    def __init__(self, queries_history: list, result_history: list):
        """Initialize the relevancy agent with query and result history."""
        if result_history is None:
            self.messages = []
        else:
            self.messages = []
            for query, result in zip(queries_history[:-1], result_history):
                self.messages.append({"role": "user", "content": query})
                self.messages.append({"role": "assistant", "content": result})

    def get_answer(self, user_question: str, database_desc: dict) -> dict:
        """Get relevancy assessment for user question against database description."""
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
        return parse_response(answer)
