"""LLM provider and model selection from the environment."""

import pytest

from api.config import _resolve_llm

AZURE_DEFAULTS = ("azure", "azure/gpt-4.1", "azure/text-embedding-ada-002")


@pytest.mark.unit
@pytest.mark.parametrize("env, provider", [
    ({}, "azure"),
    ({"AZURE_API_KEY": "k"}, "azure"),
    ({"OPENAI_API_KEY": ""}, "azure"),
    ({"COHERE_API_KEY": "k"}, "cohere"),
    ({"COHERE_API_KEY": "k", "ANTHROPIC_API_KEY": "k", "VOYAGE_API_KEY": "k"}, "anthropic"),
    ({"ANTHROPIC_API_KEY": "k", "GEMINI_API_KEY": "k"}, "gemini"),
    ({"GEMINI_API_KEY": "k", "OPENAI_API_KEY": "k"}, "openai"),
    ({"OPENAI_API_KEY": "k", "OLLAMA_MODEL": "llama3.1"}, "ollama"),
])
def test_provider_priority(env, provider):
    assert _resolve_llm(env)[0] == provider


@pytest.mark.unit
@pytest.mark.parametrize("env, expected", [
    ({}, AZURE_DEFAULTS),
    ({"AZURE_MODEL": "m", "AZURE_EMBEDDING_MODEL": "e"}, ("azure", "azure/m", "azure/e")),
    ({"OPENAI_API_KEY": "k"}, ("openai", "openai/gpt-4.1", "openai/text-embedding-ada-002")),
    ({"OPENAI_API_KEY": "k", "OPENAI_MODEL": "m", "OPENAI_EMBEDDING_MODEL": "e"}, ("openai", "openai/m", "openai/e")),
    ({"GEMINI_API_KEY": "k"}, ("gemini", "gemini/gemini-3-pro-preview", "gemini/gemini-embedding-001")),
    ({"GEMINI_API_KEY": "k", "GEMINI_MODEL": "m", "GEMINI_EMBEDDING_MODEL": "e"}, ("gemini", "gemini/m", "gemini/e")),
    ({"ANTHROPIC_API_KEY": "k", "VOYAGE_API_KEY": "k"},
     ("anthropic", "anthropic/claude-sonnet-4-5-20250929", "voyage/voyage-3")),
    ({"ANTHROPIC_API_KEY": "k", "VOYAGE_API_KEY": "k", "ANTHROPIC_MODEL": "m"},
     ("anthropic", "anthropic/m", "voyage/voyage-3")),
    ({"COHERE_API_KEY": "k"}, ("cohere", "cohere/command-a-03-2025", "cohere/embed-v4.0")),
    ({"COHERE_API_KEY": "k", "COHERE_MODEL": "m", "COHERE_EMBEDDING_MODEL": "e"}, ("cohere", "cohere/m", "cohere/e")),
    ({"OLLAMA_MODEL": "llama3.1"}, ("ollama", "ollama/llama3.1", "ollama/nomic-embed-text")),
    ({"OLLAMA_MODEL": "llama3.1", "OLLAMA_EMBEDDING_MODEL": "e"}, ("ollama", "ollama/llama3.1", "ollama/e")),
])
def test_defaults_and_provider_overrides(env, expected):
    assert _resolve_llm(env) == expected


@pytest.mark.unit
@pytest.mark.parametrize("env, expected", [
    ({"AZURE_MODEL": "", "AZURE_EMBEDDING_MODEL": ""}, AZURE_DEFAULTS),
    ({"COMPLETION_MODEL": "", "EMBEDDING_MODEL": ""}, AZURE_DEFAULTS),
    ({"COHERE_API_KEY": "k", "COHERE_MODEL": "", "COHERE_EMBEDDING_MODEL": ""},
     ("cohere", "cohere/command-a-03-2025", "cohere/embed-v4.0")),
])
def test_empty_values_fall_back_to_defaults(env, expected):
    assert _resolve_llm(env) == expected


@pytest.mark.unit
def test_completion_and_embedding_model_win():
    env = {
        "AZURE_MODEL": "ignored", "AZURE_EMBEDDING_MODEL": "ignored",
        "COMPLETION_MODEL": "azure/chosen", "EMBEDDING_MODEL": "azure/chosen-embedder",
    }
    assert _resolve_llm(env) == ("azure", "azure/chosen", "azure/chosen-embedder")


@pytest.mark.unit
def test_prefixed_name_is_not_prefixed_again():
    env = {"AZURE_MODEL": "azure/m", "AZURE_EMBEDDING_MODEL": "azure/e"}
    assert _resolve_llm(env) == ("azure", "azure/m", "azure/e")


@pytest.mark.unit
@pytest.mark.parametrize("env, embedding", [
    ({"VOYAGE_API_KEY": "k"}, "voyage/voyage-3"),
    ({"EMBEDDING_MODEL": "voyage/voyage-3-large"}, "voyage/voyage-3-large"),
    ({"VOYAGE_API_KEY": "k", "EMBEDDING_MODEL": "openai/x"}, "openai/x"),
])
def test_anthropic_embeddings(env, embedding):
    assert _resolve_llm({"ANTHROPIC_API_KEY": "k", **env})[2] == embedding


@pytest.mark.unit
def test_anthropic_without_embeddings_fails():
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY is set, but Anthropic has no native embeddings"):
        _resolve_llm({"ANTHROPIC_API_KEY": "k"})


@pytest.mark.unit
def test_graphiti_azure_uses_the_configured_deployment(monkeypatch):
    from api.memory import graphiti_tool
    monkeypatch.setattr(graphiti_tool.Config, "COMPLETION_MODEL", "azure/my-deploy")
    monkeypatch.setenv("MODEL_NAME", "unused")  # so teardown restores MODEL_NAME, which AzureOpenAIConfig overwrites
    assert graphiti_tool.AzureOpenAIConfig().llm_deployment == "my-deploy"
