# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the approved-cleanup executor wiring delete_candidate() in (#17039 review)."""

import uuid

import pytest

from models.approval import Approval
from services import orphan_storage, orphan_storage_cleanup_action

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


def _approval(**context) -> Approval:
    return Approval(
        id=uuid.uuid4(),
        title="orphan cleanup",
        approval_type="destructive_action",
        decided_by_user="alice",
        context=context,
    )


@pytest.fixture(autouse=True)
def _clean_registry(monkeypatch):
    monkeypatch.setattr(orphan_storage, "_REGISTRY", {})


class TestExecuteOrphanStorageDelete:
    async def test_a_successful_delete_is_recorded_as_a_comment_and_an_audit_entry(self, monkeypatch):
        async def _delete(provider, candidate_id):
            assert (provider, candidate_id) == ("code_source_clone", "abc")
            return orphan_storage.DeleteResult(deleted=True)

        monkeypatch.setattr(orphan_storage_cleanup_action, "delete_candidate", _delete)

        audited = {}

        async def _audit_log(operation, **kwargs):
            audited["operation"] = operation
            audited.update(kwargs)
            return True

        monkeypatch.setattr(orphan_storage_cleanup_action, "audit_log", _audit_log)

        approval = _approval(action="orphan_storage_delete", provider="code_source_clone", candidate_id="abc")
        session = _FakeSession()

        await orphan_storage_cleanup_action.execute_orphan_storage_delete(approval, session)

        assert session.commits == 1
        assert len(session.added) == 1
        comment = session.added[0]
        assert comment.approval_id == approval.id
        assert comment.author_type == "system"
        assert "deleted code_source_clone:abc" in comment.body

        assert audited["operation"] == "orphan_storage.delete"
        assert audited["result"] == "success"
        assert audited["user_id"] == "alice"
        assert audited["resource"] == "code_source_clone:abc"
        assert audited["details"]["approval_id"] == str(approval.id)

    async def test_a_refused_delete_is_recorded_as_a_failure_not_swallowed(self, monkeypatch):
        """delete_candidate() re-checking orphan status and refusing must still be reported (#17039 AC)."""

        async def _delete(provider, candidate_id):
            return orphan_storage.DeleteResult(deleted=False, reason="no longer orphaned")

        monkeypatch.setattr(orphan_storage_cleanup_action, "delete_candidate", _delete)

        audited = {}

        async def _audit_log(operation, **kwargs):
            audited["operation"] = operation
            audited.update(kwargs)
            return True

        monkeypatch.setattr(orphan_storage_cleanup_action, "audit_log", _audit_log)

        approval = _approval(action="orphan_storage_delete", provider="code_source_clone", candidate_id="abc")
        session = _FakeSession()

        await orphan_storage_cleanup_action.execute_orphan_storage_delete(approval, session)

        comment = session.added[0]
        assert "did NOT delete" in comment.body
        assert "no longer orphaned" in comment.body
        assert audited["result"] == "failed"
        assert audited["details"]["reason"] == "no longer orphaned"

    async def test_a_context_missing_the_candidate_raises_rather_than_returning_quietly(self, monkeypatch):
        """#17141: a silent return here left the approval reading APPROVED
        with nothing durable. Raising hands this to approval_execution's
        dispatcher, the sole owner of failure recording -- see
        test_a_malformed_context_is_recorded_by_the_dispatcher below for the
        durable trail this produces end to end."""

        async def _delete(*_args):
            raise AssertionError("delete_candidate must not be called without a candidate")

        monkeypatch.setattr(orphan_storage_cleanup_action, "delete_candidate", _delete)

        approval = _approval(action="orphan_storage_delete")
        session = _FakeSession()

        with pytest.raises(ValueError, match="missing provider/candidate_id"):
            await orphan_storage_cleanup_action.execute_orphan_storage_delete(approval, session)

        assert session.added == []
        assert session.commits == 0


class TestRegistration:
    async def test_register_wires_the_action_into_the_shared_dispatcher(self, monkeypatch):
        from services import approval_execution

        monkeypatch.setattr(approval_execution, "_REGISTRY", {})
        orphan_storage_cleanup_action.register()

        assert approval_execution._REGISTRY[orphan_storage_cleanup_action.ACTION] is (
            orphan_storage_cleanup_action.execute_orphan_storage_delete
        )

    async def test_dispatcher_actually_runs_it_end_to_end(self, monkeypatch):
        """The seam #17039's reopening found: approval_execution -> this module -> delete_candidate."""
        from services import approval_execution

        monkeypatch.setattr(approval_execution, "_REGISTRY", {})
        orphan_storage_cleanup_action.register()

        called = {}

        async def _delete(provider, candidate_id):
            called["provider"], called["candidate_id"] = provider, candidate_id
            return orphan_storage.DeleteResult(deleted=True)

        monkeypatch.setattr(orphan_storage_cleanup_action, "delete_candidate", _delete)
        monkeypatch.setattr(orphan_storage_cleanup_action, "audit_log", lambda *a, **k: _noop())

        approval = _approval(action="orphan_storage_delete", provider="code_source_clone", candidate_id="xyz")
        session = _FakeSession()

        await approval_execution.run_post_approval_actions(approval, session)

        assert called == {"provider": "code_source_clone", "candidate_id": "xyz"}
        assert session.commits == 1

    async def test_a_malformed_context_is_recorded_by_the_dispatcher_not_silently_dropped(self, monkeypatch):
        """#17141 AC3: the malformed-context path records through
        approval_execution's dispatcher, the same as any other handler
        failure -- this module has no recording logic of its own to keep in
        sync with it."""
        from services import approval_execution

        monkeypatch.setattr(approval_execution, "_REGISTRY", {})
        orphan_storage_cleanup_action.register()

        audited = {}

        async def _audit_log(operation, **kwargs):
            audited["operation"] = operation
            audited.update(kwargs)
            return True

        monkeypatch.setattr(approval_execution, "audit_log", _audit_log)

        # No provider/candidate_id in context -- the malformed shape.
        approval = _approval(action="orphan_storage_delete")
        session = _FakeSession()

        await approval_execution.run_post_approval_actions(approval, session)
        # No raise reaching here proves the dispatcher's own never-crash guarantee held.

        assert session.commits == 1
        comment = session.added[0]
        assert comment.approval_id == approval.id
        assert "orphan_storage_delete" in comment.body
        # safe_error_reason() falls back to the class name alone for anything
        # that isn't an OSError -- ValueError's own message text is not
        # trusted generically by the dispatcher, on the same "never leak a
        # path" principle, even though this particular message is safe.
        assert "ValueError" in comment.body

        assert audited["operation"] == "approval.post_action_failed"
        assert audited["result"] == "error"
        assert audited["resource"] == "orphan_storage_delete"
        assert audited["details"]["approval_id"] == str(approval.id)


async def _noop():
    return True
