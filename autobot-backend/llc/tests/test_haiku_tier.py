# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for Haiku assistant tier (GH#8486).

Covers:
  1. agent_hires API — model validation, AGENTS.md stub generation
  2. costs/by-agent-model — endpoint response schema
  3. health probe — agents_missing_instructions metric
"""

from __future__ import annotations

from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# GH#9995 / GH#10140: ``llc.api.agent_hires`` and ``llc.api.budget`` import
# cleanly in the test environment, so import them normally. The previous
# implementation installed module-level ``sys.modules`` MagicMock stubs for
# llc.services / autobot_shared / user_management and loaded these modules from
# file to bypass package __init__ chains. Those global stubs LEAKED into every
# test module collected after this one — turning real packages into MagicMocks
# (e.g. ``llc.services`` "is not a package") and failing ~30 llc.api route tests
# in suite order while masking genuine regressions. The stubs also broke this
# file's own tests (the real ``llc.services.model_tiers`` could not import). A
# normal import fixes both.


def _get_agent_hires_mod() -> ModuleType:
    import llc.api.agent_hires as mod

    return mod


def _get_budget_mod() -> ModuleType:
    import llc.api.budget as mod

    return mod


# ===========================================================================
# 1. agent_hires API
# ===========================================================================


class TestAgentHireModelValidation:
    """Tests for the model-override validation logic in agent_hires.py."""

    def test_valid_haiku_model_accepted(self) -> None:
        mod = _get_agent_hires_mod()
        assert mod.HAIKU_MODEL in mod._VALID_MODELS

    def test_valid_sonnet_model_accepted(self) -> None:
        mod = _get_agent_hires_mod()
        assert mod.SONNET_MODEL in mod._VALID_MODELS

    def test_invalid_model_not_in_valid_set(self) -> None:
        mod = _get_agent_hires_mod()
        assert "gpt-4o" not in mod._VALID_MODELS
        assert "claude-opus-4-5" not in mod._VALID_MODELS

    def test_haiku_and_sonnet_are_different_models(self) -> None:
        mod = _get_agent_hires_mod()
        assert mod.HAIKU_MODEL != mod.SONNET_MODEL


class TestAgentsMdGeneration:
    """Tests for AGENTS.md template generation logic."""

    def test_sonnet_without_assistant_gets_stub(self) -> None:
        mod = _get_agent_hires_mod()
        result = mod._SONNET_AGENTS_MD_NO_ASSISTANT.format(
            agent_name="Sonnet",
            role_description="test role",
        )
        assert "No Haiku assistant has been paired yet" in result

    def test_sonnet_with_assistant_gets_delegation_section(self) -> None:
        mod = _get_agent_hires_mod()
        result = mod._SONNET_AGENTS_MD_TEMPLATE.format(
            agent_name="Sonnet",
            role_description="Does hard stuff",
            assistant_name="HaikuBot",
            assistant_id="haiku-uuid-123",
        )
        assert "haiku-uuid-123" in result
        assert "HaikuBot" in result
        assert "Delegate self-contained subtasks" in result

    def test_haiku_template_contains_scope_restriction(self) -> None:
        mod = _get_agent_hires_mod()
        result = mod._HAIKU_AGENTS_MD_TEMPLATE.format(
            agent_name="HaikuBot",
            reports_to_name="SonnetPrime",
        )
        assert "Do NOT make architectural decisions" in result
        assert "SonnetPrime" in result

    def test_haiku_template_forbids_further_delegation(self) -> None:
        mod = _get_agent_hires_mod()
        result = mod._HAIKU_AGENTS_MD_TEMPLATE.format(
            agent_name="HaikuBot",
            reports_to_name="Parent",
        )
        assert "Delegate nothing further" in result

    def test_agent_hire_request_model_field(self) -> None:
        mod = _get_agent_hires_mod()
        req = mod.AgentHireRequest(agent_name="Bot", model=mod.HAIKU_MODEL)
        assert req.model == mod.HAIKU_MODEL

    def test_agent_hire_request_defaults_no_model(self) -> None:
        mod = _get_agent_hires_mod()
        req = mod.AgentHireRequest(agent_name="SonnetBot")
        assert req.model is None  # resolved to SONNET_MODEL in the handler


# ===========================================================================
# 2. costs/by-agent-model — response schema
# ===========================================================================


class TestCostsByAgentModel:
    """Tests for AgentModelCostRow schema in budget.py."""

    def test_agent_model_cost_row_schema(self) -> None:
        mod = _get_budget_mod()
        row = mod.AgentModelCostRow(
            agent_id="a1",
            agent_name="Sonnet Prime",
            model="claude-sonnet-4-6",
            input_tokens=1000,
            cached_input_tokens=800,
            output_tokens=200,
            cache_hit_rate=0.8,
            cost_usd="0.00",
        )
        assert row.cache_hit_rate == 0.8
        assert row.cached_input_tokens == 800

    def test_cache_hit_rate_zero_when_no_tokens(self) -> None:
        mod = _get_budget_mod()
        row = mod.AgentModelCostRow(
            agent_id="a2",
            agent_name="Empty",
            model="claude-haiku-4-5-20251001",
            input_tokens=0,
            cached_input_tokens=0,
            output_tokens=0,
            cache_hit_rate=0.0,
            cost_usd="0.00",
        )
        assert row.cache_hit_rate == 0.0

    def test_costs_by_model_router_exported(self) -> None:
        """costs_by_model_router must be exported from budget.py for __init__.py."""
        mod = _get_budget_mod()
        assert hasattr(mod, "costs_by_model_router")


# ===========================================================================
# 3. health probe — agents_missing_instructions
# ===========================================================================


class TestAgentsMissingInstructions:
    """Tests for _count_agents_missing_instructions and _compute_status."""

    @pytest.mark.asyncio
    async def test_returns_zero_on_db_error(self) -> None:
        """Probe should return 0 (not raise) when DB is unavailable."""
        with patch("llc.health.probe.get_async_session_factory") as mock_factory:
            mock_factory.side_effect = RuntimeError("DB unavailable")
            from llc.health.probe import _count_agents_missing_instructions

            result = await _count_agents_missing_instructions()
        assert result == 0

    @pytest.mark.asyncio
    async def test_counts_agents_with_null_path(self) -> None:
        """Agents with NULL instructions_file_path should be counted as missing."""
        mock_row = ("a1", None)

        async_ctx = AsyncMock()
        async_ctx.__aenter__ = AsyncMock(return_value=async_ctx)
        async_ctx.__aexit__ = AsyncMock(return_value=False)
        async_ctx.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[mock_row])))
        mock_factory = MagicMock(return_value=async_ctx)

        with patch("llc.health.probe.get_async_session_factory", return_value=mock_factory):
            from llc.health.probe import _count_agents_missing_instructions

            result = await _count_agents_missing_instructions()
        assert result == 1

    @pytest.mark.asyncio
    async def test_counts_agents_with_nonexistent_file(self, tmp_path) -> None:
        """Agents whose file path does not exist should be counted."""
        nonexistent = str(tmp_path / "missing" / "AGENTS.md")
        mock_row = ("a2", nonexistent)

        async_ctx = AsyncMock()
        async_ctx.__aenter__ = AsyncMock(return_value=async_ctx)
        async_ctx.__aexit__ = AsyncMock(return_value=False)
        async_ctx.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[mock_row])))
        mock_factory = MagicMock(return_value=async_ctx)

        with patch("llc.health.probe.get_async_session_factory", return_value=mock_factory):
            from llc.health.probe import _count_agents_missing_instructions

            result = await _count_agents_missing_instructions()
        assert result == 1

    @pytest.mark.asyncio
    async def test_does_not_count_agents_with_existing_file(self, tmp_path) -> None:
        """Agents whose AGENTS.md exists on disk should NOT be counted."""
        real_file = tmp_path / "AGENTS.md"
        real_file.write_text("# Test Agent\n")
        mock_row = ("a3", str(real_file))

        async_ctx = AsyncMock()
        async_ctx.__aenter__ = AsyncMock(return_value=async_ctx)
        async_ctx.__aexit__ = AsyncMock(return_value=False)
        async_ctx.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[mock_row])))
        mock_factory = MagicMock(return_value=async_ctx)

        with patch("llc.health.probe.get_async_session_factory", return_value=mock_factory):
            from llc.health.probe import _count_agents_missing_instructions

            result = await _count_agents_missing_instructions()
        assert result == 0

    def test_probe_status_degraded_when_agents_missing_instructions(self) -> None:
        """Probe status should be degraded when agents_missing_instructions > 0."""
        from llc.health.probe import _compute_status

        metrics = {
            "heartbeat_scheduler_running": True,
            "liveness_monitor_running": True,
            "session_checkpointer_running": True,
            "scheduler_last_tick_age_seconds": 5.0,
            "agents_overdue_degraded": 0,
            "agents_overdue_critical": 0,
            "budget_warning_companies": 0,
            "budget_exhausted_companies": 0,
            "pending_approvals_critical": 0,
            "agents_missing_instructions": 2,
        }
        assert _compute_status(metrics) == "degraded"

    def test_probe_status_ok_when_all_good(self) -> None:
        from llc.health.probe import _compute_status

        metrics = {
            "heartbeat_scheduler_running": True,
            "liveness_monitor_running": True,
            "session_checkpointer_running": True,
            "scheduler_last_tick_age_seconds": 5.0,
            "agents_overdue_degraded": 0,
            "agents_overdue_critical": 0,
            "budget_warning_companies": 0,
            "budget_exhausted_companies": 0,
            "pending_approvals_critical": 0,
            "agents_missing_instructions": 0,
        }
        assert _compute_status(metrics) == "ok"

    def test_probe_status_backward_compat_no_key(self) -> None:
        """Probe should handle metrics dict without agents_missing_instructions key."""
        from llc.health.probe import _compute_status

        metrics = {
            "heartbeat_scheduler_running": True,
            "liveness_monitor_running": True,
            "session_checkpointer_running": True,
            "scheduler_last_tick_age_seconds": 5.0,
            "agents_overdue_degraded": 0,
            "agents_overdue_critical": 0,
            "budget_warning_companies": 0,
            "budget_exhausted_companies": 0,
            "pending_approvals_critical": 0,
            # agents_missing_instructions deliberately absent
        }
        assert _compute_status(metrics) == "ok"
