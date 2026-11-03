# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#19733: the failsafe has a real fallback, on models every install pulls."""

import asyncio
import re
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from agents.failsafe_models import failsafe_primary_model, failsafe_secondary_model
from agents.llm_failsafe_agent import LLMFailsafeAgent, LLMTier
from autobot_shared.agent_model_tiers import AGENT_TIERS, TIER_MODELS
from autobot_shared.ssot_config import AgentConfigurationError

_ROOT = Path(__file__).resolve().parents[2]


def test_the_two_models_differ_and_every_install_pulls_both() -> None:
    primary = TIER_MODELS[AGENT_TIERS["llm_failsafe"]]
    secondary = TIER_MODELS[AGENT_TIERS["llm_failsafe_secondary"]]
    assert primary != secondary
    role = _ROOT / "autobot-slm-backend" / "ansible" / "roles" / "llm" / "defaults" / "main.yml"
    assert {primary, secondary} <= set(yaml.safe_load(role.read_text(encoding="utf-8"))["llm_cpu_models"])


def test_the_backend_template_derives_them_from_the_tier_variables() -> None:
    template = _ROOT / "autobot-slm-backend" / "ansible" / "roles" / "backend" / "templates" / "backend.env.j2"
    text = template.read_text(encoding="utf-8")
    assert re.search(r"^AUTOBOT_LLM_FAILSAFE_MODEL=\{\{ backend_routing_model\b", text, re.M)
    assert re.search(r"^AUTOBOT_LLM_FAILSAFE_SECONDARY_MODEL=\{\{ backend_light_model\b", text, re.M)


def test_the_ai_stack_service_gets_what_the_failsafe_needs() -> None:
    """Its server creates ClassificationAgent, which raises without these."""
    template = _ROOT / "autobot-slm-backend" / "ansible" / "roles" / "ai-stack" / "templates" / "ai-stack.env.j2"
    text = template.read_text(encoding="utf-8")
    expected = {
        "PROVIDER": "ollama",
        "ENDPOINT": "{{ ai_chat_endpoint }}",
    }
    for key, value in expected.items():
        assert re.search(rf"^AUTOBOT_LLM_FAILSAFE_{key}={re.escape(value)}$", text, re.M), key


def test_the_failsafe_starts_with_no_model_setting(monkeypatch) -> None:
    """The ai-stack service states no failsafe model; the tier table supplies it, so it can't disagree."""
    monkeypatch.delenv("AUTOBOT_LLM_FAILSAFE_MODEL", raising=False)
    monkeypatch.delenv("AUTOBOT_LLM_FAILSAFE_SECONDARY_MODEL", raising=False)
    primary = failsafe_primary_model()
    assert primary == TIER_MODELS[AGENT_TIERS["llm_failsafe"]]
    assert failsafe_secondary_model(primary) == TIER_MODELS[AGENT_TIERS["llm_failsafe_secondary"]]


def test_a_blank_setting_counts_as_unset(monkeypatch) -> None:
    monkeypatch.setenv("AUTOBOT_LLM_FAILSAFE_MODEL", "   ")
    monkeypatch.setenv("AUTOBOT_LLM_FAILSAFE_SECONDARY_MODEL", "   ")
    primary = failsafe_primary_model()
    assert primary == TIER_MODELS[AGENT_TIERS["llm_failsafe"]]
    assert failsafe_secondary_model(primary) == TIER_MODELS[AGENT_TIERS["llm_failsafe_secondary"]]


def test_a_host_can_still_name_the_model(monkeypatch) -> None:
    monkeypatch.setenv("AUTOBOT_LLM_FAILSAFE_MODEL", "chosen:1b")
    assert failsafe_primary_model() == "chosen:1b"


def test_the_same_model_twice_is_refused(monkeypatch) -> None:
    monkeypatch.setenv("AUTOBOT_LLM_FAILSAFE_SECONDARY_MODEL", "m")
    with pytest.raises(AgentConfigurationError):
        failsafe_secondary_model("m")


def test_an_unset_secondary_uses_the_tier(monkeypatch) -> None:
    monkeypatch.delenv("AUTOBOT_LLM_FAILSAFE_SECONDARY_MODEL", raising=False)
    assert failsafe_secondary_model("m") == TIER_MODELS["light"]


def test_a_host_already_on_the_default_secondary_gets_the_other_tier(monkeypatch) -> None:
    monkeypatch.delenv("AUTOBOT_LLM_FAILSAFE_SECONDARY_MODEL", raising=False)
    assert failsafe_secondary_model(TIER_MODELS["light"]) == TIER_MODELS["routing"]


def test_the_fallback_really_asks_a_different_model() -> None:
    """Both tiers used to call the LLM with no model, so the names were only labels."""
    agent = LLMFailsafeAgent.__new__(LLMFailsafeAgent)
    agent.logger = MagicMock()
    agent.primary_models, agent.secondary_models = ["first"], ["second"]
    agent.tier_stats = {tier: {"requests": 0, "failures": 0, "avg_time": 0.0} for tier in LLMTier}
    agent._update_tier_stats = agent._mark_tier_unhealthy = lambda *args, **kwargs: None
    agent.timeouts = {tier: 5.0 for tier in LLMTier}
    agent._create_structured_messages = lambda prompt, context: [{"role": "user", "content": prompt}]
    agent._simplify_prompt = lambda prompt: prompt
    agent._build_llm_response = lambda response, tier, model, *rest, **kw: SimpleNamespace(tier=tier, model=model)

    async def chat(_messages, *, model_name, llm_type):
        if model_name == "first":  # how llm.chat really reports a failure: it doesn't raise
            return SimpleNamespace(content="", error="model not pulled")
        return SimpleNamespace(content="an answer", error=None)

    service = MagicMock(chat=AsyncMock(side_effect=chat))
    with patch("services.llm_service.get_llm_service", return_value=service):
        result = asyncio.run(agent._try_primary_llm("q", None, time.time()))
    assert (result.tier, result.model) == (LLMTier.SECONDARY, "second")
    assert [c.kwargs["model_name"] for c in service.chat.await_args_list] == ["first", "second"]
