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


@pytest.mark.unit
@pytest.mark.parametrize("retries,expected_attempts", [(0, 1), (1, 2), (3, 4)])
def test_llm_timeout_is_a_total_budget(monkeypatch, retries, expected_attempts):
    """LLM_TIMEOUT bounds the whole call, not each attempt.

    The provider applies its timeout per attempt, so leaving the configured
    value there made the real ceiling a multiple of it: a 3s timeout took
    10.8s to fail. The per-attempt value is now the budget divided by the
    number of attempts.
    """
    from api.config import Config

    monkeypatch.setattr(Config, "LLM_TIMEOUT", 90.0, raising=False)
    monkeypatch.setattr(Config, "LLM_MAX_RETRIES", retries, raising=False)

    bounds = Config.llm_call_bounds()
    assert bounds["max_retries"] == retries
    # litellm's own retry loop stays off so the two cannot compound.
    assert bounds["num_retries"] == 0
    assert bounds["timeout"] == 90.0 / expected_attempts
    # The worst case across every attempt stays within the budget.
    assert bounds["timeout"] * expected_attempts <= Config.LLM_TIMEOUT


@pytest.mark.unit
def test_embeddings_share_the_same_bounds(monkeypatch):
    """One place defines the ceiling, so embeddings cannot drift from it."""
    from api.config import Config

    monkeypatch.setattr(Config, "LLM_TIMEOUT", 60.0, raising=False)
    monkeypatch.setattr(Config, "LLM_MAX_RETRIES", 1, raising=False)
    assert Config.EMBEDDING_MODEL._embedding_kwargs() == Config.llm_call_bounds()


@pytest.mark.unit
def test_call_site_bound_overrides_are_logged(monkeypatch, caplog):
    """An explicit override is allowed but must not be silent."""
    import api.agents.utils as agent_utils

    def fake_completion(**kwargs):
        assert kwargs["timeout"] == 1.5
        message = type("M", (), {"content": "ok"})()
        choice = type("C", (), {"message": message})()
        return type("R", (), {"choices": [choice]})()

    monkeypatch.setattr(agent_utils, "completion", fake_completion)

    with caplog.at_level("INFO"):
        agent_utils.run_completion([{"role": "user", "content": "hi"}],
                                   label="probe", timeout=1.5)

    assert "bound overrides in effect" in caplog.text, "override was not logged"
    assert "timeout" in caplog.text
