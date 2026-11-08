"""SQL sanitization utilities for handling identifiers with special characters."""

import bisect
import re
from typing import Dict, List, Set, Tuple


class SQLIdentifierQuoter:
    """
    Utility class for automatically quoting SQL identifiers (table/column names)
    that contain special characters like dashes.
    """

    # Characters that require quoting in identifiers
    SPECIAL_CHARS = {'-', ' ', '.', '@', '#', '$', '%', '^', '&', '*', '(',
                     ')', '+', '=', '[', ']', '{', '}', '|', '\\', ':',
                     ';', '"', "'", '<', '>', ',', '?', '/'}
    # SQL keywords that should not be quoted
    SQL_KEYWORDS = {
        'SELECT', 'FROM', 'WHERE', 'JOIN', 'LEFT', 'RIGHT', 'INNER', 'OUTER', 'ON',
        'AS', 'AND', 'OR', 'NOT', 'IN', 'BETWEEN', 'LIKE', 'IS', 'NULL', 'ORDER',
        'BY', 'GROUP', 'HAVING', 'LIMIT', 'OFFSET', 'INSERT', 'UPDATE', 'DELETE',
        'CREATE', 'DROP', 'ALTER', 'TABLE', 'INTO', 'VALUES', 'SET', 'COUNT',
        'SUM', 'AVG', 'MAX', 'MIN', 'DISTINCT', 'ALL', 'UNION', 'INTERSECT',
        'EXCEPT', 'CASE', 'WHEN', 'THEN', 'ELSE', 'END', 'CAST', 'ASC', 'DESC'
    }

    @staticmethod
    def _is_already_quoted(identifier: str, quote_char: str = '"') -> bool:
        """Check if an identifier is already *validly* quoted for the dialect.

        The pair is scoped to *quote_char* so that a bracketed identifier is
        only treated as pre-quoted for SQL Server; on PostgreSQL/MySQL a name
        such as ``[weird]`` is data, not a delimiter, and must still be quoted.

        Matching delimiters at the ends are not sufficient: every closing
        delimiter *inside* the pair must be doubled, or the first stray one
        ends the identifier early and the rest of the string is parsed as SQL.
        ``[name] DROP TABLE users]`` must therefore not count as quoted.

        Args:
            identifier: The identifier to inspect.
            quote_char: Opening delimiter of the active dialect.

        Returns:
            True if *identifier* is already delimited and internally escaped.
        """
        close_char = ']' if quote_char == '[' else quote_char
        if len(identifier) < 2:
            return False
        if not (identifier.startswith(quote_char) and identifier.endswith(close_char)):
            return False
        return close_char not in identifier[1:-1].replace(close_char * 2, '')

    @classmethod
    def needs_quoting(cls, identifier: str, quote_char: str = '"') -> bool:
        """
        Check if an identifier needs quoting based on special characters.

        Args:
            identifier: The table or column name to check
            quote_char: Quote character of the active dialect

        Returns:
            True if the identifier needs quoting, False otherwise
        """
        # Already quoted
        if cls._is_already_quoted(identifier, quote_char):
            return False

        # Check if it's a SQL keyword
        if identifier.upper() in cls.SQL_KEYWORDS:
            return False

        # Check for special characters
        return any(char in cls.SPECIAL_CHARS for char in identifier)

    @staticmethod
    def quote_identifier(identifier: str, quote_char: str = '"') -> str:
        """
        Quote an identifier if not already quoted.

        Args:
            identifier: The identifier to quote
            quote_char: The quote character to use (default: " for PostgreSQL/standard SQL,
                        use ` for MySQL, [ for SQL Server)

        Returns:
            Quoted identifier
        """
        identifier = identifier.strip()

        # Don't double-quote
        if SQLIdentifierQuoter._is_already_quoted(identifier, quote_char):
            return identifier

        # Every dialect here escapes its closing delimiter by doubling it --
        # ``]`` for SQL Server brackets, otherwise the quote character itself.
        # Without this a name carrying a delimiter closes the identifier early
        # and turns the remainder of the name into executable SQL.
        close_char = ']' if quote_char == '[' else quote_char
        escaped = identifier.replace(close_char, close_char * 2)
        return f'{quote_char}{escaped}{close_char}'

    @classmethod
    def extract_table_names_from_query(cls, sql_query: str) -> Set[str]:
        """
        Extract potential table names from a SQL query.
        Looks for identifiers after FROM, JOIN, UPDATE, INSERT INTO, etc.
        
        Args:
            sql_query: The SQL query to parse
            
        Returns:
            Set of potential table names
        """
        table_names = set()

        # Pattern to match table names after FROM, JOIN, UPDATE, INSERT INTO, etc.
        # This is a heuristic approach - not perfect but handles common cases
        patterns = [
            r'\bFROM\s+([a-zA-Z0-9_\-]+)',
            r'\bJOIN\s+([a-zA-Z0-9_\-]+)',
            r'\bUPDATE\s+([a-zA-Z0-9_\-]+)',
            r'\bINSERT\s+INTO\s+([a-zA-Z0-9_\-]+)',
            r'\bTABLE\s+([a-zA-Z0-9_\-]+)',
        ]

        for pattern in patterns:
            matches = re.finditer(pattern, sql_query, re.IGNORECASE)
            for match in matches:
                table_name = match.group(1).strip()
                # Skip if it's already quoted or an alias
                if not ((table_name.startswith('"') and table_name.endswith('"')) or
                       (table_name.startswith('`') and table_name.endswith('`'))):
                    table_names.add(table_name)

        return table_names

    @staticmethod
    def _protected_spans(  # pylint: disable=too-many-branches
        sql_query: str, quote_char: str
    ) -> List[Tuple[int, int]]:
        """``(start, end)`` spans to leave unchanged during identifier rewrites.

        Single- and double-quoted spans, dialect-delimited identifiers, and SQL
        comments are protected in one linear pass. Double quotes are protected
        for every dialect because they are identifiers in T-SQL and may be
        string literals in MySQL. Doubled closing delimiters are escapes.
        """
        closers = {
            "'": "'",
            '"': '"',
            quote_char: ']' if quote_char == '[' else quote_char,
        }
        mysql_backslash_escapes = quote_char == '`'
        unmatched_from: Dict[str, int] = {}
        spans: List[Tuple[int, int]] = []
        i, n = 0, len(sql_query)
        while i < n:
            if (mysql_backslash_escapes and sql_query[i] == '#') or sql_query.startswith('--', i):
                end = sql_query.find('\n', i + 1)
                end = n if end == -1 else end
                spans.append((i, end))
                i = end
                continue
            if sql_query.startswith('/*', i):
                start = i
                depth = 1
                i += 2
                while i < n and depth:
                    if not mysql_backslash_escapes and sql_query.startswith('/*', i):
                        depth += 1
                        i += 2
                    elif sql_query.startswith('*/', i):
                        depth -= 1
                        i += 2
                    else:
                        i += 1
                spans.append((start, i))
                continue

            close = closers.get(sql_query[i])
            if close is None or i + 1 >= unmatched_from.get(close, n + 1):
                i += 1
                continue
            start = i
            i += 1
            while i < n:
                if mysql_backslash_escapes and close in ("'", '"') and sql_query[i] == '\\':
                    i += 2
                    continue
                if sql_query[i] == close:
                    if i + 1 < n and sql_query[i + 1] == close:
                        i += 2
                        continue
                    i += 1
                    spans.append((start, i))
                    break
                i += 1
            else:
                unmatched_from[close] = start + 1
                i = start + 1
        return spans

    @classmethod
    def _sub_outside_delimited(
        cls, pattern: str, replacement: str, sql_query: str, quote_char: str
    ) -> str:
        """Apply a case-insensitive substitution outside literals and delimited names.

        Without this a table name is also matched *inside* an occurrence that is
        already delimited, so ``[user-accounts].id`` turns into
        ``[[user-accounts]].id``, and inside a string literal, which changes
        data rather than identifiers. Matches are found on the whole query, so
        lookarounds still see the real neighbouring text, and any match touching
        a span from :meth:`_protected_spans` is left as it was.

        Args:
            pattern: Regex matching the text to replace.
            replacement: Literal replacement text.
            sql_query: The SQL query to process.
            quote_char: Opening delimiter of the active dialect.

        Returns:
            The query with *pattern* replaced outside protected spans.
        """
        spans = cls._protected_spans(sql_query, quote_char)
        starts = [start for start, _ in spans]
        out, last = [], 0
        for match in re.finditer(pattern, sql_query, re.IGNORECASE):
            idx = bisect.bisect_right(starts, match.start()) - 1
            inside = idx >= 0 and match.start() < spans[idx][1]
            overlaps_next = idx + 1 < len(spans) and spans[idx + 1][0] < match.end()
            if inside or overlaps_next:
                continue
            out.append(sql_query[last:match.start()])
            out.append(replacement)
            last = match.end()
        out.append(sql_query[last:])
        return ''.join(out)

    @classmethod
    def auto_quote_identifiers(
        cls,
        sql_query: str,
        known_tables: Set[str],
        quote_char: str = '"'
    ) -> Tuple[str, bool]:
        """
        Automatically quote table names with special characters in a SQL query.
        
        Args:
            sql_query: The SQL query to process
            known_tables: Set of known table names from the database schema
            quote_char: Quote character to use (default: " for PostgreSQL, use ` for MySQL)
            
        Returns:
            Tuple of (modified_query, was_modified)
        """
        modified = False
        result_query = sql_query

        # Extract potential table names from query
        query_tables = cls.extract_table_names_from_query(sql_query)

        # For each table that needs quoting
        for table in query_tables:
            # Check if this table exists in known schema and needs quoting
            if table in known_tables and cls.needs_quoting(table, quote_char):
                # Quote the table name
                quoted = cls.quote_identifier(table, quote_char)

                # Replace unquoted occurrences with quoted version
                # Use word boundaries to avoid partial replacements
                # Handle cases: FROM table, JOIN table, table.column, etc.
                patterns_to_replace = [
                    (rf'\b{re.escape(table)}\b(?!\s*\.)', quoted),
                    (rf'\b{re.escape(table)}\.', f'{quoted}.'),
                ]

                for pattern, replacement in patterns_to_replace:
                    new_query = cls._sub_outside_delimited(
                        pattern, replacement, result_query, quote_char
                    )
                    if new_query != result_query:
                        modified = True
                        result_query = new_query

        return result_query, modified


class DatabaseSpecificQuoter:  # pylint: disable=too-few-public-methods
    """Factory class to get the appropriate quote character for different databases."""

    @staticmethod
    def get_quote_char(db_type: str) -> str:
        """
        Get the appropriate quote character for a database type.
        
        Args:
            db_type: Database type ('postgresql', 'mysql', etc.)
            
        Returns:
            Quote character to use
        """
        if db_type.lower() in ['mysql', 'mariadb']:
            return '`'
        if db_type.lower() == 'sqlserver':
            return '['
        # PostgreSQL, SQLite use double quotes (standard SQL)
        return '"'
