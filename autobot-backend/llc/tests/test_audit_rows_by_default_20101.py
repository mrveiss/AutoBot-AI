# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A service built the way production builds it writes its audit row (#20101).

Before, ``LLCServiceBase`` defaulted ``activity_log`` to ``None`` and each service guarded its
write with ``if self.activity_log``, so ``GoalService()`` (what every route and tool builds)
recorded nothing and nothing failed. Each test below builds the service with NO log, the way
the routes do, runs the action against a real (in-memory) database and reads the row back.
Nothing here injects a log, because a test that supplies the collaborator no caller supplies
proves the configuration that does not occur (#15931).
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.activity import LLCActivityLog
from llc.models.enums import WorkItemRelationType, WorkItemType
from llc.models.goal import GoalLevel
from llc.models.label import LLCLabel
from llc.models.secret import LLCSecret
from llc.services.actor import ActivityRecordError
from llc.services.goal import GoalService
from llc.services.handoff import HandoffService
from llc.services.label_service import LLCLabelService
from llc.services.portability import PortabilityService
from llc.services.reporting_line import Holder, ReportingLineService
from llc.services.secret import SecretService
from llc.services.work_item_relations import WorkItemRelationService
from llc.services.work_item_service import WorkItemService
from llc.services.workflow import WorkflowService
from llc.tests import _e2e_harness as harness
from models.workflow import Workflow
from user_management.models.base import Base

pytestmark = pytest.mark.asyncio

_EXPORT_ARTIFACTS_DDL = (
    "CREATE TABLE llc_export_artifacts (id CHAR(32) PRIMARY KEY, company_id CHAR(32) NOT NULL, "
    "type VARCHAR(32) NOT NULL DEFAULT 'export_artifact', export_kind VARCHAR(32) NOT NULL, "
    "schema_version VARCHAR(16) NOT NULL DEFAULT '1.0', storage_path TEXT NOT NULL, "
    "created_by VARCHAR(255) NOT NULL DEFAULT 'system', created_at DATETIME DEFAULT CURRENT_TIMESTAMP, "
    "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
)
SECRET_VALUE = "s3cr3t-value-that-must-never-reach-an-audit-row"  # pragma: allowlist secret
USER = str(uuid.uuid4())


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):  # noqa: ANN001, ANN202
    """No Redis: the pub/sub fan-out is best-effort and is not what these tests are about."""
    monkeypatch.setenv("LLC_SECRET_MASTER_KEY", "test-master-key-20101")
    no_redis = AsyncMock(return_value=None)
    monkeypatch.setattr("llc.services.activity_log.get_async_redis_client", no_redis)
    monkeypatch.setattr("llc.services.work_item_service.get_async_redis_client", no_redis)
    with patch("live_event_manager.publish_live_event", AsyncMock()):
        yield


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    await harness.create_loop_schema(engine)
    extra = [LLCSecret.__table__, LLCLabel.__table__, Workflow.__table__]
    for table in extra:
        harness._scrub_pg_server_defaults(table)
        harness._clientside_timestamps(table)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=extra))
        # The model declares its company index twice (column and __table_args__), which SQLite refuses.
        await conn.execute(sa.text(_EXPORT_ARTIFACTS_DDL))
    factory = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    async with factory() as s:
        yield s
    await engine.dispose()


async def _rows(session: AsyncSession) -> list[LLCActivityLog]:
    return list((await session.execute(sa.select(LLCActivityLog).order_by(LLCActivityLog.occurred_at))).scalars())


async def _item(session: AsyncSession, company: str, title: str):  # noqa: ANN202
    item = await WorkItemService().create(session, company_id=company, type=WorkItemType.TASK, title=title)
    await session.commit()
    return item


async def test_creating_a_goal_writes_a_row_naming_the_user(session):  # noqa: ANN001
    company = str(uuid.uuid4())
    goal = await GoalService().create(session, company, "Ship", GoalLevel.VISION, actor_user_id=USER)
    await session.commit()
    (row,) = await _rows(session)
    assert (row.action, row.entity_type, row.entity_id) == ("goal.created", "llc_goal", goal.id)
    assert (row.actor_type, str(row.actor_user_id), str(row.company_id)) == ("user", USER, company)


async def test_a_goal_made_with_no_actor_is_the_systems_act_not_a_guessed_user(session):  # noqa: ANN001
    await GoalService().create(session, str(uuid.uuid4()), "Ship", GoalLevel.VISION)
    await session.commit()
    (row,) = await _rows(session)
    assert (row.actor_type, row.actor_user_id, row.actor_agent_id) == ("system", None, None)


async def test_setting_a_secret_writes_a_row_that_never_holds_the_value(session):  # noqa: ANN001
    company = str(uuid.uuid4())
    secret = await SecretService().set(session, company, "api-token", SECRET_VALUE, actor=USER)
    await session.commit()
    (row,) = await _rows(session)
    assert (row.action, row.entity_id, str(row.actor_user_id)) == ("secret.set", secret.id, USER)
    stored = repr((row.before_state, row.after_state, row.log_metadata))
    assert SECRET_VALUE not in stored and "api-token" in stored


async def test_assigning_a_label_writes_a_row(session):  # noqa: ANN001
    company = str(uuid.uuid4())
    item = await _item(session, company, "t")
    label = LLCLabel(id=uuid.uuid4(), company_id=uuid.UUID(company), name="bug", color="#ff0000")
    session.add(label)
    await session.commit()
    await LLCLabelService().assign_labels(session, str(item.id), [str(label.id)], actor_user_id=USER)
    await session.commit()
    rows = [r for r in await _rows(session) if r.after_state.get("labels_assigned")]
    assert [(r.entity_id, str(r.actor_user_id)) for r in rows] == [(item.id, USER)]


async def test_changing_a_relation_writes_one_row_not_one_per_mirror(session):  # noqa: ANN001
    company = str(uuid.uuid4())
    a, b = await _item(session, company, "a"), await _item(session, company, "b")
    await WorkItemRelationService().add(
        session,
        company_id=company,
        source_id=str(a.id),
        target_id=str(b.id),
        relation_type=WorkItemRelationType.BLOCKS,
        created_by_user_id=USER,
    )
    await session.commit()
    rows = [r for r in await _rows(session) if r.action == "work_item.relation_added"]
    assert [(r.entity_id, str(r.actor_user_id)) for r in rows] == [(a.id, USER)]


async def test_claiming_a_work_item_writes_a_row_naming_the_claimer(session):  # noqa: ANN001
    company = str(uuid.uuid4())
    item = await _item(session, company, "t")
    await WorkItemService().claim_human(session, str(item.id), USER, company)
    await session.commit()
    rows = [r for r in await _rows(session) if r.action == "work_item.assigned"]
    assert [(r.entity_id, r.actor_type, str(r.actor_user_id)) for r in rows] == [(item.id, "user", USER)]


async def test_a_failed_audit_write_fails_the_goal_and_nothing_is_kept(session):  # noqa: ANN001
    service = GoalService()
    service.activity_log.record = AsyncMock(side_effect=sa.exc.OperationalError("insert", {}, Exception("disk full")))
    with pytest.raises(sa.exc.OperationalError):
        await service.create(session, str(uuid.uuid4()), "Ship", GoalLevel.VISION, actor_user_id=USER)
    await session.rollback()
    assert (await session.execute(sa.text("SELECT count(*) FROM llc_goals"))).scalar_one() == 0


async def test_a_failed_audit_write_fails_the_claim_as_an_activity_record_error(session):  # noqa: ANN001
    company = str(uuid.uuid4())
    item = await _item(session, company, "t")
    service = WorkItemService()
    service.activity_log.record = AsyncMock(side_effect=RuntimeError("audit store down"))
    with pytest.raises(ActivityRecordError, match="audit store down"):
        await service.claim_human(session, str(item.id), USER, company)
    await session.rollback()
    await session.refresh(item)
    assert item.assignee_user_id is None, "the claim survived its failed audit write"


async def test_an_unparseable_company_fails_the_write_instead_of_skipping_it(session):  # noqa: ANN001
    with pytest.raises(ValueError, match="company_id"):
        await GoalService().activity_log.record(
            session, "not-a-uuid", "system", None, "goal.created", "x", str(uuid.uuid4())
        )


async def test_a_failing_publish_does_not_fail_the_write(session):  # noqa: ANN001
    redis = MagicMock()
    redis.publish = AsyncMock(side_effect=ConnectionError("redis down"))
    with patch("llc.services.activity_log.get_async_redis_client", AsyncMock(return_value=redis)):
        await GoalService().create(session, str(uuid.uuid4()), "Ship", GoalLevel.VISION, actor_user_id=USER)
    await session.commit()
    assert len(await _rows(session)) == 1


async def test_clearing_a_reporting_line_writes_a_row_keyed_by_a_real_uuid(session):  # noqa: ANN001
    """The row's entity id used to be ``"user:<uuid>"``, which ``record`` rejects as not a UUID."""
    company, subject = uuid.uuid4(), Holder("user", uuid.uuid4())
    manager = Holder("user", uuid.uuid4())
    service = ReportingLineService()
    with (
        patch("llc.services.reporting_line.require_company_admin", AsyncMock()),
        patch.object(ReportingLineService, "_require_in_company", AsyncMock()),
        patch.object(ReportingLineService, "_would_cycle", AsyncMock(return_value=False)),
    ):
        await service.set_line(
            session, company_id=company, subject=subject, manager=manager, actor_user_id=uuid.UUID(USER)
        )
        assert await service.clear_line(session, company_id=company, subject=subject, actor_user_id=uuid.UUID(USER))
    await session.commit()
    assert [r.action for r in await _rows(session)] == ["reporting_line.set", "reporting_line.cleared"]


async def test_a_workflow_is_audited_under_its_row_id_not_its_free_text_name(session):  # noqa: ANN001
    """``workflow_id`` is free text (``"wf-1"``); the audit table keys on a UUID, so the row's id is used."""
    company, service = uuid.uuid4(), WorkflowService()
    workflow = await service.create(session, company, "wf-1", name="Release", actor=uuid.UUID(USER))
    await service.update_status(session, company, "wf-1", "running", actor=uuid.UUID(USER))
    assert await service.delete(session, company, "wf-1", actor=uuid.UUID(USER))
    await session.commit()
    rows = await _rows(session)
    assert [r.action for r in rows] == ["workflow.created", "workflow.updated", "workflow.deleted"]
    assert {r.entity_id for r in rows} == {workflow.id}
    assert all(r.after_state["workflow_id"] == "wf-1" for r in rows)


async def test_exporting_a_company_is_audited_with_who_exported_it(session):  # noqa: ANN001
    company = uuid.uuid4()
    await PortabilityService(session)._persist(company, "template", {"agents": []}, USER)
    await session.commit()
    (row,) = await _rows(session)
    assert (row.action, row.entity_id, str(row.actor_user_id)) == ("company.export_template", company, USER)
    assert "agents" not in repr(row.after_state), "the exported payload must not be copied into the audit row"


async def test_a_failed_audit_write_fails_a_human_to_agent_handoff(session):  # noqa: ANN001
    service = HandoffService()
    service.activity_log.record = AsyncMock(side_effect=RuntimeError("audit store down"))
    with pytest.raises(ActivityRecordError, match="audit store down"):
        await service._record_h2a_activity(session, str(uuid.uuid4()), USER, str(uuid.uuid4()), str(uuid.uuid4()))
