# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Outbound approval + audit at the shared Gateway egress seam (#14067).

`Gateway.send_message` performed three checks — session exists, adapter exists,
size limit — and then handed the message to the adapter. Sending a message to a
real person on any of the ten channels is the one agent action that cannot be
undone, and it was the one action with no gate and no record.

The seam lives in `Gateway.send_message`, not in the adapters, so a newly added
adapter inherits it without per-adapter work — the same structural argument
#14028 makes for the inbound side.
"""

from unittest.mock import AsyncMock, patch

import pytest

from services.gateway.egress_governor import EgressGovernor, EgressVerdict


@pytest.fixture
def governor():
    return EgressGovernor()


class TestDefaultPostureAllowsButAlwaysRecords:
    """Audit-only by default: a live sink, not a dormant switch."""

    @pytest.mark.asyncio
    async def test_a_send_is_allowed_when_approval_is_not_required(self, governor):
        verdict = await governor.evaluate(platform="slack", channel_id="c1", message_id="m1", require_approval=False)
        assert verdict.allowed is True

    @pytest.mark.asyncio
    async def test_an_allowed_send_is_still_recorded(self, governor):
        with patch("services.gateway.egress_governor.get_audit_logger") as mock_get:
            audit = AsyncMock()
            mock_get.return_value = audit
            await governor.evaluate(platform="slack", channel_id="c1", message_id="m1", require_approval=False)
        audit.log.assert_awaited_once()
        assert audit.log.await_args.kwargs["operation"] == "gateway.egress"
        assert audit.log.await_args.kwargs["result"] == "success"

    @pytest.mark.asyncio
    async def test_the_record_names_the_platform_and_channel(self, governor):
        with patch("services.gateway.egress_governor.get_audit_logger") as mock_get:
            audit = AsyncMock()
            mock_get.return_value = audit
            await governor.evaluate(platform="discord", channel_id="c9", message_id="m1", require_approval=False)
        resource = audit.log.await_args.kwargs["resource"]
        assert "discord" in resource and "c9" in resource

    @pytest.mark.asyncio
    async def test_a_broken_audit_sink_does_not_block_the_send(self, governor):
        """Recording is not the gate. Losing the record must not lose the message."""
        with patch("services.gateway.egress_governor.get_audit_logger", side_effect=RuntimeError("redis down")):
            verdict = await governor.evaluate(
                platform="slack", channel_id="c1", message_id="m1", require_approval=False
            )
        assert verdict.allowed is True


class TestApprovalRequiredFailsClosed:
    @pytest.mark.asyncio
    async def test_no_registered_approver_denies_rather_than_allows(self, governor):
        """The direction that matters. An unreachable approver is not consent."""
        verdict = await governor.evaluate(platform="slack", channel_id="c1", message_id="m1", require_approval=True)
        assert verdict.allowed is False
        assert "approver" in verdict.reason.lower()

    @pytest.mark.asyncio
    async def test_an_approver_that_denies_blocks_the_send(self, governor):
        governor.register_approver("slack", AsyncMock(return_value=False))
        verdict = await governor.evaluate(platform="slack", channel_id="c1", message_id="m1", require_approval=True)
        assert verdict.allowed is False

    @pytest.mark.asyncio
    async def test_an_approver_that_allows_permits_the_send(self, governor):
        governor.register_approver("slack", AsyncMock(return_value=True))
        verdict = await governor.evaluate(platform="slack", channel_id="c1", message_id="m1", require_approval=True)
        assert verdict.allowed is True

    @pytest.mark.asyncio
    async def test_an_approver_that_raises_denies_rather_than_allows(self, governor):
        governor.register_approver("slack", AsyncMock(side_effect=RuntimeError("gone")))
        verdict = await governor.evaluate(platform="slack", channel_id="c1", message_id="m1", require_approval=True)
        assert verdict.allowed is False

    @pytest.mark.asyncio
    async def test_an_approver_registered_for_another_platform_does_not_apply(self, governor):
        governor.register_approver("discord", AsyncMock(return_value=True))
        verdict = await governor.evaluate(platform="slack", channel_id="c1", message_id="m1", require_approval=True)
        assert verdict.allowed is False

    @pytest.mark.asyncio
    async def test_a_denial_is_recorded_as_a_denial(self, governor):
        governor.register_approver("slack", AsyncMock(return_value=False))
        with patch("services.gateway.egress_governor.get_audit_logger") as mock_get:
            audit = AsyncMock()
            mock_get.return_value = audit
            await governor.evaluate(platform="slack", channel_id="c1", message_id="m1", require_approval=True)
        assert audit.log.await_args.kwargs["result"] == "denied"

    @pytest.mark.asyncio
    async def test_the_verdict_names_the_rule_that_decided(self, governor):
        """`reason` and `rule` make the audit trail a by-product of the decision."""
        verdict = await governor.evaluate(platform="slack", channel_id="c1", message_id="m1", require_approval=True)
        assert verdict.rule


class TestVerdictShape:
    def test_a_verdict_is_immutable(self):
        verdict = EgressVerdict(allowed=True)
        with pytest.raises(Exception):
            verdict.allowed = False
