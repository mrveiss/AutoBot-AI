# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Live-event publishing for the agent router (#17354).

Extracted from `api/agent.py`, where `_publish_event_safe` hardcoded the
`"global"` channel. `api/live_events.py:_authorize_channel` admits **every
authenticated client** to `global`, and these events carry an operator's goal
text, the shell command they ran and its stdout, so the audience was wrong for
all but two of them -- and no caller could fix that, because the channel was
not theirs to pass.

Channel choice now happens at the call site, and it happens here rather than
inline so there is one place to read the rule:

- `owner_channel(current_user)` -> `agent:{id}`, which `_authorize_channel`
  admits only to the client whose `user_id` or `username` is `{id}` (or to an
  admin). Anything naming one operator's input, command or output goes here.
- `BROADCAST_CHANNEL` -> `global`, for events that are genuinely everyone's.
  Grepping this name enumerates the deliberate broadcasts, which matters
  because a channel passed as a variable is invisible to
  `repo_tests/global_channel_carries_no_tenant_payload_17354_test.py`.
"""

from __future__ import annotations

from autobot_shared.logging_manager import get_logger
from events.bus import PersistStrategy, get_event_bus

logger = get_logger(__name__)

#: The agent's run state is not one tenant's: `AgentOrchestrator` is a
#: process-wide singleton, so `agent_paused`/`agent_resumed` say something true
#: of the whole node, and their payload is a fixed sentence with no identifiers.
#: #17354's fourth criterion allows exactly this -- documented as genuinely
#: global rather than scoped by pattern-match.
BROADCAST_CHANNEL = "global"


def owner_channel(current_user: dict | None) -> str | None:
    """The calling operator's own channel, or `None` when it cannot be named.

    `None` is not a fallback to broadcast: `publish_event_safe` drops the event.
    An unaddressable event is a bug in the caller, and dropping it fails closed
    where defaulting to `global` would reopen #17354 quietly.
    """
    payload = current_user or {}
    claimed = str(payload.get("user_id") or payload.get("username") or "")
    return f"agent:{claimed}" if claimed else None


async def publish_event_safe(channel: str | None, event_name: str, data: dict) -> None:
    """Publish one event, treating failure as non-fatal (Issue #281).

    `channel` is the caller's to choose (#17354). A falsy channel drops the
    event with a warning -- see `owner_channel`.
    """
    if not channel:
        logger.warning("Not publishing %s: no owner channel to address it to (#17354)", event_name)
        return
    try:
        await get_event_bus().publish(channel, event_name, data, persist=PersistStrategy.NONE)
    except Exception as e:  # noqa: BLE001 -- publishing is best-effort by design
        logger.warning("Failed to publish %s event: %s", event_name, e)


async def publish_goal_events(goal: str, use_phi2: bool, channel: str | None) -> None:
    """Publish `user_message` and `goal_received` (Issue #620).

    Both carry the operator's own goal text, which is why the channel is a
    parameter and not `global` (#17354).
    """
    await publish_event_safe(channel, "user_message", {"message": goal})
    await publish_event_safe(channel, "goal_received", {"goal": goal, "use_phi2": use_phi2})
