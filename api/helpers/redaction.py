"""Redact credentials from text before it is persisted or logged."""

import re

_SENSITIVE_VALUE = re.compile(
    r"""(?ix)
    (?P<quote>["']?)
    (?P<key>password|token|secret|api[_-]?key|authorization)
    (?P=quote)
    \s*[=:]\s*
    (?P<value_quote>["']?)
    (?:(?:bearer|basic|token)\s+)?
    [^\s,;}]+
    (?P=value_quote)
    """
)
_CONNECTION_PASSWORD = re.compile(
    r"(?i)\b([a-z][a-z0-9+.\-]*://[^:@/\s]+:)[^@/\s]+@"
)


def redact_sensitive_text(value: str, limit: int = 4000) -> str:
    """Remove common credential forms and embedded URL passwords."""
    message = _SENSITIVE_VALUE.sub(
        lambda match: f"{match.group('quote')}{match.group('key')}"
        f"{match.group('quote')}: [REDACTED]",
        value,
    )
    message = _CONNECTION_PASSWORD.sub(r"\1[REDACTED]@", message)
    return message[:limit]
