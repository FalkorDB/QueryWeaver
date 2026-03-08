"""Follow-up agent for generating helpful questions when queries fail or are off-topic."""

from .utils import BaseAgent, run_completion


FOLLOW_UP_GENERATION_PROMPT = """
You are a helpful database expert. A colleague asked a question, but their query can’t run correctly.

Context:
- Question: "{QUESTION}"
- Translatability: {IS_TRANSLATABLE}
- Missing info: {MISSING_INFO}
- Ambiguities: {AMBIGUITIES}
- Analysis: {EXPLANATION}

Your task:
- Write a **very short response (max 2 sentences, under 40 words total)**.
- Sentence 1: Acknowledge warmly and show willingness to help, without being technical.
- Sentence 2: Ask for the specific missing information in natural, conversational language.
- **If the query uses "I", "my", or "me" → always ask who they are (name, employee ID, or username).**
- Use warm, natural wording like “I need to know who you are” instead of “provide your ID.”
- Keep the tone friendly, encouraging, and solution-focused — like a helpful colleague, not a system.

Example responses (personal queries):
- "I'd love to help find your employees! What's your name or employee ID so I can look up who reports to you?"
- "Happy to help with your data! Who should I look up — what's your username or employee ID?"
- "I can definitely help! Could you tell me your name or ID so I know which records are yours?"
"""


class FollowUpAgent(BaseAgent):  # pylint: disable=too-few-public-methods
    """Agent for generating helpful follow-up questions when queries fail or are off-topic."""

    def generate_follow_up_question(
        self,
        user_question: str,
        analysis_result: dict
    ) -> str:
        """
        Generate helpful follow-up questions based on failed SQL translation.
        
        Args:
            user_question: The original user question
            analysis_result: Output from analysis agent 
            schema_info: Database schema information
            found_tables: Tables found by the find function
            
        Returns:
            str: Conversational follow-up response
        """

        # Extract key information from analysis result
        is_translatable = (
            analysis_result.get("is_sql_translatable", False)
            if analysis_result else False
        )
        missing_info = analysis_result.get("missing_information", []) if analysis_result else []
        ambiguities = analysis_result.get("ambiguities", []) if analysis_result else []
        explanation = (analysis_result.get("explanation", "No detailed explanation available")
                        if analysis_result else "No analysis result available")
        # Prepare the prompt
        prompt = FOLLOW_UP_GENERATION_PROMPT.format(
            QUESTION=user_question,
            IS_TRANSLATABLE=is_translatable,
            MISSING_INFO=missing_info,
            AMBIGUITIES=ambiguities,
            EXPLANATION=explanation
        )

        try:
            response = run_completion(
                [{"role": "user", "content": prompt}],
                self.custom_model, self.custom_api_key, temperature=0.9
            )
            return response.strip()

        except Exception: # pylint: disable=broad-exception-caught
            # Fallback response if LLM call fails
            return "Sorry, I couldn't generate a follow-up. Could you clarify your question a bit?"
