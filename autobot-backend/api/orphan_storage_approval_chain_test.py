# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""propose -> approve -> delete, end to end, through the production path (#17315).

#17038's rule is a chain: an agent proposes, a human approves through an
always-available queue, and only then is anything deleted. Every link had its
own test and the chain had none -- which is how it shipped with no proposer at
all, an executor that nothing could reach, and unit tests that all passed.

So this test never registers a handler itself and never builds a context by
hand: it calls the real proposer, hands the approval it produced to the real
``ApprovalGateService.approve()``, and lets the real dispatcher route it. The
only fakes are the database session and the detector at the far end, which
records the delete instead of performing one. Break any link -- the proposer's
context shape, the registration, the dispatch key -- and this fails.
"""

import uuid

import pytest

import api.admin_orphan_storage as admin_route
from api.schemas_orphan_storage import OrphanStorageDeletionRequest
from models.approval import Approval, ApprovalComment
from services import approval_execution, orphan_storage, orphan_storage_cleanup_action
from services.approval_gate_service import ApprovalGateService

pytestmark = pytest.mark.asyncio

_ADMIN = {"username": "admin", "role": "admin", "user_id": "admin-1"}


class _FakeSession:
    """add/flush/commit/refresh, plus the one select ``_get_or_raise`` runs."""

    def __init__(self):
        self.added = []
        self.approval = None

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        if isinstance(obj, Approval):
            self.approval = obj
        self.added.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        return None

    async def refresh(self, obj):
        return None

    async def execute(self, _stmt):
        approval = self.approval

        class _Result:
            def scalar_one_or_none(self):
                return approval

        return _Result()


@pytest.fixture
def chain(monkeypatch):
    """The real executor registered against a detector that records deletes."""
    monkeypatch.setattr(approval_execution, "_REGISTRY", {})
    monkeypatch.setattr(approval_execution, "_PROPOSERS", {})
    monkeypatch.setattr(orphan_storage, "_REGISTRY", {})
    monkeypatch.setattr(ApprovalGateService, "_notify", lambda self, event, approval: _noop())

    deleted: list = []
    audited: list = []

    async def _list():
        return []

    async def _delete(candidate_id: str):
        deleted.append(candidate_id)
        return orphan_storage.DeleteResult(deleted=True)

    orphan_storage.register_detector(
        orphan_storage.OrphanDetector(provider="code_source_clone", list_candidates=_list, delete=_delete)
    )

    async def _audit_log(operation, **kwargs):
        audited.append({"operation": operation, **kwargs})
        return True

    monkeypatch.setattr(orphan_storage_cleanup_action, "audit_log", _audit_log)
    monkeypatch.setattr(approval_execution, "audit_log", _audit_log)

    # Exactly what importing the admin router does at app startup.
    orphan_storage_cleanup_action.register()
    return {"deleted": deleted, "audited": audited}


async def _noop():
    return None


async def test_proposing_then_approving_deletes_the_named_candidate(chain):
    session = _FakeSession()

    proposal = await admin_route.propose_orphan_storage_deletion(
        OrphanStorageDeletionRequest(provider="code_source_clone", candidate_id="abc"),
        current_user=_ADMIN,
        session=session,
    )

    assert proposal.status == "pending"
    assert chain["deleted"] == [], "nothing may be deleted while a human has not decided"

    await ApprovalGateService(session).approve(
        uuid.UUID(proposal.approval_id),
        decided_by="alice",
        author_type="human",
        comment=None,
    )

    assert chain["deleted"] == ["abc"], "approving must reach the registered executor"
    assert session.approval.status == "approved"
    assert session.approval.decided_by_user == "alice"

    comments = [o for o in session.added if isinstance(o, ApprovalComment)]
    assert any(
        "deleted" in c.body and "abc" in c.body for c in comments
    ), "the outcome lands on the approval itself, in the inbox that showed the proposal"
    assert [a["operation"] for a in chain["audited"]] == ["orphan_storage.delete"]
    assert chain["audited"][0]["result"] == "success"


async def test_rejecting_deletes_nothing(chain):
    """The other half of the rule: a human saying no is the end of it."""
    session = _FakeSession()

    proposal = await admin_route.propose_orphan_storage_deletion(
        OrphanStorageDeletionRequest(provider="code_source_clone", candidate_id="abc"),
        current_user=_ADMIN,
        session=session,
    )
    await ApprovalGateService(session).reject(
        uuid.UUID(proposal.approval_id),
        decided_by="alice",
        author_type="human",
        comment=None,
    )

    assert session.approval.status == "rejected"
    assert chain["deleted"] == []
    assert chain["audited"] == []
