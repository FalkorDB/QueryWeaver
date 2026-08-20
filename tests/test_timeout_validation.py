"""Timeout configuration must be positive.

Zero is not a harmless "unset": PostgreSQL treats a 0 timeout as "no limit",
removing the safeguard entirely, and PyMySQL raises at query time on a 0 socket
timeout. Both are worse than refusing to start.
"""

import importlib

import pytest


def _reload_config(monkeypatch, **env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    import api.config
    return importlib.reload(api.config)


@pytest.mark.unit
@pytest.mark.parametrize("name", [
    "DB_CONNECT_TIMEOUT",
    "DB_STATEMENT_TIMEOUT",
    "LLM_TIMEOUT",
])
@pytest.mark.parametrize("value", ["0", "-1"])
def test_zero_or_negative_timeouts_are_rejected(monkeypatch, name, value):
    with pytest.raises(ValueError, match="greater than 0"):
        _reload_config(monkeypatch, **{name: value})


@pytest.mark.unit
def test_non_numeric_timeout_is_rejected(monkeypatch):
    with pytest.raises(ValueError, match="positive number"):
        _reload_config(monkeypatch, DB_CONNECT_TIMEOUT="abc")


@pytest.mark.unit
def test_defaults_are_positive(monkeypatch):
    """And a clean environment still loads."""
    for name in ("DB_CONNECT_TIMEOUT", "DB_STATEMENT_TIMEOUT", "LLM_TIMEOUT"):
        monkeypatch.delenv(name, raising=False)
    module = _reload_config(monkeypatch)
    assert module.Config.DB_CONNECT_TIMEOUT > 0
    assert module.Config.DB_STATEMENT_TIMEOUT > 0
    assert module.Config.LLM_TIMEOUT > 0
    assert module.Config.LLM_MAX_RETRIES >= 0
