# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Delivering an approval question through the Gateway egress seam (#14068).

``services/remote_approval`` correlates a reply with a request and
``services/remote_approval_routing`` decides *where* the question is asked.
Neither may know how a platform sends — that is the Gateway's job, and #14067
put the egress governance there. This module is the one adapter between the
two, and the only place either of them meets ``services.gateway``.

Safety direction, stated once because every caller inherits it: this module
**never decides whether an approval is required and never answers one**. It
delivers a question and returns a bool saying whether it went out. A False —
Redis down, no route configured, the channel refused, the Gateway blocked the
send — leaves the approval exactly where it was: pending, awaiting the in-app
decision, denied on timeout. There is no path through here that approves.
"""

from __future__ import annotations

from autobot_shared.logging_manager import get_logger
from services.remote_approval_routing import RemoteApprovalRouting, deliver_approval

logger = get_logger(__name__)


async def gateway_sender(*, platform: str, channel_id: str, body: str) -> bool:
    """An :class:`~services.remote_approval_routing.ApprovalSender` on the Gateway.

    ``channel_id`` is the Gateway session id: the Gateway itself identifies a
    channel that way (``gateway.py`` passes ``channel_id=session.session_id``
    into both governors), so routing a session's approvals to a channel means
    naming the Gateway session that reaches the human.

    Refuses when the session is unknown or sits on a different platform than
    the route recorded — a route that has drifted onto another channel must not
    deliver the operator's approval question to whoever is on the new one.
    """
    from services.gateway.gateway import get_gateway
    from services.gateway.types import ChannelMessage, MessageType

    try:
        gateway = await get_gateway()
        session = await gateway.session_manager.get_session(channel_id)
        if session is None:
            logger.warning("Approval delivery: no Gateway session for the configured route")
            return False
        if session.channel.value != platform:
            logger.warning(
                "Approval delivery: route names platform %s but its session is on %s — refusing",
                platform,
                session.channel.value,
            )
            return False
        return await gateway.send_message(
            ChannelMessage(
                session_id=channel_id,
                channel=session.channel,
                message_type=MessageType.AGENT_TEXT,
                content=body,
                metadata={"kind": "approval_request"},
            )
        )
    except Exception as exc:  # noqa: BLE001 - a channel failure must not kill the turn
        logger.error("Approval delivery through the Gateway failed: %s", exc)
        return False


async def mirror_approval_request(
    *,
    session_id: str,
    approval_id: str,
    body: str,
    routing: RemoteApprovalRouting | None = None,
) -> bool:
    """Ask *session_id*'s human remotely as well, if they are routed remotely.

    True only when the question was delivered **and** its correlation recorded.
    False is the ordinary case (the session is not routed remotely) and is also
    every failure case; both mean the approval is answered in-app as before.
    Never raises: a delivery problem may not change a safety decision.
    """
    try:
        return await deliver_approval(
            session_id=session_id,
            approval_id=approval_id,
            body=body,
            send=gateway_sender,
            routing=routing,
        )
    except Exception as exc:  # noqa: BLE001 - see the module docstring
        logger.error("Could not mirror approval %s to the configured channel: %s", approval_id, exc)
        return False


__all__ = ["gateway_sender", "mirror_approval_request"]
