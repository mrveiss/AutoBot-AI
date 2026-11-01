# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One audit path: ``record`` fails as ``ActivityRecordError`` and publishes only after the commit (#20101).

Every Company OS service reaches the activity table through ``LLCActivityLogService.record``, about
forty call sites of which call it directly. The wrapping therefore lives in ``record`` itself:

- a failure of the write is an ``ActivityRecordError``, never a bare ``ValueError`` a route would read as
  the caller's error; a malformed ``actor_id`` is still that ``ValueError`` (it is the caller's input);
- ``audit`` does not wrap a second time, and rejects a bad actor before any write;
- the live event goes out when the caller's transaction commits, and not at all for a rollback;
- a handoff audits before it drops the checkout key and notifies.

Not shown here: Postgres (every database test is SQLite) and ``/ws/live`` delivery.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import textwrap
import uuid
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.activity import ActorType
from llc.models.enums import ActivityEventType, AssigneeType, WorkItemStatus
from llc.services import activity_log as activity_log_module
from llc.services.activity_log import LLCActivityLogService
from llc.services.actor import ActivityRecordError, audit
from llc.services.handoff import HandoffService
from llc.tests import _e2e_harness as harness
from testkit.fake_async_session import FakeAsyncSession

COMPANY, ENTITY, USER = (str(uuid.uuid4()) for _ in range(3))


def _entry(**over):  # noqa: ANN202
    """The kwargs for one write except who acted: every call below names its actor itself (#13999)."""
    base = dict(
        company_id=COMPANY,
        event_type=ActivityEventType.WORK_ITEM_CREATED,
        entity_type="work_item",
        entity_id=ENTITY,
    )
    return {**base, **over}


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    await harness.create_loop_schema(engine)
    factory = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest.fixture
def delivered():  # noqa: ANN201
    with patch.object(LLCActivityLogService, "_deliver", AsyncMock()) as spy:
        yield spy


def _bulk_entry() -> dict:
    return _entry(entity_id=str(uuid.uuid4()), actor_type=ActorType.SYSTEM, actor_id=None)


async def _drain_publishes() -> None:
    await asyncio.sleep(0)
    if activity_log_module._publish_tasks:
        await asyncio.gather(*activity_log_module._publish_tasks)


# --- the failure of the write ---------------------------------------------------------------


@pytest.mark.parametrize("bad", [{"company_id": "nope"}, {"entity_id": "nope"}])
async def test_a_bad_company_or_entity_id_is_an_activity_record_error_not_a_value_error(session, bad):  # noqa: ANN001
    with pytest.raises(ActivityRecordError) as caught:
        await LLCActivityLogService().record(session, actor_type=ActorType.SYSTEM, actor_id=None, **_entry(**bad))
    assert not isinstance(caught.value, ValueError)
    assert isinstance(caught.value.__cause__, ValueError)


async def test_a_failed_flush_is_an_activity_record_error(session):  # noqa: ANN001
    with patch.object(session, "flush", AsyncMock(side_effect=RuntimeError("table locked"))):
        with pytest.raises(ActivityRecordError, match="table locked"):
            await LLCActivityLogService().record(session, actor_type=ActorType.SYSTEM, actor_id=None, **_entry())


async def test_a_bad_actor_id_stays_the_callers_value_error_and_writes_nothing(session):  # noqa: ANN001
    with pytest.raises(ValueError, match="actor_id") as caught:
        await LLCActivityLogService().record(session, actor_type=ActorType.USER, actor_id="nope", **_entry())
    assert not isinstance(caught.value, ActivityRecordError)
    assert not session.new


async def test_audit_does_not_wrap_the_error_record_already_wrapped(session):  # noqa: ANN001
    with pytest.raises(ActivityRecordError) as caught:
        await audit(
            LLCActivityLogService(), session, actor_type=ActorType.SYSTEM, actor_id=None, **_entry(entity_id="nope")
        )
    assert str(caught.value).count("activity record failed") == 1
    assert isinstance(caught.value.__cause__, ValueError)


async def test_audit_rejects_a_bad_actor_id_before_it_calls_the_log():
    log = MagicMock(record=AsyncMock())
    with pytest.raises(ValueError, match="actor_id"):
        await audit(log, MagicMock(), actor_type=ActorType.USER, actor_id="nope", **_entry())
    log.record.assert_not_called()


async def test_audit_still_wraps_a_log_that_does_not_wrap_itself():
    log = MagicMock(record=AsyncMock(side_effect=ValueError("Invalid entity_id UUID")))
    with pytest.raises(ActivityRecordError, match="Invalid entity_id"):
        await audit(log, MagicMock(), actor_type=ActorType.SYSTEM, actor_id=None, **_entry())


# --- the guard: the wrapping stays in record, and no second path to the table exists ---------

_ACTIVITY_LOG_PY = inspect.getsource(activity_log_module)


def _record_wraps(source: str) -> bool:
    """True when ``record`` has a ``try`` whose handler raises ``ActivityRecordError``."""
    for fn in ast.walk(ast.parse(source)):
        if isinstance(fn, ast.AsyncFunctionDef) and fn.name == "record":
            return any(
                isinstance(h, ast.ExceptHandler) and "ActivityRecordError" in ast.unparse(h)
                for t in ast.walk(fn)
                if isinstance(t, ast.Try)
                for h in t.handlers
            )
    return False


def _builds_rows_elsewhere(source: str) -> bool:
    """True for code that constructs an ``LLCActivityLog`` row itself instead of calling ``record``."""
    tree = ast.parse(source)
    constructs = any(isinstance(n, ast.Call) and ast.unparse(n.func).endswith("LLCActivityLog") for n in ast.walk(tree))
    inserts = any(
        isinstance(n, ast.Call)
        and ast.unparse(n.func).split(".")[-1] == "insert"
        and n.args
        and ast.unparse(n.args[0]).endswith(("LLCActivityLog", "LLCActivityLog.__table__"))
        for n in ast.walk(tree)
    )
    return constructs or inserts or "INTO llc_activity_log" in source


def test_record_wraps_its_own_failures():
    assert _record_wraps(_ACTIVITY_LOG_PY)


def test_control_a_record_without_the_wrapping_is_reported():
    bare = "class S:\n    async def record(self, s):\n        s.add(1)\n        await s.flush()\n"
    wrapped = textwrap.dedent("""
        class S:
            async def record(self, s):
                try:
                    await s.flush()
                except Exception as exc:
                    raise ActivityRecordError('x') from exc
        """)
    assert not _record_wraps(bare) and _record_wraps(wrapped)


def test_no_module_but_the_log_service_builds_an_activity_row():
    from pathlib import Path

    root = Path(activity_log_module.__file__).resolve().parents[1]
    skip = {root / "services" / "activity_log.py"}
    scanned = [
        p
        for p in sorted(root.rglob("*.py"))
        if p not in skip and "tests" not in p.relative_to(root).parts and not p.name.endswith("_test.py")
    ]
    assert len(scanned) > 100, f"only {len(scanned)} files scanned; the walk is broken"
    offenders = [
        p.relative_to(root).as_posix() for p in scanned if _builds_rows_elsewhere(p.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"a second path to the activity table, bypassing record (#20101): {offenders}"


def test_control_a_second_path_to_the_table_is_reported():
    assert _builds_rows_elsewhere("def f(s):\n    s.add(LLCActivityLog(company_id=1))\n")
    assert _builds_rows_elsewhere("def f(s):\n    s.add(activity.LLCActivityLog(company_id=1))\n")
    assert _builds_rows_elsewhere("def f(s):\n    return sa.insert(LLCActivityLog).values(a=1)\n")
    assert _builds_rows_elsewhere("Q = 'INSERT INTO llc_activity_log (id) VALUES (1)'\n")
    assert not _builds_rows_elsewhere("def f(s):\n    return s.query(LLCActivityLog)\n")


# --- the live event: after the commit only ---------------------------------------------------


async def test_a_rolled_back_write_publishes_nothing(session, delivered):  # noqa: ANN001
    await LLCActivityLogService().record(session, actor_type=ActorType.SYSTEM, actor_id=None, **_entry())
    await session.rollback()
    await _drain_publishes()
    delivered.assert_not_called()


async def test_a_committed_write_publishes_once_and_not_before_the_commit(session, delivered):  # noqa: ANN001
    row = await LLCActivityLogService().record(session, actor_type=ActorType.SYSTEM, actor_id=None, **_entry())
    await _drain_publishes()
    delivered.assert_not_called()
    await session.commit()
    await _drain_publishes()
    delivered.assert_awaited_once()
    company_id, payload = delivered.await_args.args
    assert (company_id, payload["id"]) == (COMPANY, str(row.id))


async def test_record_bulk_publishes_every_row_on_commit_and_none_on_rollback(session, delivered):  # noqa: ANN001
    service = LLCActivityLogService()
    await service.record_bulk(session, [_bulk_entry() for _ in range(2)])
    await session.rollback()
    await _drain_publishes()
    delivered.assert_not_called()
    await service.record_bulk(session, [_bulk_entry() for _ in range(2)])
    await session.commit()
    await _drain_publishes()
    assert delivered.await_count == 2


async def test_a_rolled_back_savepoint_publishes_nothing_for_its_row(session, delivered):  # noqa: ANN001
    service = LLCActivityLogService()
    kept = await service.record(session, actor_type=ActorType.SYSTEM, actor_id=None, **_entry())
    with pytest.raises(RuntimeError):
        async with session.begin_nested():
            await service.record(
                session, actor_type=ActorType.SYSTEM, actor_id=None, **_entry(entity_id=str(uuid.uuid4()))
            )
            raise RuntimeError("undo the savepoint")
    await session.commit()
    await _drain_publishes()
    delivered.assert_awaited_once()
    assert delivered.await_args.args[1]["id"] == str(kept.id)


async def test_a_session_with_no_commit_to_follow_publishes_at_once(delivered):  # noqa: ANN001
    fake = FakeAsyncSession(assign_ids=uuid.uuid4)
    await LLCActivityLogService().record(fake, actor_type=ActorType.SYSTEM, actor_id=None, **_entry())
    delivered.assert_awaited_once()


# --- handoff: audit before the effects nothing can undo ---------------------------------------


def _redis() -> AsyncMock:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    return redis


def _service_whose_audit_fails() -> HandoffService:
    service = HandoffService()
    service.activity_log.record = AsyncMock(side_effect=ActivityRecordError("audit store down"))
    return service


def _a2h_session(agent_id: str) -> AsyncMock:
    item = MagicMock(
        assignee_agent_id=uuid.UUID(agent_id), project_id=None, title="t", description="d", version=1, identifier="W-1"
    )
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=item)))
    return session


async def test_a_failed_audit_leaves_the_key_and_sends_nothing_on_agent_to_human():
    agent, redis, service = str(uuid.uuid4()), _redis(), _service_whose_audit_fails()
    with patch("llc.services.handoff.get_async_redis_client", AsyncMock(return_value=redis)):
        with pytest.raises(ActivityRecordError):
            await service.agent_to_human(_a2h_session(agent), str(uuid.uuid4()), agent, USER, COMPANY)
    redis.delete.assert_not_called()
    redis.publish.assert_not_called()
    assert not service._background_tasks


async def test_a_failed_audit_leaves_the_key_and_sends_nothing_on_human_to_agent():
    redis, service = _redis(), _service_whose_audit_fails()
    item = MagicMock(assignee_user_id=uuid.UUID(USER), assignee_type=AssigneeType.USER.value, project_id=None)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=item)))
    kb = MagicMock(ingest_notes=AsyncMock(return_value="notes:1"))
    with (
        patch("llc.services.handoff.get_async_redis_client", AsyncMock(return_value=redis)),
        patch("llc.services.handoff.wake_for_item_changes", AsyncMock()),
        patch("llc.kb.work_item_kb.WorkItemKB", return_value=kb),
    ):
        with pytest.raises(ActivityRecordError):
            await service.human_to_agent(
                session,
                work_item_id=str(uuid.uuid4()),
                target_agent_id=str(uuid.uuid4()),
                user_id=USER,
                company_id=COMPANY,
                human_notes="n",
            )
    redis.delete.assert_not_called()
    redis.publish.assert_not_called()
    assert item.status != WorkItemStatus.IN_REVIEW
