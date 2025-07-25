"""Follow-up agent for handling follow-up questions and conversational context."""

import json
from litellm import completion
from api.config import Config


FOLLOW_UP_PROMPT = """You are an expert assistant that receives two inputs:

1. The user's question: {QUESTION}
2. The history of his questions: {HISTORY}
3. A detected database schema (all relevant tables, columns, and their descriptions): {SCHEMA}

Your primary goal is to decide if the user's questions can be addressed using the existing schema or if new or additional data is required.
Any thing that can be calculated from the provided tables is define the status Data-focused.
Please follow these steps:

1. Understand the user's question in the context of the provided schema.
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
• Ask clarifying questions to confirm the user's intent or to gather any necessary information.
• Use a JSON format such as:
{{
"status": "Needs more data",
"reason": "Reason why the current schema is insufficient.",
"followUpQuestion": "Single question to clarify user intent or additional data needed, can be a specific value..."

}}

4. Ensure your response is concise, polite, and helpful. When asking clarifying
   questions, be specific and guide the user toward providing the missing details
   so you can effectively address their query."""


class FollowUpAgent:
    """Agent for handling follow-up questions and conversational context."""

    def __init__(self):
        """Initialize the follow-up agent."""

    def get_answer(
        self, user_question: str, conversation_hist: list, database_schema: dict
    ) -> dict:
        """Get answer for follow-up questions using conversation history."""
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
