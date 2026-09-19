#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Subscribe once to be told when a peer next goes idle (#16949).

Absent before this: presence (#16947) can be *polled* for busy/idle, but
nothing pushed a notice on the transition -- an agent waiting on a peer had
to poll, which is what this layer exists to avoid.

Built on the existing event transport (`events/bus.py`'s `EventBus`), not a
new one: `AgentPresenceRegistry.report()` publishes `EVT_AGENT_IDLE`
exactly on a busy=True -> busy=False transition (never on a first report
that starts idle -- that is "already free", handled below by checking
current state before waiting, not a transition to notify about).
`wait_for_idle()` is the one-shot subscriber: it resolves immediately if
the target is already idle, otherwise waits for exactly one matching event
or the bounded timeout, whichever comes first, and tells the caller which.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from autobot_shared.async_compat import fire_and_forget
from autobot_shared.env_utils import env_float
from events.bus import EventBus, PersistStrategy, get_event_bus
from protocols.agent_kind import AgentKind

if TYPE_CHECKING:
    from protocols.agent_presence import AgentPresenceRegistry

EVT_AGENT_IDLE = "agent_idle"

#: Bounded wait for #16949's one-shot subscription -- a peer that never goes
#: idle within this must not leave the subscriber waiting forever.
IDLE_NOTICE_TIMEOUT_ENV = "AUTOBOT_IDLE_NOTICE_TIMEOUT_SECONDS"
DEFAULT_IDLE_NOTICE_TIMEOUT_SECONDS = 300.0


def idle_notice_timeout_seconds() -> float:
    return env_float(IDLE_NOTICE_TIMEOUT_ENV, DEFAULT_IDLE_NOTICE_TIMEOUT_SECONDS)


def notify_agent_idle(*, kind: AgentKind, tenant_id: str | None, name: str) -> None:
    """Publish the idle transition. Fire-and-forget -- no running loop, no notice.

    Called from `AgentPresenceRegistry.report()`, a synchronous method every
    presence feed adapter calls from an `async def` (a real running loop in
    every production case); a sync unit test calling `report()` directly
    simply gets no notification scheduled, which is correct for a test that
    never awaits anything.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    payload = {"kind": kind.value, "tenant_id": tenant_id, "name": name}
    channel = f"agent:{name}"
    fire_and_forget(
        get_event_bus().publish(channel, EVT_AGENT_IDLE, payload, persist=PersistStrategy.NONE),
        name=f"agent-idle-notice:{name}",
    )


class IdleWaitExpiredError(Exception):
    """Raised by `wait_for_idle()` when the peer never went idle in time."""


async def wait_for_idle(
    presence: "AgentPresenceRegistry",
    *,
    kind: AgentKind,
    tenant_id: str | None,
    name: str,
    bus: EventBus | None = None,
    timeout_seconds: float | None = None,
) -> None:
    """Return once, the moment *name* is idle; raise `IdleWaitExpiredError` on timeout.

    Resolves immediately without subscribing at all if the target is
    already idle -- "the next time" a caller finds an already-free peer is
    now, not a transition to wait for.
    """
    bus = bus if bus is not None else get_event_bus()
    timeout = timeout_seconds if timeout_seconds is not None else idle_notice_timeout_seconds()

    current = next((e for e in presence.list_live(tenant_id) if (e.kind, e.name) == (kind, name)), None)
    if current is not None and not current.busy:
        return

    loop = asyncio.get_running_loop()
    resolved: asyncio.Future[None] = loop.create_future()

    async def _listener(event_data: dict) -> None:
        # EventManager wraps every in-process delivery as {"type", "payload"}
        # (event_manager.py::publish) -- the raw notify_agent_idle() payload
        # is one level down, not at this dict's top level.
        fields = event_data.get("payload", {})
        if (fields.get("kind"), fields.get("tenant_id"), fields.get("name")) == (kind.value, tenant_id, name):
            if not resolved.done():
                resolved.set_result(None)

    bus.subscribe(EVT_AGENT_IDLE, _listener)
    try:
        await asyncio.wait_for(resolved, timeout=timeout)
    except asyncio.TimeoutError:
        raise IdleWaitExpiredError(f"{name!r} ({kind.value}) did not go idle within {timeout}s") from None
    finally:
        bus.unsubscribe(EVT_AGENT_IDLE, _listener)
