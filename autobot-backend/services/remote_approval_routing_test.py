# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Routing an approval to a remote human (#14068), and what it must not touch."""

from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from services.remote_approval import RemoteApprovalStore, extract_token
from services.remote_approval_routing import (
    RemoteApprovalRouting,
    RemoteTarget,
    deliver_approval,
)

_TARGET = RemoteTarget(platform="slack", channel_id="C42")


class _Routing(RemoteApprovalRouting):
    def __init__(self, target):
        self._target = target

    async def target_for(self, session_id):
        return self._target


class _Store(RemoteApprovalStore):
    def __init__(self, record_ok=True):
        self.record_ok = record_ok
        self.recorded = []
        self.forgotten = []

    async def record_delivery(self, delivery):
        self.recorded.append(delivery)
        return self.record_ok

    async def forget(self, approval_id):
        self.forgotten.append(approval_id)


class TestAutonomyIsNotWidened:
    """The invariant the whole issue turns on.

    Today an operator stepping away either blocks the run or drops to the
    `minimal` guard profile — which removes the gate. Everyone takes the second,
    so "nobody is watching" silently becomes "the agent may do more". Routing
    must not be another way to do that.
    """

    def test_the_guard_profile_is_untouched_by_this_module(self):
        import services.remote_approval_routing as routing_module
        from agent_loop import guard_profile

        before = {name: dict(fields) for name, fields in guard_profile.GUARD_PROFILES.items()}
        _ = routing_module.RemoteApprovalRouting()
        after = {name: dict(fields) for name, fields in guard_profile.GUARD_PROFILES.items()}

        assert after == before, "routing mutated the guard profile table"

    def test_routing_does_not_reference_any_autonomy_control(self):
        """Asserted over the AST, not the source text.

        A substring scan cannot distinguish code from prose: the first version of
        this test failed on the module's own docstring, which names these
        identifiers precisely to explain why it must not use them. Walking the
        tree checks what the module actually references.
        """
        import ast
        import pathlib as _p

        tree = ast.parse((_p.Path(__file__).parent / "remote_approval_routing.py").read_text(encoding="utf-8"))

        referenced = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                referenced.add(node.id)
            elif isinstance(node, ast.Attribute):
                referenced.add(node.attr)
            elif isinstance(node, ast.ImportFrom) and node.module:
                referenced.update(node.module.split("."))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    referenced.update(alias.name.split("."))

        for forbidden in ("require_approval_for_sensitive", "GUARD_PROFILES", "AgentLoopConfig", "guard_profile"):
            assert forbidden not in referenced, f"routing references an autonomy control ({forbidden})"

    @pytest.mark.asyncio
    async def test_routing_never_decides_whether_approval_is_required(self):
        """It answers 'where', never 'whether'. A session with no remote target
        returns False so the caller asks inline — not True-with-no-gate."""
        assert (
            await deliver_approval(
                session_id="s1",
                approval_id="a1",
                body="?",
                send=AsyncMock(return_value=True),
                routing=_Routing(None),
                store=_Store(),
            )
            is False
        )


class TestDelivery:
    @pytest.mark.asyncio
    async def test_a_delivered_approval_carries_its_correlation_token(self):
        send = AsyncMock(return_value=True)
        ok = await deliver_approval(
            session_id="s1",
            approval_id="a1b2",
            body="Approve deploy?",
            send=send,
            routing=_Routing(_TARGET),
            store=_Store(),
        )
        assert ok is True
        assert extract_token(send.await_args.kwargs["body"]) == "a1b2"
        assert "Approve deploy?" in send.await_args.kwargs["body"]

    @pytest.mark.asyncio
    async def test_it_goes_to_the_sessions_target(self):
        send = AsyncMock(return_value=True)
        await deliver_approval(
            session_id="s1",
            approval_id="a1",
            body="?",
            send=send,
            routing=_Routing(replace(_TARGET, channel_id="C99")),
            store=_Store(),
        )
        assert send.await_args.kwargs["channel_id"] == "C99"

    @pytest.mark.asyncio
    async def test_the_correlation_is_recorded_before_the_send(self):
        """Ordering matters. A recorded delivery that never went out costs one
        stale key; a send whose correlation failed to persist costs the
        operator's answer — they reply into a void."""
        order = []
        store = _Store()

        async def _record(delivery):
            order.append("record")
            return True

        store.record_delivery = _record

        async def _send(**kwargs):
            order.append("send")
            return True

        await deliver_approval(
            session_id="s1", approval_id="a1", body="?", send=_send, routing=_Routing(_TARGET), store=store
        )
        assert order == ["record", "send"]

    @pytest.mark.asyncio
    async def test_nothing_is_sent_when_the_correlation_cannot_be_recorded(self):
        send = AsyncMock(return_value=True)
        ok = await deliver_approval(
            session_id="s1",
            approval_id="a1",
            body="?",
            send=send,
            routing=_Routing(_TARGET),
            store=_Store(record_ok=False),
        )
        assert ok is False
        send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_failed_send_drops_the_correlation(self):
        """Otherwise a stale token stays resolvable for a message never sent."""
        store = _Store()
        ok = await deliver_approval(
            session_id="s1",
            approval_id="a1",
            body="?",
            send=AsyncMock(return_value=False),
            routing=_Routing(_TARGET),
            store=store,
        )
        assert ok is False and store.forgotten == ["a1"]

    @pytest.mark.asyncio
    async def test_a_raising_send_does_not_kill_the_run(self):
        store = _Store()
        ok = await deliver_approval(
            session_id="s1",
            approval_id="a1",
            body="?",
            send=AsyncMock(side_effect=RuntimeError("channel down")),
            routing=_Routing(_TARGET),
            store=store,
        )
        assert ok is False and store.forgotten == ["a1"]


class TestRoutingStoreDegrades:
    @pytest.mark.asyncio
    async def test_no_redis_means_ask_inline_not_suppress(self, monkeypatch):
        monkeypatch.setattr("services.remote_approval_routing.get_async_redis_client", AsyncMock(return_value=None))
        assert await RemoteApprovalRouting().target_for("s1") is None

    @pytest.mark.asyncio
    async def test_a_partial_routing_record_is_not_a_target(self, monkeypatch):
        redis = AsyncMock()
        redis.hgetall = AsyncMock(return_value={"platform": "slack"})
        monkeypatch.setattr("services.remote_approval_routing.get_async_redis_client", AsyncMock(return_value=redis))
        assert await RemoteApprovalRouting().target_for("s1") is None
