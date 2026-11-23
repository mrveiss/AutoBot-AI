# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The legacy CEO chat backfill as a proposer: file, approve, assign through the audited path (#16905, #17038).

The real classifier, proposer, approval gate service and dispatcher run on a real SQLite ``approvals`` table.
The chat store is a small in-memory double whose ``set_metadata_if_unset`` is the same compare-and-set the
route uses; the audit sink is a mock so the ``attempted`` / outcome rows can be read back.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.compiler import compiles

from models.approval import Approval, ApprovalComment, TaskApprovalLink
from services import approval_execution, chat_company_assignment_action, chat_company_proposals
from services.approval_gate_service import ApprovalGateService

pytestmark = pytest.mark.asyncio

_URL = "sqlite+aiosqlite:///:memory:"
CO_A = str(uuid.uuid4())
CO_B = str(uuid.uuid4())
DECIDER = uuid.uuid4()


@compiles(JSONB, "sqlite")
def _jsonb_as_json(element, compiler, **kw):
    return "JSON"


class _Chats:
    """The chat-store surface the proposer and the handler use."""

    def __init__(self, sessions):
        self.docs = {s["chatId"]: dict(s) for s in sessions}
        self.writes = []

    def _get_chats_directory(self):
        return "/nonexistent-chats-dir"

    async def list_sessions(self):
        return list(self.docs.values())

    async def get_session(self, session_id):
        return self.docs.get(session_id)

    async def get_session_company(self, session_id):
        return self.docs[session_id].get("companyId")

    async def set_metadata_if_unset(self, session_id, key, value):
        if self.docs[session_id].get("companyId"):
            return False
        self.docs[session_id]["companyId"] = value
        self.writes.append((session_id, key, value))
        return True


def _chats():
    return _Chats(
        [
            {"chatId": "legacy-1", "name": f"CEO · {CO_A}"},
            {"chatId": "legacy-2", "name": f"CEO · {CO_B}"},
            {"chatId": "ordinary", "name": "holiday plans"},
            {"chatId": "fake-ceo", "name": f"CEO · {uuid.uuid4()}"},
            {"chatId": "tagged", "name": f"CEO · {CO_A}", "companyId": CO_A},
        ]
    )


@pytest.fixture
async def db():
    engine = create_async_engine(_URL)  # canonical: ignore py-adhoc-db-engine (in-memory test store)
    async with engine.begin() as conn:
        for model in (Approval, ApprovalComment, TaskApprovalLink):
            await conn.run_sync(model.__table__.create)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
    await engine.dispose()


@pytest.fixture
def audit(monkeypatch, db):
    sink = AsyncMock(return_value=True)
    monkeypatch.setattr(approval_execution, "_REGISTRY", {})
    monkeypatch.setattr(approval_execution, "_PROPOSERS", {})
    monkeypatch.setattr(ApprovalGateService, "_notify", AsyncMock())
    monkeypatch.setattr(approval_execution, "audit_log", AsyncMock(return_value=True))
    monkeypatch.setattr("security.session_share_audit.audit_log", sink)
    monkeypatch.setattr(
        "chat_history.session_scope_backfill.load_known_company_ids", AsyncMock(return_value={CO_A, CO_B})
    )
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=db)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr("user_management.database.get_async_session_factory", lambda: factory)
    monkeypatch.setattr("security.session_company.company_exists", AsyncMock(return_value=True))
    monkeypatch.setattr("api.session_events.publish_session_updated", AsyncMock())
    chat_company_assignment_action.register_chat_company_assignment_action()
    return sink


@pytest.fixture
def chats(monkeypatch):
    store = _chats()
    monkeypatch.setattr("chat_history.ChatHistoryManager", lambda: store)
    return store


async def _approve(db, approval_id):
    gate = ApprovalGateService(db)
    approval = await gate.approve(uuid.UUID(approval_id), decided_by="alice", author_type="human", decider_id=DECIDER)
    return approval


async def _comments(db, approval_id):
    rows = await db.execute(select(ApprovalComment.body).where(ApprovalComment.approval_id == uuid.UUID(approval_id)))
    return list(rows.scalars().all())


async def test_files_one_proposal_per_legacy_ceo_chat_and_none_for_the_rest(db, audit, chats):
    result = await chat_company_proposals.propose_company_assignments(chats)
    assert result["scanned"] == 5 and result["taggable"] == 2 and len(result["proposed"]) == 2
    assert result["already_tagged"] == 1 and result["unclassified"] == 2
    rows = (await db.execute(select(Approval))).scalars().all()
    assert {(r.context["session_id"], r.context["company_id"]) for r in rows} == {
        ("legacy-1", CO_A),
        ("legacy-2", CO_B),
    }
    assert {r.status for r in rows} == {"pending"}


async def test_nothing_is_written_before_approval(db, audit, chats):
    await chat_company_proposals.propose_company_assignments(chats)
    assert chats.writes == []
    assert audit.await_count == 0
    assert all("companyId" not in chats.docs[s] for s in ("legacy-1", "legacy-2"))


async def test_a_rerun_does_not_duplicate_proposals(db, audit, chats):
    first = await chat_company_proposals.propose_company_assignments(chats)
    second = await chat_company_proposals.propose_company_assignments(chats)
    assert len(first["proposed"]) == 2 and second["proposed"] == [] and second["already_proposed"] == 2


async def test_approval_assigns_through_the_audited_path(db, audit, chats):
    created = (await chat_company_proposals.propose_company_assignments(chats))["proposed"]
    approved = await _approve(db, created[0])
    assert approved.status == "approved"
    assert len(chats.writes) == 1
    session_id, key, value = chats.writes[0]
    assert key == "company_id" and chats.docs[session_id]["companyId"] == value
    results = [c.args[1] for c in audit.await_args_list]
    assert results == ["attempted", "success"]
    attempted = audit.await_args_list[0]
    assert attempted.args[0] == "session.company_assign" and attempted.kwargs["durable"] is True
    assert attempted.kwargs["user_id"] == str(DECIDER) and attempted.kwargs["details"]["username"] == "alice"
    assert attempted.kwargs["details"]["company_id"] == value
    other = {"legacy-1", "legacy-2"} - {session_id}
    assert all("companyId" not in chats.docs[s] for s in other)


async def test_rejection_is_a_no_op_and_stays_rejected_on_rerun(db, audit, chats):
    created = (await chat_company_proposals.propose_company_assignments(chats))["proposed"]
    await ApprovalGateService(db).reject(uuid.UUID(created[0]), decided_by="alice", author_type="human")
    assert chats.writes == [] and audit.await_count == 0
    again = await chat_company_proposals.propose_company_assignments(chats)
    assert again["proposed"] == []  # a denial is a person's decision and stays one


async def test_a_chat_tagged_in_the_meantime_is_stale_and_unchanged(db, audit, chats):
    created = (await chat_company_proposals.propose_company_assignments(chats))["proposed"]
    chats.docs["legacy-1"]["companyId"] = CO_B  # assigned by a person, e.g. through the Unassigned group
    rows = (await db.execute(select(Approval))).scalars().all()
    target = next(str(r.id) for r in rows if r.context["session_id"] == "legacy-1")
    await _approve(db, target)
    assert chats.docs["legacy-1"]["companyId"] == CO_B and chats.writes == []
    assert [c.args[1] for c in audit.await_args_list] == ["failed"]  # one durable failed row, no attempted row
    failed = audit.await_args_list[0]
    assert failed.args[0] == "session.company_assign" and failed.kwargs["durable"] is True
    assert failed.kwargs["details"]["reason"] == "the chat already has a company"
    assert failed.kwargs["user_id"] == str(DECIDER) and failed.kwargs["resource"] == "legacy-1"
    assert any("Stale" in body for body in await _comments(db, target))
    assert created  # the other proposal is untouched and still pending


async def test_a_lost_race_at_write_time_is_recorded_failed_and_stale(db, audit, chats, monkeypatch):
    created = (await chat_company_proposals.propose_company_assignments(chats))["proposed"]
    monkeypatch.setattr(chat_company_assignment_action, "_stale_reason", AsyncMock(return_value=None))
    chats.docs["legacy-1"]["companyId"] = CO_B  # lands between the staleness check and the compare-and-set
    rows = (await db.execute(select(Approval))).scalars().all()
    target = next(str(r.id) for r in rows if r.context["session_id"] == "legacy-1")
    await _approve(db, target)
    assert [c.args[1] for c in audit.await_args_list] == ["attempted", "failed"]
    assert chats.writes == [] and chats.docs["legacy-1"]["companyId"] == CO_B
    assert created


async def test_the_action_is_server_only_and_admin_only(audit):
    assert approval_execution.is_server_only_action(chat_company_assignment_action.ACTION)
    assert approval_execution.action_needs_elevated_approver(chat_company_assignment_action.ACTION)
