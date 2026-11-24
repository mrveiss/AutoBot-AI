# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#22033: stale code-sync files are removed only by an approved proposal, with a durable audit trail.

Approve and reject go through the real gate service; only the SLM call and the audit write are faked.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, patch

import pytest

from autobot_shared.slm_stale_file_actions import STALE_SYNC_FILES_CLEANUP
from models.approval import ApprovalStatus
from services import approval_execution
from services import slm_stale_file_texts as texts
from services import slm_stale_sync_files_action as action
from services.approval_gate_service import ApprovalGateService
from services.audit.taxonomy import AuditAction
from testkit.fake_async_session import FakeAsyncSession, FakeResult

ACTION = STALE_SYNC_FILES_CLEANUP.name
_DECIDER = uuid.UUID("00000000-0000-4000-8000-000000000032")
_APPROVAL_ID = uuid.UUID("00000000-0000-4000-8000-000000000033")
_REPORT = {"results": [{"path": "a.py", "result": "removed"}, {"path": "b.py", "result": "changed"}]}


def _approval(decider: uuid.UUID | None = _DECIDER) -> SimpleNamespace:
    approval = SimpleNamespace(
        id=_APPROVAL_ID,
        decided_by_user="owner",
        status=ApprovalStatus.APPROVED.value,
        context={"action": ACTION, "node_id": "node-a", "credential_kind": "stale_sync_files"},
    )
    approval_execution.set_verified_decider(approval, decider)
    return approval


def test_the_audit_name_is_a_taxonomy_member() -> None:
    assert AuditAction.CODE_SYNC_STALE_FILES_CLEANUP.value == "code_sync.stale_files.cleanup"


async def test_approval_removes_through_the_slm_and_audits_intent_then_completion() -> None:
    session = FakeAsyncSession()
    with (
        patch.object(action, "_remove_in_slm", AsyncMock(return_value=_REPORT)) as remove,
        patch.object(action, "audit_log", AsyncMock(return_value=True)) as audit,
    ):
        await action.execute_stale_sync_files_cleanup(_approval(), session)
    remove.assert_awaited_once_with("node-a", str(_APPROVAL_ID))
    phases = [call.kwargs["details"]["phase"] for call in audit.await_args_list]
    assert phases == ["intent", "completion"] and all(c.kwargs["durable"] is True for c in audit.await_args_list)
    assert audit.await_args_list[-1].kwargs["details"]["removed"] == 1
    assert "1 removed" in session.added[-1].body and "1 changed" in session.added[-1].body


async def test_no_committed_intent_entry_means_nothing_is_removed() -> None:
    with (
        patch.object(action, "_remove_in_slm", AsyncMock()) as remove,
        patch.object(action, "audit_log", AsyncMock(return_value=False)),
        pytest.raises(ValueError),
    ):
        await action.execute_stale_sync_files_cleanup(_approval(), FakeAsyncSession())
    remove.assert_not_awaited()


async def test_no_verified_human_decider_removes_nothing() -> None:
    with (
        patch.object(action, "_remove_in_slm", AsyncMock()) as remove,
        patch.object(action, "audit_log", AsyncMock()) as audit,
        pytest.raises(ValueError),
    ):
        await action.execute_stale_sync_files_cleanup(_approval(decider=None), FakeAsyncSession())
    remove.assert_not_awaited()
    assert audit.await_args.kwargs["result"] == "denied"


async def test_a_failing_slm_call_is_audited_failed_and_raised() -> None:
    with (
        patch.object(action, "_remove_in_slm", AsyncMock(side_effect=RuntimeError("down"))),
        patch.object(action, "audit_log", AsyncMock(return_value=True)) as audit,
        pytest.raises(RuntimeError),
    ):
        await action.execute_stale_sync_files_cleanup(_approval(), FakeAsyncSession())
    assert audit.await_args.kwargs["result"] == "failed"


async def test_a_failed_comment_commit_cannot_lose_the_completion_entry() -> None:
    session = FakeAsyncSession()
    session.commit = AsyncMock(side_effect=RuntimeError("db down"))
    with (
        patch.object(action, "_remove_in_slm", AsyncMock(return_value=_REPORT)) as remove,
        patch.object(action, "audit_log", AsyncMock(return_value=True)) as audit,
        pytest.raises(RuntimeError),
    ):
        await action.execute_stale_sync_files_cleanup(_approval(), session)
    remove.assert_awaited_once()  # the comment's failure never asks the SLM again
    completion = audit.await_args_list[-1].kwargs
    assert completion["details"]["phase"] == "completion" and completion["details"]["removed"] == 1


async def test_an_unwritten_completion_entry_is_said_on_the_approval_and_raised() -> None:
    session = FakeAsyncSession()
    with (
        patch.object(action, "_remove_in_slm", AsyncMock(return_value=_REPORT)) as remove,
        patch.object(action, "audit_log", AsyncMock(side_effect=[True, False])),
        pytest.raises(ValueError, match="completion audit entry"),
    ):
        await action.execute_stale_sync_files_cleanup(_approval(), session)
    remove.assert_awaited_once()
    assert "1 removed" in session.added[-2].body and "could not be written" in session.added[-1].body


@pytest.mark.parametrize(("result", "outcome"), [("failed", "failed"), ("changed", "success")])
async def test_a_failed_unlink_makes_the_completion_entry_failed(result: str, outcome: str) -> None:
    report = {"results": [{"path": "a.py", "result": "removed"}, {"path": "b.py", "result": result}]}
    with (
        patch.object(action, "_remove_in_slm", AsyncMock(return_value=report)),
        patch.object(action, "audit_log", AsyncMock(return_value=True)) as audit,
    ):
        await action.execute_stale_sync_files_cleanup(_approval(), FakeAsyncSession())
    assert audit.await_args.kwargs["result"] == outcome and audit.await_args.kwargs["details"]["removed"] == 1


async def _decide(method: str) -> AsyncMock:
    """Approve or reject through the real gate service; returns the SLM removal mock."""
    action.register_stale_sync_files_action()
    approval = _approval()
    service = ApprovalGateService(FakeAsyncSession(results=[FakeResult([approval])]))
    with (
        patch.object(ApprovalGateService, "_transition", AsyncMock(return_value=approval)),
        patch.object(action, "_remove_in_slm", AsyncMock(return_value=_REPORT)) as remove,
        patch.object(action, "audit_log", AsyncMock(return_value=True)),
    ):
        kwargs = {"decider_id": _DECIDER} if method == "approve" else {}
        await getattr(service, method)(approval.id, "owner", author_type="user", **kwargs)
    return remove


async def test_approving_removes_and_rejecting_changes_nothing() -> None:
    (await _decide("approve")).assert_awaited_once_with("node-a", ANY)
    (await _decide("reject")).assert_not_awaited()


def test_the_action_is_server_only_admin_only_with_the_proposer_named() -> None:
    action.register_stale_sync_files_action()
    assert approval_execution.is_server_only_action(ACTION)
    assert approval_execution.action_needs_elevated_approver(ACTION)
    assert approval_execution.registered_action_proposers()[ACTION] == action.PROPOSED_BY


def test_the_description_lists_each_file_with_path_size_and_age() -> None:
    now = datetime(2026, 11, 24, tzinfo=timezone.utc)
    files = [
        {"path": "api/x.py", "size_bytes": 2048, "modified_at": datetime(2026, 11, 14, tzinfo=timezone.utc)},
        {"path": "y.py", "size_bytes": 5, "modified_at": "2026-11-23T00:00:00+00:00"},
    ]
    title, description = texts.stale_files_proposal_text("node-a", "/opt/node-root", files, 2, now)
    lines = description.splitlines()
    assert "node-a" in title and "/opt/node-root" in title
    assert lines[-2].startswith("/opt/node-root/api/x.py  2.0 KiB  10 days old")
    assert lines[-1].startswith("/opt/node-root/y.py  5 B  1 days old")


def test_a_capped_proposal_says_how_many_more_follow_and_a_complete_one_does_not() -> None:
    one = [{"path": "a.py", "size_bytes": 1, "modified_at": "2026-11-23T00:00:00+00:00"}]
    assert "4 more are proposed" in texts.stale_files_proposal_text("n", "/t", one, 5)[1]
    assert "more are proposed" not in texts.stale_files_proposal_text("n", "/t", one, 1)[1]
