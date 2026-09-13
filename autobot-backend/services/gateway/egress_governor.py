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

Audience split (#14539)
------------------------
``EgressVerdict.reason`` is for the **audit record**: an operator debugging a
denial needs the real cause, including whatever an approver's exception said.
``EgressVerdict.safe_reason`` is for **callers** — anything that might end up
in an API response. It defaults to ``reason`` for every branch whose text is
already a fixed string or built only from caller-supplied arguments (platform,
rule name). The one branch that is not — an approver raising — sets it
explicitly to a fixed message, because the exception text can carry whatever
the approver touched: a connection string, a hostname, a credential path.
Never widen a caller-facing payload back to ``reason``.

Channel-identity rule (#14540)
-------------------------------
``channel_id`` becomes part of the audit ``resource`` field and of any denial
log line a caller writes. Two existing precedents in the calling modules
answer "how much of it" from what the raw value IS, not which platform sends
it:

* A value that is directly usable **outside** this system on its own — a
  dialable phone number, a URL whose path embeds a bearer token, an email
  address — is reduced before it reaches :meth:`EgressGovernor.evaluate`
  (``whatsapp_integration._mask_phone``,
  ``notification_service._send_webhook``'s ``urlparse(url).hostname``,
  ``notification_service._mask_email``,
  ``integration_communication.send_webhook_message``'s
  ``urlparse(webhook_url).hostname`` for Teams). Recording it whole would
  hand PII or a credential to anyone who can read the audit trail or the
  logs. #14573: an *absent* identifier is the same failure in miniature — a
  caller must never pass ``""`` as a stand-in for "no reduction needed"; if a
  call site genuinely has no channel identifier available, that is a
  documented decision at the call site, not a silent default.
* A value that is an **opaque identifier scoped to this system's own
  platform credential** — a Telegram ``chat_id``, a Slack/Discord
  ``channel_id`` — is recorded as-is. It resolves to a person only through
  the bot token that already gates access to the channel, so masking it buys
  no confidentiality and only makes the record useless for locating which
  conversation was blocked. Telegram's ``chat_id`` and Slack/Discord's
  ``channel_id`` are this case, deliberately unmasked — pinned by
  ``TestChannelIdentityRule`` in ``services/gateway/live_egress_seams_test.py``.

  Caveat: Telegram is the weaker instance of this case. A Slack/Discord
  ``channel_id`` is workspace-scoped — near-useless outside that workspace's
  own token. For a 1:1 chat, a Telegram ``chat_id`` *is* the user's global
  Telegram account ID: stable, and resolvable by any bot or client that has
  contact/API access, not only this one. It is still recorded unmasked
  because an audit trail that cannot identify the blocked conversation has a
  real cost, and #14540 asked for a documented, tested choice rather than a
  particular answer — but this is the one identifier here that is closer to
  a phone number than to an opaque workspace handle, and a future review
  should not assume the two platforms are equivalent just because this rule
  groups them the same way.
"""

from __future__ import annotations

import os
from typing import Awaitable, Callable, Dict

from autobot_shared.env_utils import truthy
from autobot_shared.logging_manager import get_logger
from services.audit_logger import get_audit_logger
from services.gateway.types import GovernanceVerdict

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


# #14905: EgressVerdict was written by copying IngestVerdict's shape, then
# grew rule/safe_reason that ingest never got — the fork that made #14905
# collapse both onto services.gateway.types.GovernanceVerdict. Kept as a name
# so callers and tests importing EgressVerdict from this module do not break.
EgressVerdict = GovernanceVerdict


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
            # #14539: `exc` may embed whatever the approver touched — a connection
            # string, a hostname, a credential path. `reason` keeps it for the
            # audit record; `safe_reason` is the fixed text a caller may return.
            return EgressVerdict(
                allowed=False,
                reason=f"approver failed: {exc}",
                rule="fail-closed",
                safe_reason="approver failed",
            )

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
