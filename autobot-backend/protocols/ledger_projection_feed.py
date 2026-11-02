#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Publish the user backend's live agent state for the SLM ledger (#18632).

Turns the three process-local registries into ledger rows and hands them to
`autobot_shared.coordination.ledger_projection.publish`. The row builders are
shared with the Company OS ledger routes (`api/agent_ledger.py`), so a row means
the same thing in a company's view and in the install-wide one; the only
difference is `tenant_id`, which the install-wide rows carry and the company
view leaves out (it is the caller's own).
"""

from __future__ import annotations

from typing import Any

from autobot_shared.coordination.ledger_projection import publish
from autobot_shared.coordination.ledger_schemas import IdleSubscriberRow, PeerMessageRow, PresenceRow, PresenceTaskRow
from protocols.agent_kind import AgentKind
from protocols.agent_presence import UNKNOWN_TENANT, AgentPresenceRegistry, PresenceEntry
from protocols.idle_notice import IdleSubscription, active_subscriptions
from protocols.peer_inbox import PeerInboxDirectory, PeerMessageEntry


def presence_row(e: PresenceEntry) -> PresenceRow:
    return PresenceRow(
        kind=e.kind.value,
        tenant_id=e.tenant_id,
        name=e.name,
        busy=e.busy,
        detail=e.detail,
        current_task=PresenceTaskRow(id=e.task.id, title=e.task.title) if e.task else None,
        last_seen=e.last_seen,
    )


def peer_message_row(
    kind: AgentKind, name: str, queued: list[PeerMessageEntry], tenant_id: str | None = None
) -> PeerMessageRow:
    """Counts and sender names for one recipient. The content is never read here."""
    return PeerMessageRow(
        recipient_kind=kind.value,
        recipient_name=name,
        pending=len(queued),
        senders=sorted({m.sender.name for m in queued}),
        oldest_at=min(m.timestamp for m in queued),
        tenant_id=tenant_id,
    )


def idle_subscriber_row(s: IdleSubscription, *, with_tenant: bool = False) -> IdleSubscriberRow:
    return IdleSubscriberRow(
        subscriber=s.subscriber,
        target_kind=s.kind.value,
        target_name=s.name,
        since=s.since,
        expires_at=s.expires_at,
        tenant_id=s.tenant_id if with_tenant else None,
    )


async def publish_live_state(client: Any, registry: AgentPresenceRegistry, directory: PeerInboxDirectory) -> None:
    """One snapshot of every tenant's live state, for the SLM admin ledger only."""
    await publish(
        client,
        presence=[presence_row(e) for e in registry.snapshot_for_projection()],
        peer_messages=[
            peer_message_row(kind, name, queued, tenant)
            for kind, tenant, name, queued in directory.pending_for_projection()
        ],
        idle_subscribers=[
            idle_subscriber_row(s, with_tenant=True) for s in active_subscriptions() if s.tenant_id != UNKNOWN_TENANT
        ],
    )
