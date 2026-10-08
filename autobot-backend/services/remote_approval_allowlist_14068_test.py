# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The remote-approval path is wired in, and it denies by default (#14068).

Three claims, each failing for a different reason if the work regresses:

1. **Fail closed.** A reply from a sender outside the delivery's allowlist
   resolves nothing, and an empty allowlist admits nobody. An approval is a
   safety control: "we could not establish who answered" must read as *not
   answered*, never as *approved*.
2. **Wired.** ``chat_workflow/tool_handler.py``'s approval path really calls
   ``mirror_approval_request`` — asserted over the AST, with a contrast fixture
   where the name appears only in prose, because a text match on a module this
   size is satisfied by any comment mentioning it.
3. **A mirror, not a decision.** Delivery failing in any way returns False and
   resolves nothing; no path through the delivery code answers an approval.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from services.remote_approval import DeliveredApproval, embed_token, resolve_from_reply
from services.remote_approval_routing import RemoteTarget, deliver_approval
from services.remote_approval_sender import mirror_approval_request

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TOOL_HANDLER = _REPO_ROOT / "autobot-backend" / "chat_workflow" / "tool_handler.py"
_WIRED_CALL = "mirror_approval_request"

_ALLOWED = DeliveredApproval(approval_id="a1b2c3", platform="slack", channel_id="C42", allowed_senders=("U-operator",))
_NOBODY = DeliveredApproval(approval_id="a1b2c3", platform="slack", channel_id="C42")


class _Store:
    def __init__(self, delivery=None):
        self._delivery = delivery
        self.recorded: list[DeliveredApproval] = []
        self.forgotten: list[str] = []

    async def get_delivery(self, approval_id):
        if self._delivery and self._delivery.approval_id == approval_id:
            return self._delivery
        return None

    async def record_delivery(self, delivery):
        self.recorded.append(delivery)
        return True

    async def forget(self, approval_id):
        self.forgotten.append(approval_id)


class _Routing:
    def __init__(self, target):
        self._target = target

    async def target_for(self, session_id):
        return self._target


class TestTheAllowlistFailsClosed:
    @pytest.mark.asyncio
    async def test_the_allowlisted_operator_can_decide(self):
        """The positive control: without it, every assertion below is vacuous."""
        got = await resolve_from_reply(
            embed_token("👍", "a1b2c3"),
            platform="slack",
            channel_id="C42",
            sender_id="U-operator",
            store=_Store(_ALLOWED),
        )
        assert got is not None and got.approved is True and got.sender_id == "U-operator"

    @pytest.mark.asyncio
    async def test_a_sender_outside_the_allowlist_resolves_nothing(self):
        assert (
            await resolve_from_reply(
                embed_token("👍", "a1b2c3"),
                platform="slack",
                channel_id="C42",
                sender_id="U-intruder",
                store=_Store(_ALLOWED),
            )
            is None
        )

    @pytest.mark.asyncio
    async def test_an_empty_allowlist_admits_nobody(self):
        """Being in the channel is not authorisation to answer for the operator."""
        assert (
            await resolve_from_reply(
                embed_token("👍", "a1b2c3"),
                platform="slack",
                channel_id="C42",
                sender_id="U-operator",
                store=_Store(_NOBODY),
            )
            is None
        )

    @pytest.mark.asyncio
    async def test_an_unidentified_sender_resolves_nothing(self):
        assert (
            await resolve_from_reply(
                embed_token("👍", "a1b2c3"),
                platform="slack",
                channel_id="C42",
                sender_id="",
                store=_Store(_ALLOWED),
            )
            is None
        )

    @pytest.mark.asyncio
    async def test_a_denial_from_the_operator_still_denies(self):
        got = await resolve_from_reply(
            embed_token("👎", "a1b2c3"),
            platform="slack",
            channel_id="C42",
            sender_id="U-operator",
            store=_Store(_ALLOWED),
        )
        assert got is not None and got.approved is False


class TestDeliveryCarriesTheAllowlist:
    @pytest.mark.asyncio
    async def test_the_recorded_delivery_keeps_the_route_s_allowlist(self):
        store = _Store()
        sent: list[str] = []

        async def _send(*, platform, channel_id, body):
            sent.append(body)
            return True

        ok = await deliver_approval(
            session_id="s1",
            approval_id="a1b2c3",
            body="Approval required",
            send=_send,
            routing=_Routing(RemoteTarget("slack", "C42", allowed_senders=("U-operator",))),
            store=store,
        )
        assert ok is True
        assert store.recorded[0].allowed_senders == ("U-operator",)
        assert "[ab:a1b2c3]" in sent[0]

    @pytest.mark.asyncio
    async def test_a_session_with_no_route_delivers_nothing_and_does_not_raise(self):
        async def _send(*, platform, channel_id, body):  # pragma: no cover - must not run
            raise AssertionError("an unrouted session must not be messaged")

        assert (
            await deliver_approval(
                session_id="s1",
                approval_id="a1b2c3",
                body="Approval required",
                send=_send,
                routing=_Routing(None),
                store=_Store(),
            )
            is False
        )

    @pytest.mark.asyncio
    async def test_a_channel_failure_is_false_never_an_approval(self):
        store = _Store()

        async def _send(*, platform, channel_id, body):
            raise RuntimeError("channel down")

        assert (
            await deliver_approval(
                session_id="s1",
                approval_id="a1b2c3",
                body="Approval required",
                send=_send,
                routing=_Routing(RemoteTarget("slack", "C42", allowed_senders=("U-operator",))),
                store=store,
            )
            is False
        )
        assert store.forgotten == ["a1b2c3"]

    @pytest.mark.asyncio
    async def test_the_mirror_swallows_a_routing_failure(self):
        """A delivery problem may not change a safety decision, or crash a turn."""

        class _Exploding:
            async def target_for(self, session_id):
                raise RuntimeError("redis down")

        assert (
            await mirror_approval_request(session_id="s1", approval_id="a1b2c3", body="x", routing=_Exploding())
            is False
        )


def _calls_named(source: str, name: str) -> bool:
    """True when *source* contains a real call to *name* — AST, not text."""
    return any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name
        for node in ast.walk(ast.parse(source))
    )


def _awaits_named(node: ast.AST, name: str) -> bool:
    """True when *node* contains ``await name(...)`` — the await, not just the call.

    #14068 review: the caller used to accept a bare ``name(...)``. That regression builds a
    coroutine and never sends the approval, and a Call-only check cannot see the difference,
    so a test named "...is_awaited..." passed on exactly the bug it was written to catch.
    """
    return any(
        isinstance(inner, ast.Await)
        and isinstance(inner.value, ast.Call)
        and isinstance(inner.value.func, ast.Name)
        and inner.value.func.id == name
        for inner in ast.walk(node)
    )


#: The mirror called but never awaited — a coroutine created and dropped.
_UNAWAITED_FIXTURE = """
async def _handle_pending_approval(self, session_id, approval_id):
    await self._persist_approval_request(None, session_id, approval_id)
    mirror_approval_request(session_id=session_id, approval_id=approval_id, body="x")
"""


_CONTRAST_FIXTURE = '''
async def _handle_approval(self, session_id, approval_id):
    """Ask for approval.

    A future change should call mirror_approval_request here so the operator is
    reached wherever they are.
    """
    # mirror_approval_request(session_id=session_id, approval_id=approval_id)
    await self._persist_approval_request(approval_id, session_id, "t")
'''


class TestTheApprovalPathIsWired:
    def test_the_tool_handler_really_calls_the_mirror(self):
        assert _calls_named(_TOOL_HANDLER.read_text(encoding="utf-8"), _WIRED_CALL)

    def test_prose_naming_the_call_does_not_satisfy_the_guard(self):
        assert _WIRED_CALL in _CONTRAST_FIXTURE
        assert not _calls_named(_CONTRAST_FIXTURE, _WIRED_CALL)

    def test_the_mirror_is_awaited_in_the_approval_flow_not_some_other_one(self):
        """Named selector: the call is **awaited** in the function that persists the request."""
        source = _TOOL_HANDLER.read_text(encoding="utf-8")
        hosting = [
            node.name
            for node in ast.walk(ast.parse(source))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _awaits_named(node, _WIRED_CALL)
        ]
        assert hosting, f"no function awaits {_WIRED_CALL}"
        for name in hosting:
            function = next(
                node
                for node in ast.walk(ast.parse(source))
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
            )
            assert any(
                isinstance(inner, ast.Attribute) and inner.attr == "_persist_approval_request"
                for inner in ast.walk(function)
            ), f"{name} awaits the mirror but is not the approval path"

    def test_an_unawaited_mirror_does_not_satisfy_the_guard(self):
        """Control: the coroutine-dropped regression must fail, not pass quietly."""
        tree = ast.parse(_UNAWAITED_FIXTURE)
        assert _calls_named(_UNAWAITED_FIXTURE, _WIRED_CALL), "fixture must contain the call"
        assert not _awaits_named(tree, _WIRED_CALL), "an unawaited call must not read as awaited"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__]))
