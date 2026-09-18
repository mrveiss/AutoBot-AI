#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Peer messages, delivered at the recipient's next turn boundary (#16948).

`AgentCommunicationProtocol._process_incoming_messages` polls every 10ms and
runs a peer's handler immediately (`protocols/agent_communication.py:520`),
awaited inline -- interrupting whatever the recipient is doing mid-task, and
stalling delivery to every other channel until that handler returns. The fix
is a queue per recipient, drained non-blocking at each kind's own real turn
boundary (mapped and confirmed on #16946/#16948 -- there is no single
seam common to all three kinds, so each integrates this module at its own):

- AI_STACK: `chat_workflow/tool_handler.py`'s `_dispatch_tool_call`, wired for
  the `"chat"` role only today -- `"rag"`/`"system_commands"` are live in
  presence but not yet addressable (#16997).
- SESSION: `services/agent_terminal/service.py`'s `execute_command`.
- COMPANY_OS: out of this module's scope -- #16992, delivered through a
  heartbeat run's own context, which has no queue-and-drain shape.

A peer message is never human approval (#16946 owner ruling): draining one
here only makes its content visible as context for whatever the recipient
does next -- it does not itself invoke a tool. A tool call that content
prompts still goes through that kind's own ordinary sensitive-tool gate
exactly as it would for any other trigger.

Addressing is by the presence registry's stable `(kind, tenant_id, name)`,
never a process-start id (#16946 §2) -- `PeerInboxDirectory.send()` reuses
`AgentPresenceRegistry.list_live(tenant_id)` itself as the authorization
check, so a message can never reach a recipient the sender's own tenant
could not otherwise see: `UNKNOWN_TENANT` resolves to shared-only, and
`EXTERNAL` identities are never in presence, so they can never be addressed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from autobot_shared.singleton_factory import lazy_singleton
from protocols.agent_communication import AgentIdentity
from protocols.agent_kind import AgentKind
from protocols.agent_presence import AgentPresenceRegistry, get_presence_registry


@dataclass
class PeerMessageEntry:
    """A message from a named peer, absorbed by the recipient's next turn.

    `sender` is the presence-registry identity to reply to -- taken from the
    envelope's `header.sender` by the caller of `PeerInboxDirectory.send()`,
    never from the payload (the exact place #16950's confused-deputy bug
    drops it, `agents/base_agent.py:419` `_handle_communication_request`).
    """

    message_id: str
    sender: AgentIdentity
    content: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "message_id": self.message_id,
            "sender_kind": self.sender.kind.value,
            "sender_tenant_id": self.sender.tenant_id,
            "sender_name": self.sender.name,
            "content": self.content,
            "timestamp": self.timestamp,
        }


class PeerInbox:
    """One recipient's queue, drained non-blocking at its own turn boundary."""

    def __init__(self) -> None:
        self._entries: list[PeerMessageEntry] = []

    def deliver(self, entry: PeerMessageEntry) -> None:
        self._entries.append(entry)

    def drain(self) -> list[PeerMessageEntry]:
        """Every pending message, oldest first; the inbox is empty afterwards."""
        drained, self._entries = self._entries, []
        return drained


class RecipientNotAddressableError(Exception):
    """Raised by `send()` when the sender's tenant cannot see this recipient.

    Covers all three reasons at once, deliberately not distinguished further:
    the recipient does not exist, is a different (non-shared) tenant, or is
    `EXTERNAL` (never in presence). Telling a sender WHICH of the three is
    true would let it enumerate names it cannot address -- the refusal must
    look the same from outside.
    """


#: `sync_ai_stack_presence` reports every `AgentHealthRegistry` role as its
#: own addressable AI_STACK entry, but only `"chat"` has a drain wired
#: (`chat_workflow/tool_dispatch_guards.py::enforce_peer_messages`) -- `"rag"`
#: and `"system_commands"` run their own `StandardizedAgent.process_request`
#: flow, unrelated to that seam. Addressing them would succeed (they are
#: live) and then silently lose the message forever, which is worse than
#: refusing. Restricted here until #16997 wires their own turn boundary.
_AI_STACK_ADDRESSABLE_NAMES = frozenset({"chat"})


class PeerInboxDirectory:
    """Maps a live presence name to its `PeerInbox`; the addressing layer.

    One directory per process, matching `AgentPresenceRegistry` -- inboxes
    are not persisted or cross-process, same as presence itself (#16947 §6).
    """

    def __init__(self, presence: AgentPresenceRegistry) -> None:
        self._presence = presence
        self._inboxes: dict[tuple[AgentKind, str | None, str], PeerInbox] = {}

    def inbox_for(self, *, kind: AgentKind, tenant_id: str | None, name: str) -> PeerInbox:
        """The named recipient's inbox, created on first use.

        Called by the recipient's own drain point, not by a sender -- this
        does not check presence or tenancy; `send()` does, before a sender
        ever reaches an inbox object.
        """
        key = (kind, tenant_id, name)
        if key not in self._inboxes:
            self._inboxes[key] = PeerInbox()
        return self._inboxes[key]

    def send(
        self,
        *,
        kind: AgentKind,
        name: str,
        sender: AgentIdentity,
        content: str,
        message_id: str,
    ) -> None:
        """Deliver *content* to the named recipient, if the sender may address it.

        Authorization is exactly `list_live(sender.tenant_id)` containing the
        recipient -- the same rule presence itself enforces for visibility,
        applied here to addressing so the two can never drift apart. The
        recipient's `tenant_id` for the inbox key comes from that matched
        entry, never a caller-supplied value: trusting the caller could key
        the delivery under a tenant the recipient's own drain call never
        looks under, silently losing the message rather than refusing it.

        An AI_STACK name outside `_AI_STACK_ADDRESSABLE_NAMES` is refused
        for the same reason: being live in presence is not the same as
        having a drain that will ever read this inbox (#16997).
        """
        match = next((e for e in self._presence.list_live(sender.tenant_id) if (e.kind, e.name) == (kind, name)), None)
        if match is None:
            raise RecipientNotAddressableError(f"{name!r} ({kind.value}) is not addressable from this tenant")
        if kind is AgentKind.AI_STACK and name not in _AI_STACK_ADDRESSABLE_NAMES:
            raise RecipientNotAddressableError(
                f"{name!r} (ai_stack) is live but has no wired peer-message drain yet (#16997)"
            )
        self.inbox_for(kind=kind, tenant_id=match.tenant_id, name=name).deliver(
            PeerMessageEntry(message_id=message_id, sender=sender, content=content)
        )


get_peer_inbox_directory = lazy_singleton(lambda: PeerInboxDirectory(get_presence_registry()))
