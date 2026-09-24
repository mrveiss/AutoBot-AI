# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the post-approval execution registry itself (#17038, #17043, #17141)."""

import uuid
from types import SimpleNamespace

import pytest

from services import approval_execution

pytestmark = pytest.mark.asyncio


class _FakeSession:
    """Records every ApprovalComment added and every commit, nothing else."""

    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


@pytest.fixture(autouse=True)
def _clean_registry(monkeypatch):
    monkeypatch.setattr(approval_execution, "_REGISTRY", {})
    # #17315: and the proposer map alongside it. These tests register fake
    # actions; left in the real dict they would reach
    # approval_execution_proposer_test, which asserts every registered action
    # names an importable production proposer.
    monkeypatch.setattr(approval_execution, "_PROPOSERS", {})


@pytest.fixture(autouse=True)
def _fake_audit_log(monkeypatch):
    """Every dispatch-failure test asserts on this instead of a live audit backend."""
    calls = []

    async def _audit_log(operation, **kwargs):
        calls.append({"operation": operation, **kwargs})
        return True

    monkeypatch.setattr(approval_execution, "audit_log", _audit_log)
    return calls


def _approval(context, decided_by_user="alice"):
    return SimpleNamespace(id=uuid.uuid4(), context=context, decided_by_user=decided_by_user)


class TestRunPostApprovalActions:
    async def test_an_approval_with_no_context_action_is_a_no_op(self):
        await approval_execution.run_post_approval_actions(_approval({}), session=None)
        # No handler registered anywhere; reaching here without raising is the proof.

    async def test_an_unregistered_action_is_recorded_as_an_anomaly_not_a_no_op(self, _fake_audit_log):
        """#17141 AC2: an approved action naming no registered handler is a
        recorded deployment defect, not silence -- it means the module that
        would have registered it was never imported."""
        approval_execution.register_post_approval_action(
            "known", lambda a, s: None, proposed_by="services.approval_execution_test"
        )
        approval = _approval({"action": "unknown"})
        session = _FakeSession()

        await approval_execution.run_post_approval_actions(approval, session)

        assert session.commits == 1
        comment = session.added[0]
        assert comment.approval_id == approval.id
        assert comment.author_type == "system"
        assert "unknown" in comment.body
        assert "no handler registered" in comment.body

        assert len(_fake_audit_log) == 1
        entry = _fake_audit_log[0]
        assert entry["operation"] == "approval.post_action_failed"
        assert entry["result"] == "error"
        assert entry["user_id"] == "alice"
        assert entry["resource"] == "unknown"
        assert entry["details"]["approval_id"] == str(approval.id)

    async def test_a_registered_action_runs_with_the_approval_and_session(self):
        calls = []

        async def handler(approval, session):
            calls.append((approval, session))

        approval_execution.register_post_approval_action(
            "do-thing", handler, proposed_by="services.approval_execution_test"
        )
        approval = _approval({"action": "do-thing"})
        sentinel_session = object()

        await approval_execution.run_post_approval_actions(approval, sentinel_session)

        assert calls == [(approval, sentinel_session)]

    async def test_a_handler_exception_is_caught_not_raised_but_recorded(self, _fake_audit_log):
        """#17141 AC1: a broken action must never take the approve() response
        down with it (#17038 rule 1) -- AND must leave a durable trail, not
        just a log line, on the approval it failed under."""

        async def handler(approval, session):
            raise RuntimeError("boom")

        approval_execution.register_post_approval_action(
            "do-thing", handler, proposed_by="services.approval_execution_test"
        )
        approval = _approval({"action": "do-thing"})
        session = _FakeSession()

        await approval_execution.run_post_approval_actions(approval, session)
        # No raise reaching here is half the assertion; the rest is the trail:

        assert session.commits == 1
        comment = session.added[0]
        assert comment.approval_id == approval.id
        assert "do-thing" in comment.body
        assert "RuntimeError" in comment.body

        assert _fake_audit_log[0]["result"] == "error"
        assert _fake_audit_log[0]["resource"] == "do-thing"

    async def test_a_handler_raising_an_oserror_never_leaks_its_path_into_the_trail(self, _fake_audit_log):
        """#17141 review: an exception's own text can carry a host filesystem
        path (str(OSError) appends .filename) -- the recorded reason must not."""
        import errno

        async def handler(approval, session):
            raise OSError(errno.EACCES, "Permission denied", "/opt/autobot/data/code-sources/abc123")

        approval_execution.register_post_approval_action(
            "do-thing", handler, proposed_by="services.approval_execution_test"
        )
        approval = _approval({"action": "do-thing"})
        session = _FakeSession()

        await approval_execution.run_post_approval_actions(approval, session)

        comment = session.added[0]
        assert "/opt/autobot" not in comment.body
        assert "abc123" not in comment.body
        assert "Permission denied" in comment.body

        details = _fake_audit_log[0]["details"]
        assert "/opt/autobot" not in details["reason"]
        assert "abc123" not in details["reason"]

    async def test_registering_the_same_action_twice_replaces_the_handler(self):
        calls = []
        approval_execution.register_post_approval_action(
            "do-thing", lambda a, s: calls.append("first"), proposed_by="services.approval_execution_test"
        )

        async def second(approval, session):
            calls.append("second")

        approval_execution.register_post_approval_action(
            "do-thing", second, proposed_by="services.approval_execution_test"
        )
        await approval_execution.run_post_approval_actions(_approval({"action": "do-thing"}), session=None)

        assert calls == ["second"]

    async def test_a_failure_to_record_the_trail_itself_never_raises(self, _fake_audit_log):
        """The recording path shares the same never-crash-approve() guarantee
        as dispatch itself: a session that cannot commit must not surface."""

        class _BrokenSession:
            def add(self, obj):
                pass

            async def commit(self):
                raise RuntimeError("db is down")

        async def handler(approval, session):
            raise RuntimeError("boom")

        approval_execution.register_post_approval_action(
            "do-thing", handler, proposed_by="services.approval_execution_test"
        )

        await approval_execution.run_post_approval_actions(_approval({"action": "do-thing"}), _BrokenSession())
        # No raise reaching here is the assertion.
