# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""One provider x tier table for hosted default models (#15501, #18210)."""

from __future__ import annotations

import pytest

import autobot_shared.ssot_hosted_models as hm


def test_every_provider_has_every_tier():
    assert set(hm.HOSTED_PROVIDER_DEFAULT_MODELS) == {
        "openai",
        "anthropic",
        "groq",
        "mistral",
        "vertexai",
        "openrouter",
        "bedrock",
        "huggingface",
    }
    for provider, models in hm.HOSTED_PROVIDER_DEFAULT_MODELS.items():
        assert set(models) == set(hm.TIERS) and all(models.values()), provider


def test_the_stale_defaults_are_gone():
    """Owner 2026-10-23: mirror the direct providers."""
    assert hm.hosted_default_model("openrouter") == "openai/gpt-4o-mini"
    assert hm.hosted_default_model("bedrock") == hm.BEDROCK_CLAUDE_SONNET4
    flat = {m for models in hm.HOSTED_PROVIDER_DEFAULT_MODELS.values() for m in models.values()}
    assert not flat & {"gpt-3.5-turbo", "claude-3-5-sonnet"}


@pytest.mark.parametrize(
    "provider,env",
    [("openai", "OPENAI_DEFAULT_MODEL"), ("vertexai", "VERTEX_AI_DEFAULT_MODEL"), ("bedrock", "BEDROCK_DEFAULT_MODEL")],
)
def test_the_default_tier_honours_its_env_override(monkeypatch, provider, env):
    monkeypatch.setenv(env, " my-model ")
    assert hm.hosted_default_model(provider) == "my-model"
    assert hm.hosted_default_model(provider, "light") == hm.HOSTED_PROVIDER_DEFAULT_MODELS[provider]["light"]


def test_a_blank_override_is_no_override(monkeypatch):
    monkeypatch.setenv("GROQ_DEFAULT_MODEL", "")
    assert hm.hosted_default_model("groq") == hm.HOSTED_PROVIDER_DEFAULT_MODELS["groq"]["default"]


def test_an_unknown_provider_or_tier_raises():
    with pytest.raises(KeyError):
        hm.hosted_default_model("nope")
    with pytest.raises(KeyError):
        hm.hosted_default_model("openai", "huge")


def test_bedrock_resolves_its_default_to_a_model_id():
    from llm_shared.providers.bedrock import BEDROCK_MODELS

    assert BEDROCK_MODELS[hm.BEDROCK_CLAUDE_SONNET4] == hm.BEDROCK_CLAUDE_SONNET4_ID


def test_a_value_in_the_project_env_file_applies_without_load_dotenv(monkeypatch, tmp_path):
    """#15501 review: the overrides read .env through env_file, as every SSOT setting does; a worker
    or script that never ran load_dotenv must still see the override."""
    model = "mistral-large-latest"
    (tmp_path / ".env").write_text(f"MISTRAL_DEFAULT_MODEL={model}\n", encoding="utf-8")
    monkeypatch.setitem(hm._HostedModelOverrides.model_config, "env_file", str(tmp_path / ".env"))
    monkeypatch.delenv("MISTRAL_DEFAULT_MODEL", raising=False)
    assert hm.hosted_default_model("mistral") == model
    monkeypatch.setenv("MISTRAL_DEFAULT_MODEL", "open-mistral-nemo")
    assert hm.hosted_default_model("mistral") == "open-mistral-nemo", "the process environment wins"
