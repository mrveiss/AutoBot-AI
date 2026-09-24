# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A scoped channel is only scoped if delivery honours it (#17363).

`api/live_events.py:_authorize_channel` gates `agent:{id}` to its owner or an
admin, and admits every authenticated client to `global`. Its own comment states
the invariant that makes that safe: *"nothing tenant-scoped may be published to
it"*.

`LiveEventManager.publish` broke that invariant from the other side. It mirrored
**every** non-`global` publish to `global` subscribers, so scoping a channel
changed who it was addressed to and not who received it. #17363 moved the agent
router's events from `global` to `agent:{user_id}`; the mirror handed them back
to every signed-in client.

The mirror is kept for the three claim events, because #15949 depends on it and
rejected a second publish to `global` as double-delivery with mismatched ids --
see `tests/coordination/test_claim_projection.py`. It is keyed on the event type
rather than the channel prefix because `agent:` is overloaded: `agent:{user_id}`
is a human operator's private channel, `agent:{agent_id}` is an automation
agent's claim channel, and no prefix rule can separate them.
"""

import pytest
from starlette.websockets import WebSocketState

import live_event_manager as lem

#: The operator events #17363 moved off `global` -- goal text, the shell command
#: the operator ran, and its stdout.
_OPERATOR_EVENTS = ("goal_received", "command_execution_start", "tool_output", "goal_completed")

#: #15949's three, which must keep reaching the dashboard.
_CLAIM_EVENTS = ("work_claim_acquired", "work_claim_released", "work_claim_conflict")


class _FakeWS:
    def __init__(self) -> None:
        self.client_state = WebSocketState.CONNECTED
        self.messages: list[dict] = []

    async def send_json(self, message: dict) -> None:
        self.messages.append(message)


@pytest.fixture
def manager(monkeypatch):
    class _Stream:
        def __init__(self) -> None:
            self._n: dict[str, int] = {}

        async def next_event_id(self, channel: str) -> int:
            self._n[channel] = self._n.get(channel, 0) + 1
            return self._n[channel]

        async def append(self, channel: str, message: dict) -> None:
            return None

    monkeypatch.setattr(lem, "get_channel_event_stream", lambda: _Stream())
    return lem.LiveEventManager()


@pytest.mark.asyncio
@pytest.mark.parametrize("event_type", _OPERATOR_EVENTS)
async def test_a_global_subscriber_never_sees_an_operators_event(manager, event_type):
    """The defect #17363 exists to close, asserted at the delivery boundary.

    Before the allowlist this failed for all four: the eavesdropper received the
    operator's goal text on a channel it was never authorised to subscribe to.
    """
    eavesdropper, owner = _FakeWS(), _FakeWS()
    await manager.subscribe(eavesdropper, "global")
    await manager.subscribe(owner, "agent:u-7")

    await manager.publish("agent:u-7", event_type, {"goal": "deploy the staging node"})

    assert owner.messages, "the owner must still receive their own event -- otherwise this proves nothing"
    assert eavesdropper.messages == [], (
        f"a `global` subscriber received `{event_type}` addressed to `agent:u-7`; "
        f"`global` admits every authenticated client, so scoping the publish is void (#17363)"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("event_type", _CLAIM_EVENTS)
async def test_the_claim_dashboard_still_sees_agent_scoped_claims(manager, event_type):
    """#15949's fan-out, preserved. Removing it would reverse a recorded ruling."""
    dashboard = _FakeWS()
    await manager.subscribe(dashboard, "global")

    await manager.publish("agent:agent-1", event_type, {"scope": "path:a/b.py"})

    assert len(dashboard.messages) == 1, f"the claim dashboard stopped receiving `{event_type}` (#15949)"
    assert dashboard.messages[0]["channel"] == "agent:agent-1", "the origin channel is preserved"


@pytest.mark.asyncio
async def test_a_global_publish_still_reaches_global(manager):
    """Positive control. Without it, an allowlist that dropped everything would
    pass every assertion above."""
    listener = _FakeWS()
    await manager.subscribe(listener, "global")

    await manager.publish("global", "agent_paused", {"message": "Agent operation paused."})

    assert len(listener.messages) == 1


@pytest.mark.asyncio
async def test_the_allowlist_names_only_the_claim_events(manager):
    """A guard on the guard: widening it is a decision, not a refactor.

    An event type added here reaches every authenticated client, so the set is
    pinned rather than left to grow silently.
    """
    assert lem.MIRRORED_TO_GLOBAL_SUBSCRIBERS == frozenset(_CLAIM_EVENTS), (
        "the set of event types mirrored to `global` changed; every name in it is "
        "readable by every authenticated client, so this needs a reviewer (#17363, #15949)"
    )
