# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A deleted or deactivated user's chat sessions go to a successor (#20029).

The shared ``UserService`` lifecycle is the real one; storage is stood in for: the database is in-memory
SQLite, the session files a dict, the Redis ownership key a dict. The audit sink is captured.
"""

from __future__ import annotations

import copy
import uuid
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from autobot_shared.db_session import POST_COMMIT_CALLBACKS
from autobot_shared.user_management.base_service import TenantContext
from autobot_shared.user_management.user_service import UserService as SharedUserService
from autobot_shared.user_management.user_service_errors import SessionReassignError
from llc.models.company_ceo import LLCCompanyCEO
from llc.models.enums import MembershipRole
from llc.models.membership import LLCCompanyMembership
from llc.models.reporting_line import LLCReportingLine
from llc.models.role_assignment import LLCRoleAssignment
from llc.tests import _e2e_harness as harness
from models.agent_org import AgentOrgNode
from services.audit.taxonomy import AuditAction
from user_management.models.base import Base
from user_management.models.user import User
from user_management.services import session_successor as ss

T0 = datetime(2026, 1, 1)
MESSAGES = [{"sender": "user", "text": "hello"}, {"sender": "bot", "text": "hi"}]


class FakeManager:
    """Session files as a dict: ``id -> chat_data``. ``update_session_metadata`` merges, as the real one does."""

    def __init__(self, sessions: dict[str, dict[str, Any]]) -> None:
        self.sessions = sessions
        self.fail_on: set[str] = set()

    def _get_chats_directory(self) -> str:
        return "/nonexistent-chats-dir"

    async def load_full_session(self, sid: str):
        return self.sessions.get(sid)

    async def update_session_metadata(self, sid: str, metadata: dict) -> bool:
        if sid in self.fail_on:
            return False
        self.sessions[sid]["metadata"].update(metadata)
        return True


class FakeValidator:
    def __init__(self) -> None:
        self.owners: dict[str, str] = {}
        self.forced: list[bool] = []

    async def set_session_owner(self, sid: str, username: str, force: bool = False, **_: Any) -> bool:
        self.owners[sid] = username
        self.forced.append(force)
        return True


@pytest.fixture(autouse=True)
def stores(monkeypatch):
    """Session listing by dict, and the audit sink captured."""
    events: list[dict] = []
    monkeypatch.setattr(ss, "emit_security", lambda action, actor, **kw: events.append({"action": action, **kw}))

    async def listdir(_fn, _dir):
        return [f"{sid}_chat.json" for sid in MANAGER.sessions]

    monkeypatch.setattr(ss, "run_in_chat_io_executor", listdir)
    return events


MANAGER = FakeManager({})


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")  # canonical: ignore py-adhoc-db-engine (test-local)
    tables = [
        User.__table__,
        LLCCompanyMembership.__table__,
        LLCReportingLine.__table__,
        LLCCompanyCEO.__table__,
        LLCRoleAssignment.__table__,
        AgentOrgNode.__table__,
    ]
    for table in tables:
        harness._scrub_pg_server_defaults(table)
        harness._clientside_timestamps(table)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    await engine.dispose()


async def _user(factory, name, *, admin=False, active=True, created=0):  # noqa: ANN001
    uid = uuid.uuid4()
    async with factory() as s:
        await s.execute(
            sa.insert(User.__table__).values(
                id=uid,
                email=f"{name}@x.test",
                username=name,
                is_active=active,
                is_verified=True,
                mfa_enabled=False,
                is_platform_admin=admin,
                preferences={},
                created_at=datetime(2026, 1, 1 + created),
            )
        )
        await s.commit()
    return uid


async def _member(factory, company, uid, role=MembershipRole.MEMBER, joined=0):  # noqa: ANN001
    async with factory() as s:
        s.add(
            LLCCompanyMembership(
                id=uuid.uuid4(),
                company_id=company,
                user_id=uid,
                role=role.value,
                created_at=datetime(2026, 1, 1 + joined),
            )
        )
        await s.commit()


def _session(owner, **meta):
    return {"name": "n", "messages": copy.deepcopy(MESSAGES), "metadata": {"owner": owner, "username": owner, **meta}}


@pytest.fixture
def mgr():
    MANAGER.sessions = {}
    MANAGER.fail_on = set()
    return MANAGER


async def _run(factory, user_id):  # noqa: ANN001
    validator = FakeValidator()
    async with factory() as db:
        out = await ss.reassign_user_sessions(db, user_id, "actor-1", MANAGER, validator)
    return out, validator


@pytest.mark.asyncio
async def test_sessions_go_to_the_resolved_successor_with_an_audit_record_and_content_untouched(
    factory, mgr, stores
):  # noqa: ANN001
    company = uuid.uuid4()
    leaving = await _user(factory, "leaving")
    owner = await _user(factory, "boss")
    await _member(factory, company, leaving)
    await _member(factory, company, owner, MembershipRole.OWNER)
    mgr.sessions["s1"] = _session("leaving")
    mgr.sessions["s2"] = _session("someone-else")
    before = copy.deepcopy(mgr.sessions["s1"]["messages"])

    out, validator = await _run(factory, leaving)

    assert out == {"sessions_reassigned": 1}
    assert mgr.sessions["s1"]["metadata"]["owner"] == "boss"
    assert mgr.sessions["s1"]["metadata"]["user_id"] == str(owner)
    assert mgr.sessions["s1"]["messages"] == before and mgr.sessions["s1"]["name"] == "n"
    assert mgr.sessions["s2"]["metadata"]["owner"] == "someone-else", "another user's session is not touched"
    assert validator.owners == {"s1": "boss"} and validator.forced == [True]
    [event] = stores
    assert event["action"] is AuditAction.SESSION_REASSIGN and event["outcome"] == "success"
    assert event["resource_id"] == "s1"
    assert event["metadata"] | {} == {
        "from_user_id": str(leaving),
        "to_user_id": str(owner),
        "source": ss.SOURCE_SUCCESSOR,
        "company_id": str(company),
    }


@pytest.mark.asyncio
async def test_a_company_session_prefers_its_own_company_over_an_earlier_membership(factory, mgr):  # noqa: ANN001
    first, second = uuid.uuid4(), uuid.uuid4()
    leaving = await _user(factory, "leaving")
    boss_first = await _user(factory, "boss_first")
    boss_second = await _user(factory, "boss_second")
    await _member(factory, first, leaving, joined=0)
    await _member(factory, second, leaving, joined=1)
    await _member(factory, first, boss_first, MembershipRole.OWNER)
    await _member(factory, second, boss_second, MembershipRole.OWNER)
    mgr.sessions["plain"] = _session("leaving")
    mgr.sessions["agent"] = _session("leaving", company_id=str(second))

    await _run(factory, leaving)

    assert mgr.sessions["plain"]["metadata"]["owner"] == "boss_first", "no company link: earliest membership"
    assert mgr.sessions["agent"]["metadata"]["owner"] == "boss_second", "its own company when the user belongs"


@pytest.mark.asyncio
async def test_a_user_in_no_company_falls_to_an_active_admin_with_the_source_recorded(
    factory, mgr, stores
):  # noqa: ANN001
    leaving = await _user(factory, "leaving", admin=True)  # an admin who is leaving is not their own fallback
    await _user(factory, "off_admin", admin=True, active=False)
    admin = await _user(factory, "root", admin=True, created=3)
    mgr.sessions["s1"] = _session("leaving")

    out, _ = await _run(factory, leaving)

    assert out == {"sessions_reassigned": 1} and mgr.sessions["s1"]["metadata"]["owner"] == "root"
    assert stores[0]["metadata"]["source"] == ss.SOURCE_ADMIN
    assert stores[0]["metadata"]["to_user_id"] == str(admin) and stores[0]["metadata"]["company_id"] is None


@pytest.mark.asyncio
async def test_no_successor_and_no_admin_refuses_and_writes_nothing(factory, mgr, stores):  # noqa: ANN001
    leaving = await _user(factory, "leaving")
    await _user(factory, "plain_member")
    mgr.sessions["s1"] = _session("leaving")
    mgr.sessions["s2"] = _session("leaving")

    with pytest.raises(SessionReassignError):
        await _run(factory, leaving)

    assert all(s["metadata"]["owner"] == "leaving" for s in mgr.sessions.values()), "nothing half-moved"
    [event] = stores
    assert event["outcome"] == "denied"


@pytest.mark.asyncio
async def test_a_user_with_no_sessions_needs_no_successor(factory, mgr):  # noqa: ANN001
    leaving = await _user(factory, "leaving")
    mgr.sessions["s1"] = _session("someone-else")
    out, _ = await _run(factory, leaving)
    assert out == {"sessions_reassigned": 0}


@pytest.mark.asyncio
async def test_a_failed_owner_write_aborts_and_is_audited_failed(factory, mgr, stores):  # noqa: ANN001
    leaving = await _user(factory, "leaving")
    await _user(factory, "root", admin=True)
    mgr.sessions["s1"] = _session("leaving")
    mgr.fail_on = {"s1"}

    with pytest.raises(SessionReassignError):
        await _run(factory, leaving)

    assert [e["outcome"] for e in stores] == ["failed"]


# ---- the lifecycle: delete and deactivate both reach the hook, and a refusal changes nothing ----


class _Service(SharedUserService):
    user_model = MagicMock()
    handover: Any = None

    async def reassign_sessions(self, user_id):
        self.handover(user_id)
        return {"sessions_reassigned": 3}


def _lifecycle(handover):
    user = SimpleNamespace(id=uuid.uuid4(), username="alice", is_active=True, deleted_at=None)
    session = MagicMock(flush=AsyncMock(), delete=AsyncMock())
    session.info = {POST_COMMIT_CALLBACKS: []}
    svc = _Service(session, TenantContext())
    svc.handover = handover
    svc.get_user = AsyncMock(return_value=user)
    svc._audit_log = AsyncMock()
    svc._queue_membership_epoch_bumps = AsyncMock()
    return svc, user


@pytest.mark.asyncio
@pytest.mark.parametrize("hard", [False, True])
async def test_delete_reassigns_before_the_row_goes_and_audits_the_count(hard):
    seen = []
    svc, user = _lifecycle(lambda uid: seen.append(("reassign", user.is_active, user.deleted_at)))
    await svc.delete_user(user.id, hard_delete=hard)
    assert seen == [("reassign", True, None)], "reassigned while the account was still intact"
    assert svc._audit_log.await_args.args[3]["sessions_reassigned"] == 3


@pytest.mark.asyncio
async def test_deactivate_reassigns_before_the_flip_and_audits_the_count():
    seen = []
    svc, user = _lifecycle(lambda uid: seen.append(user.is_active))
    await svc.deactivate_user(user.id)
    assert seen == [True] and user.is_active is False
    assert svc._audit_log.await_args.args[3]["sessions_reassigned"] == 3


@pytest.mark.asyncio
async def test_activate_reassigns_nothing():
    svc, user = _lifecycle(lambda uid: pytest.fail("reactivation must not move sessions"))
    user.is_active = False
    await svc.activate_user(user.id)
    assert user.is_active is True


@pytest.mark.asyncio
async def test_a_refusal_leaves_the_account_exactly_as_it_was():
    def refuse(_uid):
        raise SessionReassignError("no successor")

    svc, user = _lifecycle(refuse)
    with pytest.raises(SessionReassignError):
        await svc.delete_user(user.id, hard_delete=True)
    with pytest.raises(SessionReassignError):
        await svc.deactivate_user(user.id)
    assert user.is_active is True and user.deleted_at is None
    svc.session.delete.assert_not_awaited()
    svc._audit_log.assert_not_awaited()
