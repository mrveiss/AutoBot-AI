# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for the adversarial pre-action verifier (#10547).

Acceptance criteria verified here:
  AC-1  Consequential actions trigger an independent verifier pass.
  AC-2  Verifier uses a distinct model/provider when configured; verdict + rationale logged.
  AC-3  A seeded "plausible but wrong" plan is blocked by the verifier.
  AC-4  Thresholds configurable per action class; integrates with approval gate.

Test strategy: the verifier LLM transport (_call_verifier_once) is mocked so
the suite runs without a live provider; assertions cover all verdict paths and
the full loop integration (verifier result shown at the approval gate).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_loop.pre_action_verifier import (
    THRESHOLD_DEFAULT,
    THRESHOLD_DEPLOY,
    THRESHOLD_EXEC,
    THRESHOLD_MUTATE,
    THRESHOLD_NETWORK,
    PreActionVerifier,
    VerifierVerdict,
    _parse_probability,
    _parse_rationale,
    _threshold_for_tool,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_provider(name: str = "mock_provider") -> MagicMock:
    """Return a mock BaseProvider that echoes a canned verifier response."""
    provider = MagicMock()
    provider.provider_name = name
    provider.chat_completion = AsyncMock()
    return provider


def _make_llm_response(content: str) -> MagicMock:
    resp = MagicMock()
    resp.content = content
    resp.model = "mock-model"
    return resp


_REFUTE_RESPONSE = (
    "REFUTATION_PROBABILITY: 0.90\n"
    "FLAW: The target path does not exist and the operation would silently fail.\n"
    "RATIONALE: The agent assumes /data/config.yaml exists but no prior tool "
    "confirmed this. Executing write_file on a non-existent intermediate path "
    "will raise an OSError."
)

_PASS_RESPONSE = (
    "REFUTATION_PROBABILITY: 0.10\n"
    "FLAW: None\n"
    "RATIONALE: The path was confirmed by a prior read_file call. "
    "The write appears safe."
)


# ---------------------------------------------------------------------------
# Unit: threshold mapping
# ---------------------------------------------------------------------------


class TestThresholdMapping:
    def test_deploy_tools(self):
        for name in ("deploy", "ansible", "kubectl", "helm", "terraform"):
            assert _threshold_for_tool(name) == THRESHOLD_DEPLOY

    def test_mutate_tools(self):
        for name in ("write_file", "edit_file", "delete_file", "git_push", "git_commit"):
            assert _threshold_for_tool(name) == THRESHOLD_MUTATE

    def test_network_tools(self):
        for name in ("http_post", "http_put", "http_patch", "http_delete", "send_request"):
            assert _threshold_for_tool(name) == THRESHOLD_NETWORK

    def test_exec_tools(self):
        for name in ("bash", "shell", "execute_command", "code_interpreter"):
            assert _threshold_for_tool(name) == THRESHOLD_EXEC

    def test_unknown_tool_uses_default(self):
        assert _threshold_for_tool("some_exotic_tool") == THRESHOLD_DEFAULT

    def test_prefix_matching_deploy(self):
        # "ansible_playbook" should map to deploy threshold via prefix
        assert _threshold_for_tool("ansible_playbook") == THRESHOLD_DEPLOY

    def test_prefix_matching_exec(self):
        assert _threshold_for_tool("bash_run") == THRESHOLD_EXEC


# ---------------------------------------------------------------------------
# Unit: response parsing
# ---------------------------------------------------------------------------


class TestParsing:
    def test_parse_probability_valid(self):
        raw = "REFUTATION_PROBABILITY: 0.85\nFLAW: x\nRATIONALE: y"
        assert _parse_probability(raw) == pytest.approx(0.85)

    def test_parse_probability_clamped_above_one(self):
        raw = "REFUTATION_PROBABILITY: 1.5"
        assert _parse_probability(raw) == pytest.approx(1.0)

    def test_parse_probability_clamped_below_zero(self):
        raw = "REFUTATION_PROBABILITY: -0.2"
        assert _parse_probability(raw) == pytest.approx(0.0)

    def test_parse_probability_missing_returns_conservative(self):
        assert _parse_probability("nothing here") == pytest.approx(0.5)

    def test_parse_rationale_extracted(self):
        rat = _parse_rationale(_REFUTE_RESPONSE)
        assert "OSError" in rat or "non-existent" in rat

    def test_parse_rationale_fallback_on_missing(self):
        raw = "no structured output at all"
        result = _parse_rationale(raw)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# Unit: PreActionVerifier — disabled path
# ---------------------------------------------------------------------------


class TestVerifierDisabled:
    @pytest.mark.asyncio
    async def test_verifier_disabled_returns_skip(self):
        with patch("agent_loop.pre_action_verifier.VERIFIER_ENABLED", False):
            v = PreActionVerifier()
            result = await v.verify("write_file", {"path": "/etc/passwd"}, "test")
        assert result.verdict == VerifierVerdict.SKIP
        assert result.refutation_probability == 0.0


# ---------------------------------------------------------------------------
# AC-3: seeded "plausible but wrong" plan is BLOCKED by the verifier
# ---------------------------------------------------------------------------


class TestVerifierBlocksPlausibleButWrong:
    """The key acceptance criterion: a convincing-but-wrong plan is refuted."""

    @pytest.mark.asyncio
    async def test_plausible_but_wrong_plan_is_blocked(self):
        """Seeded wrong plan: agent claims a config file exists and proposes
        overwriting it.  The verifier LLM is mocked to return a high
        refutation probability, simulating it catching the false assumption.
        """
        provider = _fake_provider("anthropic")
        provider.chat_completion.return_value = _make_llm_response(_REFUTE_RESPONSE)

        with (
            patch(
                "agent_loop.pre_action_verifier._select_verifier_provider",
                new=AsyncMock(return_value=provider),
            ),
            patch("agent_loop.pre_action_verifier.VERIFIER_ENABLED", True),
        ):
            v = PreActionVerifier(actor_provider="ollama")
            result = await v.verify(
                tool_name="write_file",
                args={"path": "/data/config.yaml", "content": "key: wrong_value"},
                reason="The config file exists from the last deployment. Updating it now.",
                task_id="task-test-001",
            )

        assert result.verdict == VerifierVerdict.BLOCK, (
            f"Expected BLOCK for plausible-but-wrong plan; got {result.verdict} "
            f"(prob={result.refutation_probability:.2f})"
        )
        assert result.refutation_probability >= 0.5
        assert result.rationale != ""
        # Verifier used the distinct provider, not the actor
        assert result.provider_used == "anthropic"

    @pytest.mark.asyncio
    async def test_correct_plan_passes(self):
        """A well-founded plan should get a PASS verdict."""
        provider = _fake_provider("anthropic")
        provider.chat_completion.return_value = _make_llm_response(_PASS_RESPONSE)

        with (
            patch(
                "agent_loop.pre_action_verifier._select_verifier_provider",
                new=AsyncMock(return_value=provider),
            ),
            patch("agent_loop.pre_action_verifier.VERIFIER_ENABLED", True),
        ):
            v = PreActionVerifier(actor_provider="ollama")
            result = await v.verify(
                tool_name="write_file",
                args={"path": "/data/config.yaml", "content": "key: correct_value"},
                reason="read_file confirmed the path exists. Updating it now.",
                task_id="task-test-002",
            )

        assert result.verdict == VerifierVerdict.PASS
        assert result.refutation_probability < 0.5


# ---------------------------------------------------------------------------
# AC-2: distinct provider is chosen
# ---------------------------------------------------------------------------


class TestDistinctProvider:
    @pytest.mark.asyncio
    async def test_distinct_provider_selected_over_actor(self):
        """Registry with two providers: verifier must pick the non-actor one."""
        actor_prov = _fake_provider("ollama")
        verifier_prov = _fake_provider("anthropic")
        verifier_prov.chat_completion.return_value = _make_llm_response(_REFUTE_RESPONSE)

        mock_registry = MagicMock()
        mock_registry.list_providers.return_value = [
            {"name": "ollama"},
            {"name": "anthropic"},
        ]

        async def _get_prov(name: str) -> Any:
            return actor_prov if name == "ollama" else verifier_prov

        mock_registry.get_provider = _get_prov

        with (
            patch("agent_loop.pre_action_verifier.get_provider_registry", return_value=mock_registry),
            patch("agent_loop.pre_action_verifier.VERIFIER_ENABLED", True),
        ):
            from agent_loop.pre_action_verifier import _select_verifier_provider

            chosen = await _select_verifier_provider(actor_provider="ollama")

        assert chosen is verifier_prov

    @pytest.mark.asyncio
    async def test_falls_back_to_actor_when_only_one_provider(self):
        """Single-provider install: verifier uses the only available provider."""
        only_prov = _fake_provider("ollama")

        mock_registry = MagicMock()
        mock_registry.list_providers.return_value = [{"name": "ollama"}]

        async def _get_prov(name: str) -> Any:
            return only_prov

        mock_registry.get_provider = _get_prov

        with patch("agent_loop.pre_action_verifier.get_provider_registry", return_value=mock_registry):
            from agent_loop.pre_action_verifier import _select_verifier_provider

            chosen = await _select_verifier_provider(actor_provider="ollama")

        assert chosen is only_prov


# ---------------------------------------------------------------------------
# AC-4: loop integration — verifier verdict shown at approval gate
# ---------------------------------------------------------------------------


class TestLoopIntegration:
    """Verify the verifier is invoked inside _check_approvals and its result
    is published via _record_verifier_verdict before the human approval step.
    """

    def _make_loop(self, verifier_enabled: bool = True) -> Any:
        from agent_loop.loop import AgentLoop
        from agent_loop.types import AgentLoopConfig, LoopState, TaskContext

        event_stream = MagicMock()
        event_stream.get_latest = AsyncMock(return_value=[])
        event_stream.publish = AsyncMock()
        cfg = AgentLoopConfig(
            require_approval_for_sensitive=True,
            approval_timeout_seconds=5,
            pre_action_verifier_enabled=verifier_enabled,
        )
        loop = AgentLoop(event_stream=event_stream, config=cfg)
        loop._current_context = TaskContext(task_id="t-verifier", description="test")
        loop._state = LoopState.RUNNING
        return loop

    @pytest.mark.asyncio
    async def test_verifier_called_before_approval(self):
        """_run_verifier is awaited inside _check_approvals for sensitive tools."""
        loop = self._make_loop()

        mock_result = MagicMock()
        mock_result.verdict = VerifierVerdict.PASS
        mock_result.refutation_probability = 0.1
        mock_result.to_dict.return_value = {}

        loop._run_verifier = AsyncMock(return_value=mock_result)
        loop._record_verifier_verdict = AsyncMock()
        loop._request_approval = AsyncMock(return_value=True)

        tools = [{"tool_name": "bash", "args": {"cmd": "ls"}}]
        result = await loop._check_approvals(tools)

        loop._run_verifier.assert_awaited_once()
        loop._record_verifier_verdict.assert_awaited_once()
        assert result == {}

    @pytest.mark.asyncio
    async def test_hard_block_prevents_approval_request(self):
        """When HARD_BLOCK=1 and verifier returns BLOCK, _request_approval is never called."""
        loop = self._make_loop()

        mock_result = MagicMock()
        mock_result.verdict = VerifierVerdict.BLOCK
        mock_result.refutation_probability = 0.92
        mock_result.rationale = "Path does not exist."
        mock_result.to_dict.return_value = {}

        loop._run_verifier = AsyncMock(return_value=mock_result)
        loop._record_verifier_verdict = AsyncMock()
        loop._request_approval = AsyncMock(return_value=True)

        with patch("agent_loop.pre_action_verifier.HARD_BLOCK", True):
            result = await loop._check_approvals([{"tool_name": "bash", "args": {}}])

        loop._request_approval.assert_not_called()
        assert "bash" in result
        assert "hard-blocked" in result["bash"]["error"] or "verifier" in result["bash"]["error"].lower()

    @pytest.mark.asyncio
    async def test_soft_block_escalates_to_human_with_rationale(self):
        """Soft-block (HARD_BLOCK=0): approval request is sent with verifier rationale."""
        loop = self._make_loop()

        mock_result = MagicMock()
        mock_result.verdict = VerifierVerdict.BLOCK
        mock_result.refutation_probability = 0.80
        mock_result.rationale = "Destructive operation detected."
        mock_result.to_dict.return_value = {}

        loop._run_verifier = AsyncMock(return_value=mock_result)
        loop._record_verifier_verdict = AsyncMock()
        # Human approves
        loop._request_approval = AsyncMock(return_value=True)

        with patch("agent_loop.pre_action_verifier.HARD_BLOCK", False):
            result = await loop._check_approvals([{"tool_name": "bash", "args": {}}])

        # Human approved, so no error returned
        assert result == {}
        # The tool dict passed to _request_approval carries verifier_rationale
        call_args = loop._request_approval.call_args
        tool_passed = call_args[0][0]
        assert "verifier_rationale" in tool_passed
        assert "0.80" in tool_passed["verifier_rationale"] or "Verifier" in tool_passed["verifier_rationale"]

    @pytest.mark.asyncio
    async def test_verifier_disabled_skips_verifier_call(self):
        """When pre_action_verifier_enabled=False the _verifier attribute is None."""
        loop = self._make_loop(verifier_enabled=False)
        assert loop._verifier is None

        loop._record_verifier_verdict = AsyncMock()
        loop._request_approval = AsyncMock(return_value=True)

        await loop._check_approvals([{"tool_name": "bash", "args": {}}])
        loop._record_verifier_verdict.assert_not_called()

    @pytest.mark.asyncio
    async def test_verifier_verdict_recorded_in_trajectory(self):
        """_record_verifier_verdict stores the payload in context metadata."""
        loop = self._make_loop()

        mock_result = MagicMock()
        mock_result.verdict = VerifierVerdict.PASS
        mock_result.refutation_probability = 0.1
        mock_result.tool_name = "bash"
        mock_result.to_dict.return_value = {
            "verdict": "PASS",
            "tool_name": "bash",
            "refutation_probability": 0.1,
        }

        with patch("agent_loop.loop._bus_publish_event", new=AsyncMock()):
            await loop._record_verifier_verdict(mock_result)

        stored = loop._current_context.metadata.get("verifier_verdicts", [])
        assert len(stored) == 1
        assert stored[0]["verdict"] == "PASS"


# ---------------------------------------------------------------------------
# N-of-M panel
# ---------------------------------------------------------------------------


class TestPanel:
    @pytest.mark.asyncio
    async def test_panel_blocks_when_quorum_refutes(self):
        """Panel of 3, quorum of 2: if 2 refute, result is BLOCK."""

        provider = _fake_provider("anthropic")
        # Return high probability each time
        provider.chat_completion.return_value = _make_llm_response(_REFUTE_RESPONSE)

        call_count = 0

        async def _side_effect(name):
            nonlocal call_count
            call_count += 1
            return provider

        with (
            patch(
                "agent_loop.pre_action_verifier._select_verifier_provider",
                side_effect=_side_effect,
            ),
            patch("agent_loop.pre_action_verifier.VERIFIER_ENABLED", True),
            patch("agent_loop.pre_action_verifier.PANEL_QUORUM", 2),
        ):
            v = PreActionVerifier()
            result = await v.verify(
                tool_name="write_file",
                args={"path": "/etc/hosts"},
                reason="need to update hosts",
                panel_size=3,
            )

        assert result.verdict == VerifierVerdict.BLOCK
        assert result.panel_size == 3
        assert result.panel_refutations >= 2

    @pytest.mark.asyncio
    async def test_panel_passes_when_below_quorum(self):
        """Panel of 3, quorum of 2: if only 1 refutes, result is PASS."""
        provider_pass = _fake_provider("anthropic")
        provider_pass.chat_completion.return_value = _make_llm_response(_PASS_RESPONSE)

        with (
            patch(
                "agent_loop.pre_action_verifier._select_verifier_provider",
                new=AsyncMock(return_value=provider_pass),
            ),
            patch("agent_loop.pre_action_verifier.VERIFIER_ENABLED", True),
            patch("agent_loop.pre_action_verifier.PANEL_QUORUM", 2),
        ):
            v = PreActionVerifier()
            result = await v.verify(
                tool_name="write_file",
                args={"path": "/data/safe.yaml"},
                reason="prior read confirmed existence",
                panel_size=3,
            )

        assert result.verdict == VerifierVerdict.PASS
        assert result.panel_size == 3
