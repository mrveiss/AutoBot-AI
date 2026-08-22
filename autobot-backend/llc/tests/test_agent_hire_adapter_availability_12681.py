# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss

"""#12681: a registered adapter is not necessarily a runnable one.

Hiring already rejected an *unregistered* `adapter_type`, and the comment on that
check names the failure it prevents: an agent whose every heartbeat is skipped,
looking degraded forever. A registered type whose CLI is missing produces exactly
that symptom one level down — the type is in the registry, the binary is not on
the service PATH, and the hire succeeds anyway.

The availability probe already existed and is already what `GET /adapters`
reports; the hire path simply never asked. These drive `hire_agent` itself rather
than the helper, because the defect was the missing call, not a wrong answer.
"""

from __future__ import annotations

import uuid
from types import ModuleType
from unittest.mock import AsyncMock, patch

import pytest

from user_management.services import TenantContext


def _mod() -> ModuleType:
    import llc.api.agent_hires as mod

    return mod


def _ctx() -> TenantContext:
    return TenantContext(org_id=None, user_id=uuid.uuid4(), is_platform_admin=True)


class _CliAdapter:
    """Stands in for a subprocess adapter: has the probe, reports unavailable."""

    def __init__(self, available: bool = False, raises: bool = False) -> None:
        self._available = available
        self._raises = raises

    def is_cli_available(self) -> bool:
        if self._raises:
            raise OSError("probe blew up")
        return self._available

    def cli_not_found_message(self) -> str:
        return "'claude' CLI not found on PATH or common install locations"


class _InProcessAdapter:
    """Stands in for an adapter that shells out to nothing — no probe at all."""


class TestAdapterAvailabilityReason:
    def test_missing_cli_reports_the_actionable_message(self):
        mod = _mod()
        with patch.object(mod, "get_adapter", return_value=_CliAdapter(available=False)):
            reason = mod._adapter_unavailable_reason("claude_code")
        assert reason is not None
        assert "not found on PATH" in reason

    def test_present_cli_reports_nothing(self):
        mod = _mod()
        with patch.object(mod, "get_adapter", return_value=_CliAdapter(available=True)):
            assert mod._adapter_unavailable_reason("claude_code") is None

    def test_an_adapter_without_the_probe_is_reported_unimplemented(self):
        """Absence of the probe means "not implemented", not "nothing to check".

        `GET /adapters` computes `available = implemented` from the very same
        `hasattr`, so treating a probe-less adapter as runnable would have the
        hire succeed for a type the UI greys out.
        """
        mod = _mod()
        with patch.object(mod, "get_adapter", return_value=_InProcessAdapter()):
            reason = mod._adapter_unavailable_reason("codex_subscription")
        assert reason is not None
        assert "not implemented" in reason

    def test_the_real_codex_stub_is_refused(self):
        """Against the actual registered adapter, not a stand-in.

        The stand-in is what let this slip: `codex_subscription` is registered,
        has no `is_cli_available`, and its `invoke` raises NotImplementedError.
        """
        from llc.adapters.codex_subscription_adapter import CodexSubscriptionAdapter

        mod = _mod()
        with patch.object(mod, "get_adapter", return_value=CodexSubscriptionAdapter()):
            reason = mod._adapter_unavailable_reason("codex_subscription")
        assert reason is not None, "a registered but unimplemented adapter must be refused"

    def test_a_crashing_probe_fails_closed(self):
        """`GET /adapters` reports available=False when the probe raises.

        Failing open here would let a hire succeed for an adapter the UI is
        simultaneously showing as unavailable — two surfaces disagreeing about
        the same question.
        """
        mod = _mod()
        with patch.object(mod, "get_adapter", return_value=_CliAdapter(raises=True)):
            reason = mod._adapter_unavailable_reason("claude_code")
        assert reason is not None
        assert "could not be determined" in reason


class TestHireRejectsAnUnrunnableAdapter:
    """Driving the route: the bug was that hire_agent never consulted the probe."""

    @pytest.mark.asyncio
    async def test_hire_is_refused_when_the_cli_is_absent(self):
        mod = _mod()
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        body = mod.AgentHireRequest(agent_name="CEO", org_role="manager", title="Chief Executive")

        with (
            patch.object(mod, "registered_adapter_types", return_value=["claude_code"]),
            patch.object(mod, "get_adapter", return_value=_CliAdapter(available=False)),
            patch.object(mod.BudgetService, "provision_budget", new=AsyncMock()),
            pytest.raises(mod.HTTPException) as caught,
        ):
            await mod.hire_agent(company_id=uuid.uuid4(), body=body, session=session, ctx=_ctx())

        assert caught.value.status_code == 422
        assert "cannot run on this deployment" in str(caught.value.detail)
        session.execute.assert_not_awaited()
        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_hire_proceeds_when_the_cli_is_present(self):
        """The control: without it, a gate that rejected everything would pass above."""
        mod = _mod()
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        body = mod.AgentHireRequest(agent_name="CEO", org_role="manager", title="Chief Executive")

        with (
            patch.object(mod, "registered_adapter_types", return_value=["claude_code"]),
            patch.object(mod, "get_adapter", return_value=_CliAdapter(available=True)),
            patch.object(mod.BudgetService, "provision_budget", new=AsyncMock()),
        ):
            await mod.hire_agent(company_id=uuid.uuid4(), body=body, session=session, ctx=_ctx())

        session.execute.assert_awaited()
        session.commit.assert_awaited()
