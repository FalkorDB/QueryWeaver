"""Retries must be spent on failures a replay can change.

A 401 does not become a valid key by asking twice, and a transient 500 on a
batch item should not silently degrade a table description to its name. One
policy decides both: ``_retryable`` judges the failure, ``run_completion`` and
``run_batch_completion`` apply the verdict against the remaining budget.
"""

import types

import pytest

import api.agents.utils as agent_utils

pytestmark = pytest.mark.unit


class _ProviderError(Exception):
    """A provider failure carrying an HTTP verdict, litellm-style."""

    def __init__(self, status_code=None, retry_after=None):
        super().__init__(f"status={status_code}")
        if status_code is not None:
            self.status_code = status_code
        if retry_after is not None:
            self.response = types.SimpleNamespace(
                headers={"retry-after": retry_after}
            )


def _ok(content="ok"):
    message = types.SimpleNamespace(content=content)
    choice = types.SimpleNamespace(message=message)
    return types.SimpleNamespace(choices=[choice])


@pytest.fixture(autouse=True)
def _fast_backoff(monkeypatch):
    monkeypatch.setattr(agent_utils, "_RETRY_BACKOFF_SECONDS", 0.001)


class TestRetryVerdicts:
    """The classification itself, one failure class at a time."""

    @pytest.mark.parametrize("status_code", [400, 401, 403, 404, 422])
    def test_the_request_itself_being_bad_is_permanent(self, status_code):
        assert agent_utils._retryable(_ProviderError(status_code)) is False

    @pytest.mark.parametrize("status_code", [408, 429, 500, 502, 503, 504])
    def test_the_service_having_a_moment_is_transient(self, status_code):
        assert agent_utils._retryable(_ProviderError(status_code)) is True

    def test_a_failure_with_no_verdict_is_transient(self):
        """Timeouts and dropped connections carry no status code."""
        assert agent_utils._retryable(RuntimeError("connection reset")) is True

    def test_retry_after_wins_over_backoff(self):
        delay = agent_utils._retry_delay(
            _ProviderError(429, retry_after="0.25"), attempt=1
        )
        assert delay == 0.25

    def test_retry_after_is_capped(self):
        """A provider asking for an hour cannot eat the whole budget."""
        delay = agent_utils._retry_delay(
            _ProviderError(429, retry_after="3600"), attempt=1
        )
        assert delay <= agent_utils._RETRY_BACKOFF_CAP_SECONDS

    def test_garbage_retry_after_falls_back_to_backoff(self):
        delay = agent_utils._retry_delay(
            _ProviderError(429, retry_after="tomorrow"), attempt=1
        )
        assert delay == agent_utils._RETRY_BACKOFF_SECONDS


class TestRunCompletion:
    """The single-call loop applies the verdicts."""

    def test_a_401_makes_exactly_one_request(self, monkeypatch):
        monkeypatch.setattr(agent_utils.Config, "LLM_MAX_RETRIES", 3,
                            raising=False)
        calls = []

        def unauthorized(**kwargs):
            calls.append(kwargs)
            raise _ProviderError(401)

        monkeypatch.setattr(agent_utils, "completion", unauthorized)

        with pytest.raises(_ProviderError):
            agent_utils.run_completion([{"role": "user", "content": "hi"}],
                                       label="probe")

        assert len(calls) == 1, "a permanent failure was replayed"

    def test_a_transient_failure_is_retried(self, monkeypatch):
        monkeypatch.setattr(agent_utils.Config, "LLM_MAX_RETRIES", 1,
                            raising=False)
        calls = []

        def flaky(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise _ProviderError(500)
            return _ok("recovered")

        monkeypatch.setattr(agent_utils, "completion", flaky)

        result = agent_utils.run_completion(
            [{"role": "user", "content": "hi"}], label="probe")

        assert result == "recovered"
        assert len(calls) == 2


class TestRunBatchCompletion:
    """The batch loop retries only the slots worth retrying."""

    def test_only_transient_failures_are_replayed(self, monkeypatch):
        monkeypatch.setattr(agent_utils.Config, "LLM_MAX_RETRIES", 2,
                            raising=False)
        permanent = _ProviderError(401)
        transient = _ProviderError(500)
        batches = []

        def fake_batch(**kwargs):
            batches.append(kwargs["messages"])
            if len(batches) == 1:
                return [_ok("first"), transient, permanent]
            return [_ok("second")]  # only the transient slot came back

        monkeypatch.setattr(agent_utils, "batch_completion", fake_batch)

        messages = [[{"role": "user", "content": f"table {i}"}]
                    for i in range(3)]
        results = agent_utils.run_batch_completion(messages, model="m",
                                                   label="probe")

        assert len(batches) == 2
        assert batches[1] == [messages[1]], "retry was not scoped to the transient slot"
        assert results[0].choices[0].message.content == "first"
        assert results[1].choices[0].message.content == "second"
        assert results[2] is permanent, "the permanent failure must be kept, not retried"

    def test_a_clean_batch_makes_one_call(self, monkeypatch):
        calls = []

        def fake_batch(**kwargs):
            calls.append(kwargs)
            return [_ok(), _ok()]

        monkeypatch.setattr(agent_utils, "batch_completion", fake_batch)

        results = agent_utils.run_batch_completion(
            [[{"role": "user", "content": "a"}],
             [{"role": "user", "content": "b"}]],
            model="m", label="probe")

        assert len(calls) == 1
        assert len(results) == 2
        # Library retry knobs stay off; the budget bounds the call.
        assert calls[0]["max_retries"] == 0
        assert calls[0]["num_retries"] == 0
        assert calls[0]["timeout"] <= agent_utils.Config.LLM_TIMEOUT

    def test_attempts_run_against_the_remaining_budget(self, monkeypatch):
        """A later attempt gets less time, never a fresh allocation."""
        monkeypatch.setattr(agent_utils.Config, "LLM_MAX_RETRIES", 2,
                            raising=False)
        timeouts = []

        def failing_batch(**kwargs):
            timeouts.append(kwargs["timeout"])
            return [_ProviderError(500)]

        monkeypatch.setattr(agent_utils, "batch_completion", failing_batch)

        results = agent_utils.run_batch_completion(
            [[{"role": "user", "content": "a"}]], model="m", label="probe")

        assert len(timeouts) == 3
        assert timeouts == sorted(timeouts, reverse=True)
        assert isinstance(results[0], _ProviderError)

    def test_a_slot_the_library_never_answered_is_a_failure(self, monkeypatch):
        """A short batch response must not surface as a None 'success'."""

        def short_batch(**kwargs):
            return [_ok("only one")]  # two were asked for

        monkeypatch.setattr(agent_utils, "batch_completion", short_batch)

        results = agent_utils.run_batch_completion(
            [[{"role": "user", "content": "a"}],
             [{"role": "user", "content": "b"}]],
            model="m", label="probe")

        assert results[0].choices[0].message.content == "only one"
        assert isinstance(results[1], Exception), "an unanswered slot leaked as None"
