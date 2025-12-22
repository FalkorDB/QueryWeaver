"""Relevancy agent for determining relevancy of queries to database schema."""

import json
from litellm import completion
from api.config import Config
from .utils import BaseAgent, parse_response


RELEVANCY_PROMPT = """
You are an expert assistant tasked with determining whether the user's question is relevant (translatable into a database query). 
You are given:
- The user's latest question: {QUESTION_PLACEHOLDER}
- The database description: {DB_PLACEHOLDER}
- The conversation history (previous questions and answers) is also provided in this chat.

Guidelines:

1. **Always use the full conversation context** when deciding relevance, not just the latest question.
   - If earlier in the chat the system asked for missing information (e.g., "What's your name or ID?") and the user provided it, then the current question should be treated as valid and on-topic.
   - Consider whether ambiguities have already been resolved in prior turns.

2. **Focus on actionable intent for database querying.**
   - Ask yourself: "Can this request, given the conversation so far, be answered by querying the database?"
   - Personal pronouns ("I", "my", "me") are on-topic if the user has identified themselves or if the intent clearly maps to database data.
   - Conversational or casual phrasing is fine as long as the underlying request is for data.

3. **On-topic cases include:**
   - Questions that can be translated into database queries (directly or with previously provided clarifications).
   - Personal queries where the user provided their identity after being asked.
   - Questions about data, database structure, reports, metrics, or insights.

4. **Off-topic cases include:**
   - Completely unrelated to data/business information,
   - Questions about the AI/system itself,
   - Requests for private information about people outside the database,
   - Offensive, illegal, or guideline-violating content.

Output format:

• On-topic and appropriate:
{{
"status": "On-topic",
"reason": "Brief explanation of why it can be translated to a database query.",
"suggestions": []
}}

• Off-topic:
{{
"status": "Off-topic",
"reason": "Short reason why it cannot be translated to a database query.",
"suggestions": [
"An alternative, high-level question about the schema..."
]
}}

• Inappropriate:
{{
"status": "Inappropriate",
"reason": "Short reason why it is inappropriate.",
"suggestions": [
"Suggested topics that would be more appropriate..."
]
}}

Remember: **Prioritize the conversation’s actionable data intent over phrasing style. If missing info (like identity) was provided earlier in the chat, treat the question as on-topic.**
"""


class RelevancyAgent(BaseAgent):
    # pylint: disable=too-few-public-methods
    """Agent for determining relevancy of queries to database schema."""


    async def get_answer(self, user_question: str, database_desc: dict) -> dict:
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
        
        # Prepare completion arguments
        completion_args = {
            "model": self.custom_model if self.custom_model else Config.COMPLETION_MODEL,
            "messages": self.messages,
            "temperature": 0,
        }
        
        # Add custom API key if provided
        if self.custom_api_key:
            completion_args["api_key"] = self.custom_api_key
        
        completion_result = completion(**completion_args)

        answer = completion_result.choices[0].message.content
        self.messages.append({"role": "assistant", "content": answer})
        return parse_response(answer)
