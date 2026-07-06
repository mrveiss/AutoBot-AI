# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for #10580 — best_prompt_template threaded from LearnedStrategy into routing result.

Verifies:
- A high-confidence LearnedStrategy with best_prompt_template produces a routing
  result that includes ``learned_prompt_template``.
- A strategy below the confidence threshold does NOT populate the field.
- The template is then rendered into the planning prompt by build_planning_prompt.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Hollow stubs so agents/* can be imported without heavy optional deps.
# ---------------------------------------------------------------------------
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ORCH_DIR = _BACKEND_DIR / "agents" / "agent_orchestration"

if "agents" not in sys.modules:
    _agents_pkg = types.ModuleType("agents")
    _agents_pkg.__path__ = [str(_BACKEND_DIR / "agents")]  # type: ignore[assignment]
    _agents_pkg.__package__ = "agents"
    sys.modules["agents"] = _agents_pkg

if "agents.agent_orchestration" not in sys.modules:
    _orch_pkg = types.ModuleType("agents.agent_orchestration")
    _orch_pkg.__path__ = [str(_ORCH_DIR)]  # type: ignore[assignment]
    _orch_pkg.__package__ = "agents.agent_orchestration"
    sys.modules["agents.agent_orchestration"] = _orch_pkg

if "agents.agent_orchestration.rl_router" not in sys.modules:
    _rl_stub = types.ModuleType("agents.agent_orchestration.rl_router")
    _rl_stub.RLRouter = type("RLRouter", (), {})  # type: ignore[attr-defined]
    sys.modules["agents.agent_orchestration.rl_router"] = _rl_stub

# Add backend to sys.path for autobot_shared imports.
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))
if str(_BACKEND_DIR.parent / "autobot_shared") not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR.parent))

from agents.agent_orchestration.routing import AgentRouter  # noqa: E402
from agents.agent_orchestration.types import AgentCapabilityDescriptor, AgentType  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def minimal_capabilities():
    return {
        AgentType.CHAT: AgentCapabilityDescriptor(
            agent_type=AgentType.CHAT,
            model_size="small",
            specialization="chat",
            strengths=["conversation"],
            limitations=[],
            resource_usage="low",
        )
    }


@pytest.fixture()
def mock_llm():
    llm = AsyncMock()
    llm.chat_completion = AsyncMock(
        return_value={
            "message": {
                "content": (
                    '{"strategy": "single_agent", "primary_agent": "chat", '
                    '"secondary_agents": [], "confidence": 0.9, "reasoning": "test"}'
                )
            }
        }
    )
    return llm


def _make_strategy(confidence: float, best_prompt_template: str, best_approach: str = "chat"):
    """Build a minimal LearnedStrategy-like object."""
    s = MagicMock()
    s.confidence = confidence
    s.best_approach = best_approach
    s.best_prompt_template = best_prompt_template
    s.sample_size = 10
    return s


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_build_learned_result_includes_template(minimal_capabilities, mock_llm):
    """High-confidence strategy with non-empty template → key present in result."""
    router = AgentRouter(minimal_capabilities, mock_llm)
    strategy = _make_strategy(confidence=0.9, best_prompt_template="Complete this chat task: {goal}")
    result = router._build_learned_result(strategy, "chat")
    assert "learned_prompt_template" in result, "learned_prompt_template must be threaded through"
    assert "{goal}" in result["learned_prompt_template"]


def test_build_learned_result_empty_template_omits_key(minimal_capabilities, mock_llm):
    """Strategy with empty best_prompt_template → key absent from result."""
    router = AgentRouter(minimal_capabilities, mock_llm)
    strategy = _make_strategy(confidence=0.9, best_prompt_template="")
    result = router._build_learned_result(strategy, "chat")
    assert "learned_prompt_template" not in result


@pytest.mark.asyncio
async def test_check_learned_strategy_below_threshold_returns_none(minimal_capabilities, mock_llm):
    """Strategy below LEARNED_STRATEGY_CONFIDENCE threshold → _check_learned_strategy returns None."""
    import types as _types

    router = AgentRouter(minimal_capabilities, mock_llm)
    low_strategy = _make_strategy(confidence=0.5, best_prompt_template="Use this: {goal}")

    # TaskPatternLearner is imported locally inside _check_learned_strategy via
    # ``from agents.task_pattern_learner import …`` — inject a stub module so
    # that import resolves without touching Redis or any real learner.
    fake_learner_inst = MagicMock()
    fake_learner_inst.normalize_task_type = lambda t: t
    fake_learner_inst.get_learned_strategy = AsyncMock(return_value=low_strategy)

    _tpl_mod = _types.ModuleType("agents.task_pattern_learner")
    _tpl_mod.TaskPatternLearner = MagicMock(return_value=fake_learner_inst)  # type: ignore[attr-defined]
    _tpl_mod.LEARNED_STRATEGY_CONFIDENCE = 0.7  # type: ignore[attr-defined]
    sys.modules["agents.task_pattern_learner"] = _tpl_mod

    router._strategy_cache.clear()
    result = await router._check_learned_strategy("hello", {"task_type": "chat"})

    assert result is None, "Below-threshold strategy must not be applied"


@pytest.mark.asyncio
async def test_check_learned_strategy_above_threshold_has_template(minimal_capabilities, mock_llm):
    """Strategy above threshold with template → result includes learned_prompt_template."""
    import types as _types

    router = AgentRouter(minimal_capabilities, mock_llm)
    high_strategy = _make_strategy(confidence=0.85, best_prompt_template="Respond concisely: {goal}")

    fake_learner_inst = MagicMock()
    fake_learner_inst.normalize_task_type = lambda t: t
    fake_learner_inst.get_learned_strategy = AsyncMock(return_value=high_strategy)

    _tpl_mod = _types.ModuleType("agents.task_pattern_learner")
    _tpl_mod.TaskPatternLearner = MagicMock(return_value=fake_learner_inst)  # type: ignore[attr-defined]
    _tpl_mod.LEARNED_STRATEGY_CONFIDENCE = 0.7  # type: ignore[attr-defined]
    sys.modules["agents.task_pattern_learner"] = _tpl_mod

    router._strategy_cache.clear()
    result = await router._check_learned_strategy("hello", {"task_type": "chat"})

    assert result is not None
    assert "learned_prompt_template" in result
    assert "goal" in result["learned_prompt_template"]


def test_build_planning_prompt_includes_learned_template():
    """build_planning_prompt with learned_prompt_template → template text in rendered prompt."""
    import sys

    if str(_BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(_BACKEND_DIR))

    from orchestration.orchestrator_prompts import build_planning_prompt

    prompt = build_planning_prompt(
        "deploy service X",
        "{}",
        learned_prompt_template="Learned: deploy using blue-green for {goal}",
    )
    assert "Learned: deploy using blue-green" in prompt, "Learned template must appear in rendered prompt"
    assert "deploy service X" in prompt


def test_build_planning_prompt_no_template_unchanged():
    """build_planning_prompt without template → prompt matches baseline (no extra section)."""
    from orchestration.orchestrator_prompts import build_planning_prompt

    prompt = build_planning_prompt("deploy service X", "{}")
    assert "Learned approach" not in prompt
