"""Timeout configuration must be positive.

Zero is not a harmless "unset": PostgreSQL treats a 0 timeout as "no limit",
removing the safeguard entirely, and PyMySQL raises at query time on a 0 socket
timeout. Both are worse than refusing to start.
"""

import importlib
import time

import pytest


@pytest.fixture(autouse=True)
def _restore_config_module():
    """Reload tests replace api.config; put the pristine module back after."""
    yield
    from api import config as api_config
    importlib.reload(api_config)


def _reload_config(monkeypatch, **env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    # ``from ... import`` throughout, for one consistent style; reload needs the
    # module object, which the alias provides.
    from api import config as api_config
    return importlib.reload(api_config)


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
    """LLM_TIMEOUT bounds the whole call, across every attempt.

    The budget is enforced by the retry loop in ``run_completion``, which hands
    each attempt the remaining time. The library's own retry knobs stay off:
    litellm treats ``num_retries`` as overriding ``max_retries``, so relying on
    them made one request while the budget was divided as though several would
    happen.
    """
    from api import config as api_config

    monkeypatch.setattr(api_config.Config, "LLM_TIMEOUT", 90.0, raising=False)
    monkeypatch.setattr(api_config.Config, "LLM_MAX_RETRIES", retries, raising=False)

    assert api_config.Config.llm_attempts() == expected_attempts
    bounds = api_config.Config.llm_call_bounds()
    assert bounds["max_retries"] == 0
    assert bounds["num_retries"] == 0
    # Default is the whole budget, which is right for single-attempt callers.
    assert bounds["timeout"] == 90.0


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


@pytest.mark.unit
@pytest.mark.parametrize("retries", [0, 1, 3])
def test_run_completion_makes_exactly_the_budgeted_attempts(monkeypatch, retries):
    """Attempt count must match the configuration, and be observable.

    litellm treats ``num_retries`` as overriding ``max_retries``, so relying on
    the library pair made one request while the budget was divided as though
    several would happen — no retry, and half the deadline. Retries are driven
    here instead.
    """
    import api.agents.utils as agent_utils

    # Patch the Config the module under test holds: the reload-based tests in
    # this file rebind api.config.Config, so a freshly imported reference can be
    # a different object.
    monkeypatch.setattr(agent_utils.Config, "LLM_TIMEOUT", 5.0, raising=False)
    monkeypatch.setattr(agent_utils.Config, "LLM_MAX_RETRIES", retries, raising=False)

    # Backoff between retries is real behaviour but slow in a test.
    monkeypatch.setattr(agent_utils, "_RETRY_BACKOFF_SECONDS", 0.001)

    calls = []

    def failing_completion(**kwargs):
        calls.append(kwargs["timeout"])
        raise RuntimeError("transient")

    monkeypatch.setattr(agent_utils, "completion", failing_completion)

    with pytest.raises(RuntimeError, match="transient"):
        agent_utils.run_completion([{"role": "user", "content": "hi"}], label="probe")

    assert len(calls) == retries + 1
    # Library retries stay off, and each attempt is handed the remaining budget,
    # so the per-attempt timeout never grows.
    assert all(t <= 5.0 for t in calls)
    assert calls == sorted(calls, reverse=True)


@pytest.mark.unit
def test_run_completion_stops_retrying_when_the_budget_is_spent(monkeypatch):
    """A slow failure consumes the budget, so no further attempt is made."""
    import api.agents.utils as agent_utils

    monkeypatch.setattr(agent_utils.Config, "LLM_TIMEOUT", 0.3, raising=False)
    monkeypatch.setattr(agent_utils.Config, "LLM_MAX_RETRIES", 5, raising=False)

    monkeypatch.setattr(agent_utils, "_RETRY_BACKOFF_SECONDS", 0.001)

    calls = []

    def slow_failing_completion(**_kwargs):
        calls.append(1)
        time.sleep(0.2)
        raise RuntimeError("slow transient")

    monkeypatch.setattr(agent_utils, "completion", slow_failing_completion)

    with pytest.raises(RuntimeError):
        agent_utils.run_completion([{"role": "user", "content": "hi"}], label="probe")

    assert len(calls) < 6, "kept retrying past the budget"


@pytest.mark.unit
def test_library_retry_knobs_are_disabled():
    """Both library mechanisms stay off so they cannot compound or override."""
    import api.agents.utils as agent_utils

    bounds = agent_utils.Config.llm_call_bounds(timeout=7)
    assert bounds == {"timeout": 7, "max_retries": 0, "num_retries": 0}
