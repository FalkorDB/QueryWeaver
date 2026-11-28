"""The request Anthropic receives must only carry settings its models accept.

These go through the real LiteLLM and stop at the HTTP layer, so they assert on
the payload that would be sent rather than on the arguments handed to LiteLLM.
"""

import json

import pytest
from litellm.llms.custom_httpx.http_handler import HTTPHandler

from api.agents import utils as agent_utils

MESSAGES = [{"role": "user", "content": "hi"}]


@pytest.fixture(name="sent")
def _sent(monkeypatch):
    """Capture outgoing Anthropic payloads without touching the network."""
    payloads = []

    def capture(_self, *_args, **kwargs):
        data = kwargs.get("data") or kwargs.get("json")
        payloads.append(json.loads(data) if isinstance(data, (str, bytes)) else data)
        raise RuntimeError("stopped before the network")

    monkeypatch.setattr(HTTPHandler, "post", capture)
    monkeypatch.setattr(agent_utils.Config, "LLM_MAX_RETRIES", 0, raising=False)
    return payloads


def _single(model):
    with pytest.raises(Exception):
        agent_utils.run_completion(MESSAGES, custom_model=model,
                                   custom_api_key="key", temperature=0)


def _batch(model):
    agent_utils.run_batch_completion([MESSAGES], model=model, api_key="key",
                                     temperature=0, max_tokens=50)


@pytest.mark.unit
@pytest.mark.parametrize("call", [_single, _batch])
def test_sonnet_5_5_gets_no_sampling_params_and_no_upfront_thinking(call, sent):
    call("anthropic/claude-sonnet-5-5")

    assert len(sent) == 1, "the request never left LiteLLM"
    assert "temperature" not in sent[0]
    assert "top_p" not in sent[0]
    # Adaptive thinking is on when the field is absent and counts against the
    # small max_tokens these callers use.
    assert sent[0]["thinking"] == {"type": "between_tools"}


@pytest.mark.unit
@pytest.mark.parametrize("call", [_single, _batch])
def test_earlier_claude_models_keep_temperature_without_top_p(call, sent):
    call("anthropic/claude-haiku-4-5")

    assert len(sent) == 1
    assert sent[0]["temperature"] == 0
    assert "top_p" not in sent[0]
    assert "thinking" not in sent[0]


@pytest.mark.unit
def test_other_providers_are_unchanged(monkeypatch):
    calls = []

    def fake_completion(**kwargs):
        calls.append(kwargs)
        raise ValueError("stop")

    monkeypatch.setattr(agent_utils, "completion", fake_completion)
    with pytest.raises(ValueError):
        agent_utils.run_completion(MESSAGES, custom_model="openai/gpt-4.1",
                                   temperature=0)

    assert calls[0]["top_p"] == 1
    assert "drop_params" not in calls[0]
