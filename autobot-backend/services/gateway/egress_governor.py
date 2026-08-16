# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Outbound approval + audit for Gateway egress (#14067).

`Gateway.send_message` checked that a session existed, that an adapter existed,
and that the message fit the size limit — then handed it to the adapter. Nothing
in the package referenced approval at all. Sending a message to a real person on
Slack, Discord, Telegram, WhatsApp, Matrix, Signal, Teams or iMessage is the one
class of agent action that cannot be undone, and it was the one class with no
gate and no record.

This mirrors :mod:`services.gateway.ingest_governor` deliberately: one shared
stage at the Gateway seam rather than per-adapter checks, so a newly added
adapter inherits the governance without adapter-side work. Ingest governs what
reaches an agent; egress governs what leaves the machine.

Posture
-------
Default is **audit-only**: every governed send is recorded, none is blocked. That
keeps the seam live — the record is a real sink, not a dormant switch waiting for
a caller — while the delivery path that makes a synchronous human gate usable is
built (#14068). With ``require_approval`` on, the stage fails **closed**: no
registered approver, an approver that denies, and an approver that raises all
deny. An unreachable approver is not consent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict

from autobot_shared.env_utils import truthy
from autobot_shared.logging_manager import get_logger
from services.audit_logger import get_audit_logger

logger = get_logger(__name__)

#: Operation name every egress decision is recorded under.
EGRESS_AUDIT_OPERATION = "gateway.egress"


def _resolve_require_approval() -> bool:
    """Whether outbound sends need approval, from the environment."""
    return truthy(os.getenv("AUTOBOT_GATEWAY_REQUIRE_OUTBOUND_APPROVAL", ""))


#: Read once at import, like the ingest governor's limits. Callers may still
#: pass ``require_approval`` explicitly; this is only the default.
EGRESS_REQUIRE_APPROVAL = _resolve_require_approval()

#: An approver decides one outbound send. Returning False denies it.
Approver = Callable[..., Awaitable[bool]]


@dataclass(frozen=True)
class EgressVerdict:
    """Result of running the egress governance stage on one outbound message.

    ``reason`` and ``rule`` are carried on the verdict rather than logged
    separately, so the audit trail is a by-product of the decision instead of a
    second thing a caller has to remember to do.
    """

    allowed: bool
    reason: str = ""
    rule: str = ""


class EgressGovernor:
    """Approval gate + audit record for every governed Gateway send."""

    def __init__(self) -> None:
        self._approvers: Dict[str, Approver] = {}

    def register_approver(self, platform: str, approver: Approver) -> None:
        """Register the approver consulted for *platform*'s outbound sends."""
        self._approvers[platform] = approver

    async def _decide(self, platform: str, channel_id: str, message_id: str, require_approval: bool) -> EgressVerdict:
        """The decision, before it is recorded."""
        if not require_approval:
            return EgressVerdict(allowed=True, reason="approval not required", rule="audit-only")

        approver = self._approvers.get(platform)
        if approver is None:
            return EgressVerdict(
                allowed=False,
                reason=f"no approver registered for platform '{platform}'",
                rule="fail-closed",
            )

        try:
            approved = await approver(platform=platform, channel_id=channel_id, message_id=message_id)
        except Exception as exc:  # noqa: BLE001 - an unreachable approver is not consent
            logger.warning("Egress approver for %s failed, denying: %s", platform, exc)
            return EgressVerdict(allowed=False, reason=f"approver failed: {exc}", rule="fail-closed")

        if approved:
            return EgressVerdict(allowed=True, reason="approved", rule="approver")
        return EgressVerdict(allowed=False, reason="denied by approver", rule="approver")

    async def _record(self, verdict: EgressVerdict, platform: str, channel_id: str, message_id: str) -> None:
        """Record the decision. A broken sink must never block a send."""
        try:
            audit = await get_audit_logger()
            await audit.log(
                operation=EGRESS_AUDIT_OPERATION,
                result="success" if verdict.allowed else "denied",
                resource=f"{platform}:{channel_id}",
                details={
                    "message_id": message_id,
                    "rule": verdict.rule,
                    "reason": verdict.reason,
                },
            )
        except Exception as exc:  # noqa: BLE001 - losing the record must not lose the message
            logger.warning("Egress audit record failed for %s:%s — %s", platform, channel_id, exc)

    async def evaluate(
        self,
        *,
        platform: str,
        channel_id: str,
        message_id: str,
        require_approval: bool | None = None,
    ) -> EgressVerdict:
        """Run the egress governance stage on one outbound message."""
        if require_approval is None:
            require_approval = EGRESS_REQUIRE_APPROVAL
        verdict = await self._decide(platform, channel_id, message_id, require_approval)
        await self._record(verdict, platform, channel_id, message_id)
        return verdict


# Shared singleton, matching ingest_governor: holds only the per-platform
# approver registry, never per-message state.
egress_governor = EgressGovernor()
