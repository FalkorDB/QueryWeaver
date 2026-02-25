"""
HealerAgent - Specialized agent for fixing SQL syntax errors.

This agent focuses solely on correcting SQL queries that failed execution,
without requiring full graph context. It uses the error message and the
failed query to generate a corrected version.
"""
# pylint: disable=trailing-whitespace,line-too-long,too-many-arguments
# pylint: disable=too-many-positional-arguments,broad-exception-caught

import re
from typing import Dict, Callable, Any
from litellm import completion
from api.config import Config
from .utils import parse_response


class HealerAgent:
    """Agent specialized in fixing SQL syntax errors."""
    
    def __init__(self, max_healing_attempts: int = 3):
        """Initialize the healer agent.
        
        Args:
            max_healing_attempts: Maximum number of healing attempts before giving up
        """
        self.max_healing_attempts = max_healing_attempts
        self.messages = []
    
    @staticmethod
    def validate_sql_syntax(sql_query: str) -> dict:
        """
        Validate SQL query for basic syntax errors.
        Similar to CypherValidator in the text-to-cypher PR.
        
        Args:
            sql_query: The SQL query to validate
            
        Returns:
            dict with 'is_valid', 'errors', and 'warnings' keys
        """
        errors = []
        warnings = []
        
        query = sql_query.strip()
        
        # Check if query is empty
        if not query:
            errors.append("Query is empty")
            return {"is_valid": False, "errors": errors, "warnings": warnings}
        
        # Check for basic SQL keywords
        query_upper = query.upper()
        has_sql_keywords = any(
            kw in query_upper for kw in ["SELECT", "INSERT", "UPDATE", "DELETE", "WITH", "CREATE"]
        )
        if not has_sql_keywords:
            errors.append("Query does not contain valid SQL keywords")
        
        # Check for dangerous operations (for dev/test safety)
        dangerous_patterns = [
            r'\bDROP\s+TABLE\b', r'\bTRUNCATE\b', r'\bDELETE\s+FROM\s+\w+\s*;?\s*$'
        ]
        for pattern in dangerous_patterns:
            if re.search(pattern, query_upper):
                warnings.append(f"Query contains potentially dangerous operation: {pattern}")
        
        # Check for balanced parentheses
        paren_count = 0
        for char in query:
            if char == '(':
                paren_count += 1
            elif char == ')':
                paren_count -= 1
                if paren_count < 0:
                    errors.append("Unbalanced parentheses in query")
                    break
        if paren_count != 0:
            errors.append("Unbalanced parentheses in query")
        
        # Check for SELECT queries have proper structure
        if query_upper.startswith("SELECT") or "SELECT" in query_upper:
            if "FROM" not in query_upper and "DUAL" not in query_upper:
                warnings.append("SELECT query missing FROM clause")
        
        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }
    
    def _build_healing_prompt(
        self,
        failed_sql: str,
        error_message: str,
        db_description: str,
        question: str,
        database_type: str
    ) -> str:
        """Build a focused prompt for SQL query healing."""
        
        # Analyze error to provide targeted hints
        error_hints = self._analyze_error(error_message, database_type)
        
        prompt = f"""You are a SQL query debugging expert. Your task is to fix a SQL query that failed execution.

DATABASE TYPE: {database_type.upper()}

FAILED SQL QUERY:
```sql
{failed_sql}
```

EXECUTION ERROR:
{error_message}

{f"ORIGINAL QUESTION: {question}" if question else ""}

{f"DATABASE INFO: {db_description}"}

COMMON ERROR PATTERNS:
{error_hints}

YOUR TASK:
1. Identify the exact cause of the error
2. Fix ONLY what's broken - don't rewrite the entire query
3. Ensure the fix is compatible with {database_type.upper()}
4. Maintain the original query logic and intent

CRITICAL RULES FOR {database_type.upper()}:
"""
        
        if database_type == "sqlite":
            prompt += """
- SQLite does NOT support EXTRACT() function - use strftime() instead
  * EXTRACT(YEAR FROM date_col) → strftime('%Y', date_col)
  * EXTRACT(MONTH FROM date_col) → strftime('%m', date_col)
  * EXTRACT(DAY FROM date_col) → strftime('%d', date_col)
- SQLite column/table names are case-insensitive BUT must exist
- SQLite uses double quotes "column" for identifiers with special characters
- Use backticks `column` for compatibility
- No schema qualifiers (database.table.column)
"""
        elif database_type == "postgresql":
            prompt += """
- PostgreSQL is case-sensitive - use double quotes for mixed-case identifiers
- EXTRACT() is supported: EXTRACT(YEAR FROM date_col)
- Column references must match exact case when quoted
"""
        
        prompt += """
RESPONSE FORMAT (valid JSON only):
{
  "sql_query": "-- your fixed SQL query here",
  "confidence": 85,
  "explanation": "Brief explanation of what was fixed",
  "changes_made": ["Changed EXTRACT to strftime", "Fixed column casing"]
}

IMPORTANT:
- Return ONLY the JSON object, no other text
- Fix ONLY the specific error, preserve the rest
- Test your fix mentally before responding
- If error is about a column/table name, check spelling carefully
"""
        
        return prompt
    
    def heal_and_execute(  # pylint: disable=too-many-locals
        self,
        initial_sql: str,
        initial_error: str,
        execute_sql_func: Callable[[str], Any],
        db_description: str = "",
        question: str = "",
        database_type: str = "sqlite"
    ) -> Dict[str, Any]:
        """Iteratively heal and execute SQL query until success or max attempts.
        
        This method creates a conversation loop between the healer and the database:
        1. Build initial prompt once with the failed SQL and error (including syntax validation)
        2. Loop: Call LLM → Parse healed SQL → Execute → Check if successful
        3. If successful, return results
        4. If failed and not last attempt, add error feedback and repeat
        5. If failed on last attempt, return failure
        
        Args:
            initial_sql: The initial SQL query that failed
            initial_error: The error message from the initial execution failure
            execute_sql_func: Function that executes SQL and returns results or raises exception
            db_description: Optional database description
            question: Optional original question
            database_type: Type of database (sqlite, postgresql, mysql, etc.)
            
        Returns:
            Dict containing:
                - success: Whether healing succeeded
                - sql_query: Final SQL query (healed or original)
                - query_results: Results from successful execution (if success=True)
                - attempts: Number of healing attempts made
                - final_error: Final error message (if success=False)
        """
        self.messages = []
        
        # Validate SQL syntax for additional error context
        validation_result = self.validate_sql_syntax(initial_sql)
        additional_context = ""
        if validation_result["errors"]:
            additional_context += f"\nSyntax errors: {', '.join(validation_result['errors'])}"
        if validation_result["warnings"]:
            additional_context += f"\nWarnings: {', '.join(validation_result['warnings'])}"
        # Enhance error message with validation context
        enhanced_error = initial_error + additional_context
        
        # Build initial prompt once before the loop
        prompt = self._build_healing_prompt(
            failed_sql=initial_sql,
            error_message=enhanced_error,
            db_description=db_description,
            question=question,
            database_type=database_type
        )
        self.messages.append({"role": "user", "content": prompt})
        
        for attempt in range(self.max_healing_attempts):
            # Call LLM
            response = completion(
                model=Config.COMPLETION_MODEL,
                messages=self.messages,
                temperature=0.1,
                max_tokens=2000
            )
            
            content = response.choices[0].message.content
            self.messages.append({"role": "assistant", "content": content})
            
            # Parse response
            result = parse_response(content)
            healed_sql = result.get("sql_query", "")
            
            # Execute against database
            error = None
            try:
                query_results = execute_sql_func(healed_sql)
            except Exception as e:
                error = str(e)
            
            # Check if it worked
            if error is None:
                # Success!
                return {
                    "success": True,
                    "sql_query": healed_sql,
                    "query_results": query_results,
                    "attempts": attempt + 1,
                    "final_error": None
                }
            
            # Failed - check if last attempt
            if attempt >= self.max_healing_attempts - 1:
                return {
                    "success": False,
                    "sql_query": healed_sql,
                    "query_results": None,
                    "attempts": attempt + 1,
                    "final_error": error
                }
            
            # Not last attempt - add feedback and continue
            feedback = f"""The healed query failed with error:

```sql
{healed_sql}
```

ERROR:
{error}

Please fix this error."""
            self.messages.append({"role": "user", "content": feedback})
        
        # Fallback return
        return {
            "success": False,
            "sql_query": initial_sql,
            "query_results": None,
            "attempts": self.max_healing_attempts,
            "final_error": initial_error
        }
        
    
    def _analyze_error(self, error_message: str, database_type: str) -> str:
        """Analyze error message and provide targeted hints."""
        
        error_lower = error_message.lower()
        hints = []
        
        # Common SQLite errors
        if database_type == "sqlite":
            if "near \"from\"" in error_lower or "syntax error" in error_lower:
                hints.append("⚠️  EXTRACT() is NOT supported in SQLite - use strftime() instead!")
                hints.append("   Example: strftime('%Y', date_column) for year")
            
            if "no such column" in error_lower:
                hints.append("⚠️  Column name doesn't exist - check spelling and case")
                hints.append("   SQLite is case-insensitive but the column must exist")
            
            if "no such table" in error_lower:
                hints.append("⚠️  Table name doesn't exist - check spelling")
            
            if "ambiguous column" in error_lower:
                hints.append("⚠️  Ambiguous column - use table alias: table.column or alias.column")
        
        # PostgreSQL errors
        elif database_type == "postgresql":
            if "column" in error_lower and "does not exist" in error_lower:
                hints.append("⚠️  Column case mismatch - PostgreSQL is case-sensitive")
                hints.append('   Use double quotes for mixed-case: "ColumnName"')
            
            if "relation" in error_lower and "does not exist" in error_lower:
                hints.append("⚠️  Table doesn't exist or case mismatch")
        
        # Generic hints if no specific patterns matched
        if not hints:
            hints.append("⚠️  Check syntax compatibility with " + database_type.upper())
            hints.append("⚠️  Verify column and table names exist")
        
        return "\n".join(hints)
