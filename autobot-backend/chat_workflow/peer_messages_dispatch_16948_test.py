# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""AI_STACK peer messages are drained at the real dispatch seam (#16948).

`_dispatch_tool_call` polls every 10ms and ran a peer's handler immediately,
interrupting whatever the recipient was doing mid-task
(`protocols/agent_communication.py:520`). `enforce_peer_messages` is called
at the top of `_dispatch_tool_call` (`chat_workflow/tool_handler.py`), the
one seam common to the graph path, the legacy fallback and delegated
subagents (#16948 seam map, confirmed). Drives the real function against a
real `LLMIterationContext`, not a fake standing in for both.
"""

from protocols.agent_communication import AgentIdentity
from protocols.agent_kind import AgentKind
from protocols.agent_presence import AgentPresenceRegistry
from protocols.peer_inbox import PeerInboxDirectory


def _ctx(**overrides):
    from chat_workflow.models import LLMIterationContext

    defaults = dict(
        ollama_endpoint="http://localhost:11434",
        selected_model="test-model",
        session_id="sess-1",
        terminal_session_id="term-1",
        used_knowledge=False,
        rag_citations=[],
        workflow_messages=[],
    )
    defaults.update(overrides)
    return LLMIterationContext(**defaults)


def _sender(name: str = "rag") -> AgentIdentity:
    return AgentIdentity(agent_id=name, agent_type=name, kind=AgentKind.AI_STACK, name=name, tenant_id=None)


def _directory_with_chat_registered() -> PeerInboxDirectory:
    presence = AgentPresenceRegistry(ttl_seconds=60)
    presence.report(kind=AgentKind.AI_STACK, tenant_id=None, name="chat", instance_id="chat", busy=False)
    return PeerInboxDirectory(presence)


class TestEnforcePeerMessages:
    def test_a_queued_message_is_drained_into_ctx_context(self, monkeypatch):
        from chat_workflow.tool_dispatch_guards import enforce_peer_messages

        directory = _directory_with_chat_registered()
        directory.send(kind=AgentKind.AI_STACK, name="chat", sender=_sender(), content="hello", message_id="m1")
        monkeypatch.setattr("protocols.peer_inbox.get_peer_inbox_directory", lambda: directory)

        ctx = _ctx()
        enforce_peer_messages(ctx)

        assert ctx.context["peer_messages"][0]["content"] == "hello"
        assert ctx.context["peer_messages"][0]["sender_name"] == "rag"

    def test_never_blocks_the_tool_call(self, monkeypatch):
        """The one property that distinguishes this from every other guard: it
        always returns None, since a peer message is context, not an instruction
        that could refuse a tool call (#16946 owner ruling)."""
        from chat_workflow.tool_dispatch_guards import enforce_peer_messages

        directory = _directory_with_chat_registered()
        directory.send(kind=AgentKind.AI_STACK, name="chat", sender=_sender(), content="hello", message_id="m1")
        monkeypatch.setattr("protocols.peer_inbox.get_peer_inbox_directory", lambda: directory)

        assert enforce_peer_messages(_ctx()) is None

    def test_no_ctx_is_a_no_op(self, monkeypatch):
        directory = _directory_with_chat_registered()
        directory.send(kind=AgentKind.AI_STACK, name="chat", sender=_sender(), content="hello", message_id="m1")
        monkeypatch.setattr("protocols.peer_inbox.get_peer_inbox_directory", lambda: directory)

        from chat_workflow.tool_dispatch_guards import enforce_peer_messages

        assert enforce_peer_messages(None) is None
        # The message is still queued -- a missing ctx drops the delivery
        # opportunity for this call, not the message itself.
        assert directory.inbox_for(kind=AgentKind.AI_STACK, tenant_id=None, name="chat").drain() != []

    def test_a_message_queued_after_this_calls_own_drain_is_not_included(self, monkeypatch):
        """The mid-task-vs-next-turn boundary itself (#16948 AC4): a message
        that arrives after THIS dispatch call already drained is held for the
        next one, not retroactively spliced into a context already built."""
        from chat_workflow.tool_dispatch_guards import enforce_peer_messages

        directory = _directory_with_chat_registered()
        monkeypatch.setattr("protocols.peer_inbox.get_peer_inbox_directory", lambda: directory)

        ctx = _ctx()
        enforce_peer_messages(ctx)  # drains an empty inbox -- nothing queued yet
        assert "peer_messages" not in ctx.context

        # A message arrives mid-task, after this call's own drain already ran.
        directory.send(kind=AgentKind.AI_STACK, name="chat", sender=_sender(), content="late", message_id="m2")
        assert "peer_messages" not in ctx.context  # not retroactively added

        # It surfaces only on the NEXT dispatch call's own drain -- a fresh ctx,
        # matching a fresh LLM turn.
        next_ctx = _ctx()
        enforce_peer_messages(next_ctx)
        assert next_ctx.context["peer_messages"][0]["content"] == "late"
