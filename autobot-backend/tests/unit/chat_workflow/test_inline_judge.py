# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for the inline AgentResponseJudge gate (#10599, §3.3).

Verified scenarios:
  (a) Judge flag OFF (default) → inline_judge_response is a no-op; no LLM call.
  (b) Judge flag ON + score above threshold → judge_count incremented; no hint.
  (c) Judge flag ON + score below threshold + first attempt → hint set; route
      returns generate_response for one regeneration.
  (d) Judge flag ON + judge_count already 1 → no further regeneration (cap).
  (e) Judge call raises exception → node returns {} (non-fatal).
  (f) route_after_judge with no hint → returns persist_conversation.
  (g) Grounding instruction present in prompt when citation flag is enabled.
  (h) structured_output=True forwarded in grounded_agent._extract_claims.
"""

import json
import sys
import types
import typing
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub langchain / langgraph so graph.py can be imported without those packages
# being installed in the test environment.
# ---------------------------------------------------------------------------

_STUBS = {
    "langchain_core": types.ModuleType("langchain_core"),
    "langchain_core.messages": types.ModuleType("langchain_core.messages"),
    "langchain_core.runnables": types.ModuleType("langchain_core.runnables"),
    "xxhash": types.ModuleType("xxhash"),
    "redis": types.ModuleType("redis"),
    "redis.asyncio": types.ModuleType("redis.asyncio"),
    "langgraph": types.ModuleType("langgraph"),
    "langgraph.checkpoint": types.ModuleType("langgraph.checkpoint"),
    "langgraph.checkpoint.redis": types.ModuleType("langgraph.checkpoint.redis"),
    "langgraph.checkpoint.redis.aio": types.ModuleType("langgraph.checkpoint.redis.aio"),
    "langgraph.graph": types.ModuleType("langgraph.graph"),
    "langgraph.types": types.ModuleType("langgraph.types"),
    "typing_extensions": types.ModuleType("typing_extensions"),
}

for _name, _stub in _STUBS.items():
    sys.modules.setdefault(_name, _stub)

for _attr in ("END", "START", "StateGraph"):
    if not hasattr(sys.modules["langgraph.graph"], _attr):
        setattr(sys.modules["langgraph.graph"], _attr, MagicMock())

if not hasattr(sys.modules["langgraph.types"], "interrupt"):
    sys.modules["langgraph.types"].interrupt = MagicMock()

if not hasattr(sys.modules["typing_extensions"], "TypedDict"):
    sys.modules["typing_extensions"].TypedDict = typing.TypedDict

for _attr in ("HumanMessage", "SystemMessage", "AIMessage", "BaseMessage"):
    if not hasattr(sys.modules["langchain_core.messages"], _attr):
        setattr(sys.modules["langchain_core.messages"], _attr, MagicMock())

if not hasattr(sys.modules["langchain_core.runnables"], "RunnableConfig"):
    sys.modules["langchain_core.runnables"].RunnableConfig = MagicMock()

# AsyncRedisSaver must exist so the try/except in graph.py sets _REDIS_CHECKPOINTER_AVAILABLE=True
sys.modules["langgraph.checkpoint.redis.aio"].AsyncRedisSaver = MagicMock()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(
    llm_response: str = "A helpful answer.",
    judge_count: int = 0,
    used_knowledge: bool = False,
    user_message: str = "What is AutoBot?",
    rlm_refinement_hint: str = "",
) -> dict:
    return {
        "llm_response": llm_response,
        "judge_count": judge_count,
        "used_knowledge": used_knowledge,
        "user_message": user_message,
        "reflection_history": [],
        "rlm_refinement_hint": rlm_refinement_hint,
    }


def _make_config() -> dict:
    return {"configurable": {"manager": MagicMock()}}


# ---------------------------------------------------------------------------
# Import the functions under test (after stubs are in place)
# ---------------------------------------------------------------------------


def _load_graph():
    """Load graph.py isolated so stubs take effect before module-level imports."""
    _graph_path = Path(__file__).parent.parent.parent.parent / "chat_workflow" / "graph.py"
    import importlib.util

    spec = importlib.util.spec_from_file_location(f"_graph_judge_test_{id(object())}", _graph_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# inline_judge_response node tests
# ---------------------------------------------------------------------------


class TestInlineJudgeNode:
    """Tests for the inline_judge_response graph node."""

    @pytest.mark.asyncio
    async def test_judge_disabled_is_noop(self) -> None:
        """(a) AUTOBOT_CHAT_INLINE_JUDGE=false → node returns {} without any LLM call."""
        graph_mod = _load_graph()

        mock_ssot = MagicMock()
        mock_ssot.chat_inline_judge_enabled = False

        with patch.object(graph_mod, "_ssot_config", mock_ssot):
            result = await graph_mod.inline_judge_response(_make_state(), _make_config())

        assert result == {}

    @pytest.mark.asyncio
    async def test_empty_response_is_noop(self) -> None:
        """No llm_response in state → node returns {} immediately."""
        graph_mod = _load_graph()

        mock_ssot = MagicMock()
        mock_ssot.chat_inline_judge_enabled = True

        with patch.object(graph_mod, "_ssot_config", mock_ssot):
            result = await graph_mod.inline_judge_response(_make_state(llm_response=""), _make_config())

        assert result == {}

    @pytest.mark.asyncio
    async def test_judge_count_cap_prevents_second_regen(self) -> None:
        """(d) judge_count already 1 → node is a no-op (cap enforcement)."""
        graph_mod = _load_graph()

        mock_ssot = MagicMock()
        mock_ssot.chat_inline_judge_enabled = True

        with patch.object(graph_mod, "_ssot_config", mock_ssot):
            result = await graph_mod.inline_judge_response(_make_state(judge_count=1), _make_config())

        assert result == {}

    @pytest.mark.asyncio
    async def test_judge_exception_is_nonfatal(self) -> None:
        """(e) When the judge raises an exception the node returns {} (non-fatal)."""
        graph_mod = _load_graph()

        mock_ssot = MagicMock()
        mock_ssot.chat_inline_judge_enabled = True
        mock_ssot.chat_inline_judge_threshold = 0.6

        # Pre-register a stub in sys.modules so the lazy import inside the
        # function body resolves to our mock rather than the real class.
        failing_judge = MagicMock()
        failing_judge.assess_response_quality = AsyncMock(side_effect=RuntimeError("LLM down"))
        judge_stub = types.ModuleType("judges.agent_response_judge")
        judge_stub.AgentResponseJudge = MagicMock(return_value=failing_judge)

        with (
            patch.object(graph_mod, "_ssot_config", mock_ssot),
            patch.dict("sys.modules", {"judges.agent_response_judge": judge_stub}),
        ):
            result = await graph_mod.inline_judge_response(_make_state(), _make_config())

        assert result == {}

    @pytest.mark.asyncio
    async def test_low_score_sets_refinement_hint(self) -> None:
        """(c) Low score + first attempt → rlm_refinement_hint set + judge_count=1."""
        graph_mod = _load_graph()

        mock_ssot = MagicMock()
        mock_ssot.chat_inline_judge_enabled = True
        mock_ssot.chat_inline_judge_threshold = 0.6

        low_score_judge = MagicMock()
        low_score_judge.assess_response_quality = AsyncMock(return_value=(False, 0.3, "Quality: 0.30"))
        judge_stub = types.ModuleType("judges.agent_response_judge")
        judge_stub.AgentResponseJudge = MagicMock(return_value=low_score_judge)

        with (
            patch.object(graph_mod, "_ssot_config", mock_ssot),
            patch.dict("sys.modules", {"judges.agent_response_judge": judge_stub}),
        ):
            result = await graph_mod.inline_judge_response(_make_state(), _make_config())

        assert result.get("judge_count") == 1
        hint = result.get("rlm_refinement_hint", "")
        assert "Judge feedback" in hint or "judge" in hint.lower() or "0.3" in hint

    @pytest.mark.asyncio
    async def test_good_score_increments_count_no_hint(self) -> None:
        """(b) Score above threshold → judge_count incremented; no refinement hint."""
        graph_mod = _load_graph()

        mock_ssot = MagicMock()
        mock_ssot.chat_inline_judge_enabled = True
        mock_ssot.chat_inline_judge_threshold = 0.6

        high_score_judge = MagicMock()
        high_score_judge.assess_response_quality = AsyncMock(return_value=(True, 0.85, "Quality: 0.85"))
        judge_stub = types.ModuleType("judges.agent_response_judge")
        judge_stub.AgentResponseJudge = MagicMock(return_value=high_score_judge)

        with (
            patch.object(graph_mod, "_ssot_config", mock_ssot),
            patch.dict("sys.modules", {"judges.agent_response_judge": judge_stub}),
        ):
            result = await graph_mod.inline_judge_response(_make_state(), _make_config())

        assert result.get("judge_count") == 1
        assert not result.get("rlm_refinement_hint", "")


# ---------------------------------------------------------------------------
# route_after_judge routing function
# ---------------------------------------------------------------------------


class TestRouteAfterJudge:
    """Tests for the route_after_judge conditional edge function."""

    def test_no_hint_routes_to_persist(self) -> None:
        """(f) No refinement hint → persist_conversation."""
        graph_mod = _load_graph()
        state = _make_state()
        assert graph_mod.route_after_judge(state) == "persist_conversation"

    def test_hint_and_count_one_routes_to_generate(self) -> None:
        """(c) Hint present + judge_count==1 → generate_response for one retry."""
        graph_mod = _load_graph()
        state = {
            **_make_state(),
            "rlm_refinement_hint": "[Judge feedback] Please revise.",
            "judge_count": 1,
        }
        assert graph_mod.route_after_judge(state) == "generate_response"

    def test_hint_and_count_two_routes_to_persist(self) -> None:
        """(d) hint present but judge_count>=2 → cap respected → persist."""
        graph_mod = _load_graph()
        state = {
            **_make_state(),
            "rlm_refinement_hint": "[Judge feedback] Please revise.",
            "judge_count": 2,
        }
        assert graph_mod.route_after_judge(state) == "persist_conversation"

    def test_hint_count_zero_routes_to_persist(self) -> None:
        """hint set but judge_count==0 → hint came from RLM, not the judge → persist."""
        graph_mod = _load_graph()
        state = {
            **_make_state(),
            "rlm_refinement_hint": "Some RLM hint",
            "judge_count": 0,
        }
        assert graph_mod.route_after_judge(state) == "persist_conversation"


# ---------------------------------------------------------------------------
# Grounding instruction in prompt (§3.1 / §3.2)
# ---------------------------------------------------------------------------


class TestGroundingInPrompt:
    """(g) Verify the citation instruction appears in KB context when enabled."""

    def test_citation_instruction_present_when_enabled(self, monkeypatch) -> None:
        """build_grounded_context includes the grounding sentence when flag=True."""
        from autobot_shared.ssot_config import config
        from services.knowledge.service import build_grounded_context

        monkeypatch.setattr(config, "chat_citation_instruction_enabled", True, raising=False)
        ctx = build_grounded_context(["Redis is configured in config/redis.yaml"])
        assert "[Source 1]" in ctx
        assert "don't know" in ctx or "you don't know" in ctx

    def test_source_labels_present_when_instruction_disabled(self, monkeypatch) -> None:
        """[Source N] labels always present even when instruction is off."""
        from autobot_shared.ssot_config import config
        from services.knowledge.service import build_grounded_context

        monkeypatch.setattr(config, "chat_citation_instruction_enabled", False, raising=False)
        ctx = build_grounded_context(["fact one", "fact two"])
        assert "[Source 1] fact one" in ctx
        assert "[Source 2] fact two" in ctx

    def test_empty_input_returns_empty_string(self) -> None:
        """build_grounded_context([]) must return an empty string."""
        from services.knowledge.service import build_grounded_context

        assert build_grounded_context([]) == ""


# ---------------------------------------------------------------------------
# structured_output forwarded in grounded_agent._extract_claims (§3.4)
# ---------------------------------------------------------------------------


class TestStructuredOutputInExtractClaims:
    """(h) _extract_claims passes structured_output=True to the LLM call."""

    @pytest.mark.asyncio
    async def test_structured_output_forwarded(self) -> None:
        """_extract_claims uses structured_output=True so JSON isn't silently lost."""
        from services.grounded_agent import GroundedAgent

        fake_response = types.SimpleNamespace(content=json.dumps([]))
        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value=fake_response)

        agent = GroundedAgent.__new__(GroundedAgent)
        agent.llm_service = mock_llm

        await agent._extract_claims("test query", "test response")

        call_kwargs = mock_llm.chat.call_args[1]
        assert (
            call_kwargs.get("structured_output") is True
        ), "_extract_claims must pass structured_output=True to prevent silent JSON drops"
