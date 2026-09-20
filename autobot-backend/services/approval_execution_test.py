# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the post-approval execution registry itself (#17038, #17043)."""

import uuid
from types import SimpleNamespace

import pytest

from services import approval_execution

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _clean_registry(monkeypatch):
    monkeypatch.setattr(approval_execution, "_REGISTRY", {})


def _approval(context):
    return SimpleNamespace(id=uuid.uuid4(), context=context)


class TestRunPostApprovalActions:
    async def test_an_approval_with_no_context_action_is_a_no_op(self):
        await approval_execution.run_post_approval_actions(_approval({}), session=None)
        # No handler registered anywhere; reaching here without raising is the proof.

    async def test_an_unregistered_action_is_a_no_op(self):
        approval_execution.register_post_approval_action("known", lambda a, s: None)
        await approval_execution.run_post_approval_actions(_approval({"action": "unknown"}), session=None)

    async def test_a_registered_action_runs_with_the_approval_and_session(self):
        calls = []

        async def handler(approval, session):
            calls.append((approval, session))

        approval_execution.register_post_approval_action("do-thing", handler)
        approval = _approval({"action": "do-thing"})
        sentinel_session = object()

        await approval_execution.run_post_approval_actions(approval, sentinel_session)

        assert calls == [(approval, sentinel_session)]

    async def test_a_handler_exception_is_caught_not_raised(self):
        """A broken action must never take the approve() response down with it (#17038 rule 1)."""

        async def handler(approval, session):
            raise RuntimeError("boom")

        approval_execution.register_post_approval_action("do-thing", handler)

        await approval_execution.run_post_approval_actions(_approval({"action": "do-thing"}), session=None)
        # No raise reaching here is the assertion.

    async def test_registering_the_same_action_twice_replaces_the_handler(self):
        calls = []
        approval_execution.register_post_approval_action("do-thing", lambda a, s: calls.append("first"))

        async def second(approval, session):
            calls.append("second")

        approval_execution.register_post_approval_action("do-thing", second)
        await approval_execution.run_post_approval_actions(_approval({"action": "do-thing"}), session=None)

        assert calls == ["second"]
