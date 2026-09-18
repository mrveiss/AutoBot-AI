# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for PeerInboxDirectory (#16948)."""

import pytest

from protocols.agent_communication import AgentIdentity
from protocols.agent_kind import AgentKind
from protocols.agent_presence import AgentPresenceRegistry
from protocols.peer_inbox import PeerInboxDirectory, RecipientNotAddressableError


def _sender(*, name: str = "sender-1", tenant_id: str | None = None) -> AgentIdentity:
    return AgentIdentity(agent_id=name, agent_type="test", kind=AgentKind.AI_STACK, name=name, tenant_id=tenant_id)


class TestSendAndDrain:
    def test_a_message_to_a_live_recipient_is_delivered(self):
        presence = AgentPresenceRegistry(ttl_seconds=60)
        presence.report(kind=AgentKind.SESSION, tenant_id=None, name="sess-1", instance_id="i1", busy=False)
        directory = PeerInboxDirectory(presence)

        directory.send(kind=AgentKind.SESSION, name="sess-1", sender=_sender(), content="hello", message_id="m1")

        drained = directory.inbox_for(kind=AgentKind.SESSION, tenant_id=None, name="sess-1").drain()
        assert len(drained) == 1
        assert drained[0].content == "hello"
        assert drained[0].sender.name == "sender-1"

    def test_drain_empties_the_inbox(self):
        presence = AgentPresenceRegistry(ttl_seconds=60)
        presence.report(kind=AgentKind.SESSION, tenant_id=None, name="sess-1", instance_id="i1", busy=False)
        directory = PeerInboxDirectory(presence)
        directory.send(kind=AgentKind.SESSION, name="sess-1", sender=_sender(), content="hi", message_id="m1")

        first = directory.inbox_for(kind=AgentKind.SESSION, tenant_id=None, name="sess-1").drain()
        second = directory.inbox_for(kind=AgentKind.SESSION, tenant_id=None, name="sess-1").drain()

        assert len(first) == 1
        assert second == []

    def test_multiple_messages_drain_oldest_first(self):
        presence = AgentPresenceRegistry(ttl_seconds=60)
        presence.report(kind=AgentKind.SESSION, tenant_id=None, name="sess-1", instance_id="i1", busy=False)
        directory = PeerInboxDirectory(presence)
        directory.send(kind=AgentKind.SESSION, name="sess-1", sender=_sender(), content="first", message_id="m1")
        directory.send(kind=AgentKind.SESSION, name="sess-1", sender=_sender(), content="second", message_id="m2")

        drained = directory.inbox_for(kind=AgentKind.SESSION, tenant_id=None, name="sess-1").drain()

        assert [e.content for e in drained] == ["first", "second"]


class TestAddressingAndTenancy:
    def test_a_recipient_not_in_presence_is_refused(self):
        presence = AgentPresenceRegistry(ttl_seconds=60)
        directory = PeerInboxDirectory(presence)

        with pytest.raises(RecipientNotAddressableError):
            directory.send(kind=AgentKind.SESSION, name="ghost", sender=_sender(), content="hi", message_id="m1")

    def test_a_recipient_in_a_different_tenant_is_refused(self):
        presence = AgentPresenceRegistry(ttl_seconds=60)
        presence.report(kind=AgentKind.COMPANY_OS, tenant_id="tenant-y", name="agent-y", instance_id="i1", busy=False)
        directory = PeerInboxDirectory(presence)

        with pytest.raises(RecipientNotAddressableError):
            directory.send(
                kind=AgentKind.COMPANY_OS,
                name="agent-y",
                sender=_sender(tenant_id="tenant-x"),
                content="hi",
                message_id="m1",
            )

    def test_a_shared_recipient_is_addressable_from_any_tenant(self):
        presence = AgentPresenceRegistry(ttl_seconds=60)
        presence.report(kind=AgentKind.AI_STACK, tenant_id=None, name="rag", instance_id="rag", busy=False)
        directory = PeerInboxDirectory(presence)

        directory.send(
            kind=AgentKind.AI_STACK, name="rag", sender=_sender(tenant_id="tenant-x"), content="hi", message_id="m1"
        )

        drained = directory.inbox_for(kind=AgentKind.AI_STACK, tenant_id=None, name="rag").drain()
        assert len(drained) == 1

    def test_the_recipients_own_tenant_is_used_for_the_inbox_key_not_the_senders(self):
        """A same-tenant delivery must key under the recipient's tenant.

        If `send()` trusted a caller-supplied tenant_id instead of the
        matched presence entry's own, a mismatched value here would key the
        inbox under a tenant the recipient's own drain call never looks
        under, silently losing the message.
        """
        presence = AgentPresenceRegistry(ttl_seconds=60)
        presence.report(kind=AgentKind.COMPANY_OS, tenant_id="tenant-x", name="agent-x", instance_id="i1", busy=False)
        directory = PeerInboxDirectory(presence)

        directory.send(
            kind=AgentKind.COMPANY_OS,
            name="agent-x",
            sender=_sender(tenant_id="tenant-x"),
            content="hi",
            message_id="m1",
        )

        drained = directory.inbox_for(kind=AgentKind.COMPANY_OS, tenant_id="tenant-x", name="agent-x").drain()
        assert len(drained) == 1

    def test_external_is_never_addressable(self):
        """EXTERNAL identities are refused at presence.report() itself (#16947) --
        they can never appear in list_live(), so send() refuses them structurally."""
        presence = AgentPresenceRegistry(ttl_seconds=60)
        directory = PeerInboxDirectory(presence)

        with pytest.raises(RecipientNotAddressableError):
            directory.send(kind=AgentKind.EXTERNAL, name="peer-1", sender=_sender(), content="hi", message_id="m1")


class TestSenderAddressPreserved:
    def test_the_delivered_entry_carries_the_senders_full_identity_for_reply(self):
        presence = AgentPresenceRegistry(ttl_seconds=60)
        presence.report(kind=AgentKind.SESSION, tenant_id=None, name="sess-1", instance_id="i1", busy=False)
        directory = PeerInboxDirectory(presence)
        sender = _sender(name="rag", tenant_id=None)

        directory.send(kind=AgentKind.SESSION, name="sess-1", sender=sender, content="hi", message_id="m1")

        entry = directory.inbox_for(kind=AgentKind.SESSION, tenant_id=None, name="sess-1").drain()[0]
        assert entry.sender is sender
        assert entry.to_dict()["sender_name"] == "rag"
