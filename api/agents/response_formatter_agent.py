"""Response formatter agent for generating user-readable responses from SQL query results."""

from typing import List, Dict
from litellm import completion
from api.config import Config


RESPONSE_FORMATTER_PROMPT = """
You are an AI assistant that helps users understand database query results. Your task is to analyze the SQL query results and provide a clear, concise, and user-friendly explanation.

**Context:**
Database Description: {DB_DESCRIPTION}

**User's Original Question:**
{USER_QUERY}

**SQL Query Executed:**
{SQL_QUERY}

**Query Type:** {SQL_TYPE}

**Query Results:**
{FORMATTED_RESULTS}

**Instructions:**
1. Provide a clear, natural language answer to the user's question based on the query results
2. For SELECT queries: Focus on the key insights and findings from the data
3. For INSERT/UPDATE/DELETE queries: Confirm the operation was successful and mention how many records were affected
4. For other operations (CREATE, DROP, etc.): Confirm the operation was completed successfully
5. Use bullet points or numbered lists when presenting multiple items
6. Include relevant numbers, percentages, or trends if applicable
7. Be concise but comprehensive - avoid unnecessary technical jargon
8. If the results are empty, explain that no data was found matching the criteria
9. If there are many results, provide a summary with highlights
10. Do not mention the SQL query or technical database details unless specifically relevant to the user's understanding

**Response Format:**
Provide a direct answer to the user's question in a conversational tone, as if you were explaining the findings to a colleague.
"""


class ResponseFormatterAgent:
    """Agent for generating user-readable responses from SQL query results."""

    def __init__(self):
        """Initialize the response formatter agent."""

    def format_response(self, user_query: str, sql_query: str,
                       query_results: List[Dict], db_description: str = "") -> str:
        """
        Generate a user-readable response based on the SQL query results.

        Args:
            user_query: The original user question
            sql_query: The SQL query that was executed
            query_results: The results from the SQL query execution
            db_description: Description of the database context

        Returns:
            A formatted, user-readable response string
        """
        prompt = self._build_response_prompt(user_query, sql_query, query_results, db_description)

        messages = [{"role": "user", "content": prompt}]

        completion_result = completion(
            model=Config.COMPLETION_MODEL,
            messages=messages,
            temperature=0.3,  # Slightly higher temperature for more natural responses
            top_p=1,
        )

        response = completion_result.choices[0].message.content
        return response.strip()

    def _build_response_prompt(self, user_query: str, sql_query: str,
                              query_results: List[Dict], db_description: str) -> str:
        """Build the prompt for generating user-readable responses."""

        # Format the query results for better readability
        formatted_results = self._format_query_results(query_results)

        # Determine the type of SQL operation
        sql_type = sql_query.strip().split()[0].upper() if sql_query else "UNKNOWN"

        prompt = RESPONSE_FORMATTER_PROMPT.format(
            DB_DESCRIPTION=db_description if db_description else "Not provided",
            USER_QUERY=user_query,
            SQL_QUERY=sql_query,
            SQL_TYPE=sql_type,
            FORMATTED_RESULTS=formatted_results
        )

        return prompt

    def _format_query_results(self, query_results: List[Dict]) -> str:
        """Format query results for inclusion in the prompt."""
        if not query_results:
            return "No results found."

        if len(query_results) == 0:
            return "No results found."

        # Check if this is an operation result (INSERT/UPDATE/DELETE)
        if len(query_results) == 1 and "operation" in query_results[0]:
            result = query_results[0]
            operation = result.get("operation", "UNKNOWN")
            affected_rows = result.get("affected_rows")
            status = result.get("status", "unknown")

            if affected_rows is not None:
                return f"Operation: {operation}, Status: {status}, Affected rows: {affected_rows}"

            return f"Operation: {operation}, Status: {status}"

        # Handle regular SELECT query results
        # Limit the number of results shown in the prompt to avoid token limits
        max_results_to_show = 50
        results_to_show = query_results[:max_results_to_show]

        formatted = []
        for i, result in enumerate(results_to_show, 1):
            if isinstance(result, dict):
                result_str = ", ".join([f"{k}: {v}" for k, v in result.items()])
                formatted.append(f"{i}. {result_str}")
            else:
                formatted.append(f"{i}. {result}")

        result_text = "\n".join(formatted)

        if len(query_results) > max_results_to_show:
            result_text += f"\n... and {len(query_results) - max_results_to_show} more results"

        return result_text
