# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Review fixes on the Claude-ID SSOT: the final SDK kwargs, the beta header, pricing, chains, hires (#20884)."""

import asyncio

import pytest

from autobot_shared.ssot_claude_models import CLAUDE_HAIKU, CLAUDE_OPUS, CLAUDE_SONNET
from llm_shared.models import LLMRequest
from llm_shared.providers.anthropic import AnthropicProvider

_BETA = "interleaved-thinking-2025-05-14"


def _sdk_kwargs(model: str, api_kwargs: dict) -> tuple[dict, dict]:
    request = LLMRequest(messages=[{"role": "user", "content": "hi"}], metadata={"api_kwargs": api_kwargs})
    kwargs, headers, _ = AnthropicProvider(settings={"api_key": "k"})._build_request_kwargs(model, request)
    return kwargs, headers


def test_a_caller_enabled_thinking_dict_becomes_adaptive_on_a_5x_model():
    kwargs, headers = _sdk_kwargs(
        CLAUDE_SONNET, {"thinking": {"type": "enabled", "budget_tokens": 63000}, "max_tokens": 64000}
    )
    assert kwargs["thinking"] == {"type": "adaptive"}
    assert "budget_tokens" not in str(kwargs)
    assert kwargs["output_config"]["effort"] == "max"
    assert kwargs["max_tokens"] == 64000
    assert _BETA not in str(headers)


def test_a_caller_enabled_thinking_dict_is_kept_on_a_pre_4_6_model():
    kwargs, _ = _sdk_kwargs("claude-sonnet-4-20250514", {"thinking": {"type": "enabled", "budget_tokens": 5000}})
    assert kwargs["thinking"] == {"type": "enabled", "budget_tokens": 5000}


def test_effort_driven_request_for_claude_sonnet_5_5_reaches_the_sdk_adaptive_with_no_budget():
    """Provider path (``metadata.api_kwargs.thinking_tokens``): the only path that reaches the Anthropic SDK."""
    kwargs, headers = _sdk_kwargs(CLAUDE_SONNET, {"thinking_tokens": 10000})
    assert kwargs["thinking"] == {"type": "adaptive"}
    assert "budget_tokens" not in str(kwargs)
    assert _BETA not in str(headers)


def test_the_chat_workflow_user_pref_kwargs_are_adaptive_for_sonnet_5_5_and_beta_only_for_pre_4_6():
    from chat_workflow.reasoning_kwargs import build_reasoning_api_kwargs

    ctx = {"thinking_mode_enabled": True, "thinking_budget_tokens": 8000}
    adaptive = asyncio.run(build_reasoning_api_kwargs(ctx, CLAUDE_SONNET))
    assert adaptive["thinking"] == {"type": "adaptive"} and "budget_tokens" not in str(adaptive)
    assert "betas" not in adaptive
    old = asyncio.run(build_reasoning_api_kwargs(ctx, "claude-sonnet-4-20250514"))
    assert old["thinking"]["budget_tokens"] == 8000
    assert old["betas"] == [_BETA]


def test_the_fallback_pricing_patterns_point_at_the_current_generation():
    from services.llm_cost_tracker import LLMCostTracker

    patterns = dict(LLMCostTracker._FALLBACK_PATTERNS)
    assert patterns["claude-opus"] == CLAUDE_OPUS
    assert patterns["claude-sonnet"] == CLAUDE_SONNET
    assert patterns["claude-haiku"] == CLAUDE_HAIKU
    assert patterns["claude"] == CLAUDE_SONNET


def test_haiku_cache_read_is_unknown_not_free():
    from llm_shared.pricing.anthropic_source import AnthropicPricingSource

    rows = asyncio.run(AnthropicPricingSource().fetch())
    assert rows[CLAUDE_HAIKU].cache_read_per_1m is None
    assert rows[CLAUDE_SONNET].cache_read_per_1m == 0.20


def test_every_still_listed_legacy_anthropic_id_keeps_a_default_chain():
    from llm_shared.fallback_chain import FallbackChainManager
    from llm_shared.providers.anthropic import _ANTHROPIC_MODELS

    manager = FallbackChainManager()
    for model in _ANTHROPIC_MODELS:
        if "haiku" in model:
            continue  # the cheapest tier has nothing below it
        assert manager.get_chain(model) is not None, model


@pytest.mark.parametrize(
    ("old", "expected"),
    [
        ("claude-sonnet-4-6", CLAUDE_SONNET),
        ("claude-haiku-4-5-20251001", CLAUDE_HAIKU),
        ("sonnet", CLAUDE_SONNET),
        ("haiku", CLAUDE_HAIKU),
    ],
)
def test_the_hire_form_accepts_earlier_generation_ids_by_mapping_them(monkeypatch, old, expected):
    from llc.api import agent_hires

    monkeypatch.setattr(agent_hires, "registered_adapter_types", lambda: ["claude_code"])
    monkeypatch.setattr(agent_hires, "adapter_unavailable_reason", lambda _t: None)
    request = agent_hires.AgentHireRequest.model_construct(model=old, adapter_type=None)
    assert agent_hires._validate_hire(request) == expected


def test_a_hire_model_that_maps_to_no_hireable_tier_is_still_a_422(monkeypatch):
    from fastapi import HTTPException

    from llc.api import agent_hires

    request = agent_hires.AgentHireRequest.model_construct(model="claude-opus-4-6", adapter_type=None)
    with pytest.raises(HTTPException) as caught:
        agent_hires._validate_hire(request)
    assert caught.value.status_code == 422


def test_a_stored_old_haiku_row_still_renders_the_haiku_template():
    from autobot_shared.ssot_claude_models import current_claude_model
    from llc.api import agent_hires

    stored = "claude-haiku-4-5-20251001"
    assert current_claude_model(stored) == agent_hires.HAIKU_MODEL
    assert agent_hires.HAIKU_MODEL != stored  # the comparison at the response site is on resolved IDs


def test_a_yaml_read_failure_keeps_the_anthropic_defaults(monkeypatch):
    from llc.services import model_tiers

    monkeypatch.setattr(model_tiers, "_TIERS_YAML_PATH", "/nonexistent/model-tiers.yml")
    model_tiers._load_platform_defaults.cache_clear()
    try:
        assert model_tiers._load_platform_defaults()["anthropic"] == {
            "senior": CLAUDE_SONNET,
            "assistant": CLAUDE_HAIKU,
        }
    finally:
        model_tiers._load_platform_defaults.cache_clear()
