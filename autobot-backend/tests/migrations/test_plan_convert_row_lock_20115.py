# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A plan's row lock serialises a convert and an edit, and a double convert creates one set of rows (#20115).

Every plan write takes ``plan_store.load_writable``'s ``FOR UPDATE`` before it reads the document. The unit
tests run on SQLite, which has no row locks, so they cannot show it works. Here several real sessions race:

* an edit that holds the lock makes a queued convert wait, then the convert sees the edit voided the approval
  and creates nothing;
* a lock held while a convert and an edit queue behind it (the convert first, confirmed through
  ``pg_blocking_pids``): the convert wins, the edit is refused as the revision is converted;
* the same for two converts: exactly one set of rows exists, and the second is refused;
* two edits queued on one row both keep their change.

The controls run the same races with the lock dropped and end differently: the second writer works from the
document it read before the first committed, so an edit is lost, and a convert goes ahead on an approval
that no longer stands.

Real Postgres only (``AUTOBOT_MIGRATION_TEST_ADMIN_URL``).
"""

import asyncio
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.migrations.conftest import requires_postgres, run_alembic
from tests.migrations.test_membership_lock_19985 import _backend_pid

pytestmark = [pytest.mark.asyncio, pytest.mark.migration_gate, requires_postgres]

ACTOR = uuid.uuid4()
PLAN = "intake"
#: Upper bound on waiting for a condition to become true; never the ordering itself.
_DEADLINE_SECONDS = 15.0
_POLL_SECONDS = 0.05


@pytest.fixture()
async def maker(fresh_db_url, monkeypatch):
    from llc.services.goal import GoalService

    monkeypatch.setattr(GoalService, "_schedule_post_commit_index", lambda *a, **k: None)
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url, pool_size=12)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    # The conversion files its AI-line proposals in the approvals store's own session: point it at this database.
    monkeypatch.setattr("services.ai_line_change_proposal.get_async_session_factory", lambda: sessions)
    yield sessions
    await engine.dispose()


async def _seed_company(maker) -> tuple:  # noqa: ANN001
    """A company owned by ``ACTOR`` with one role held by a person; return (company, role)."""
    from llc.models.company import CompanyCreate
    from llc.models.enums import MembershipRole, RoleHolderType
    from llc.models.role_assignment import LLCRoleAssignment
    from llc.services.company import CompanyService
    from llc.services.membership_service import MembershipService
    from user_management.models.role import Role

    tag = uuid.uuid4().hex[:6]
    async with maker() as session:
        org = await CompanyService(session).create(CompanyCreate(name=f"co {tag}", slug=f"co-{tag}"))
        await MembershipService().add_member(session, str(org.id), str(ACTOR), MembershipRole.OWNER)
        role = Role(id=uuid.uuid4(), org_id=org.id, name="Operator")
        session.add(role)
        await session.flush()
        held = LLCRoleAssignment(
            id=uuid.uuid4(), company_id=org.id, role_id=role.id, holder_type=RoleHolderType.USER.value
        )
        held.holder_user_id = uuid.uuid4()
        session.add(held)
        await session.commit()
    return org.id, role.id


async def _approved_plan(maker) -> uuid.UUID:  # noqa: ANN001
    """An approved plan, built through the services one committed step at a time; return its company."""
    from llc.services.company_os.plan_convert import PlanConversionService
    from llc.services.company_os.plan_types import (
        Direction,
        Edge,
        EdgeCase,
        HolderKind,
        Label,
        Lane,
        ReturnKind,
        Step,
        SubStep,
        SubStepState,
        Unit,
    )
    from llc.services.company_os.plans import CompanyOsPlanService

    company, role = await _seed_company(maker)
    lanes = [Lane(key="ops", name="Ops", holder_kind=HolderKind.USER, role_id=role)]
    lanes.append(Lane(key="cust", name="Customer", holder_kind=HolderKind.CUSTOMER))
    steps = [Step(key=k, lane_key=ln, label=k) for k, ln in (("s1", "ops"), ("s2", "ops"), ("s3", "cust"))]
    edges = [Edge(from_step="s1", to_step="s2"), Edge(from_step="s2", to_step="s3")]
    plans, conversion = CompanyOsPlanService(), PlanConversionService()
    subs = [
        SubStep(key="c1", step_key="s2", lane_key="", label="Listen", state=SubStepState.CURRENT),
        SubStep(
            key="p1",
            step_key="s2",
            lane_key="",
            label="Price it",
            state=SubStepState.PROPOSED,
            classification=Label.AUTOMATION,
            tool_action="pricing:calc",
            replaces=["c1"],
        ),
    ]
    case = EdgeCase(step_key="s2", key="e1", description="No photos", classification=Label.AUTOMATION, handling="Ask")
    async with maker() as session:
        await plans.create(
            session,
            company,
            actor=ACTOR,
            lanes=lanes,
            steps=steps,
            edges=edges,
            key=PLAN,
            name="Client intake",
            entry_point="org_chart",
            starts_at="A call",
            ends_at="A yes",
        )
        for step in ("s1", "s2", "s3"):
            await plans.put_metric(
                session, company, PLAN, step, actor=ACTOR, frequency=(5, Unit.PER_WEEK), duration=(2, Unit.HOURS)
            )
        await plans.put_one_number(
            session,
            company,
            PLAN,
            actor=ACTOR,
            title="Hours",
            step_key="s2",
            return_kind=ReturnKind.HOURS_BACK,
            direction=Direction.DOWN,
            unit=Unit.HOURS,
            baseline_value=2,
        )
        await plans.put_breakdown(session, company, PLAN, "s2", actor=ACTOR, sub_steps=subs, edge_cases=[case])
        await session.commit()
        await conversion.preview(session, company, PLAN, actor=ACTOR)
        await session.commit()
        plan = await conversion.approve(session, company, PLAN, actor=ACTOR)
        await session.commit()
    assert plan.status.value == "approved"
    return company


async def _edit(maker, company, key: str) -> str:  # noqa: ANN001
    """Add step *key* in its own transaction; return how it ended."""
    from llc.services.company_os.errors import CompanyOsConflict
    from llc.services.company_os.plan_edit import PlanEditService
    from llc.services.company_os.plan_types import Step

    async with maker() as session:
        try:
            await PlanEditService().add_step(
                session, company, PLAN, Step(key=key, lane_key="ops", label=key), actor=ACTOR
            )
        except CompanyOsConflict:
            await session.rollback()
            return "refused"
        await session.commit()
        return "edited"


async def _convert(maker, company) -> str:  # noqa: ANN001
    """Convert in its own transaction; return how it ended."""
    from llc.services.company_os.errors import CompanyOsConflict, ConversionBlocked
    from llc.services.company_os.plan_convert import PlanConversionService

    async with maker() as session:
        try:
            await PlanConversionService().convert(session, company, PLAN, actor=ACTOR)
        except ConversionBlocked:
            await session.rollback()
            return "blocked"
        except CompanyOsConflict:
            await session.rollback()
            return "refused"
        await session.commit()
        return "converted"


async def _rows(maker, company) -> dict:  # noqa: ANN001
    """Workflows, processes and the stored plan's steps and status, read in a fresh session."""
    from llc.models.company_os import LLCProcess
    from llc.models.company_os_plan import CompanyOsWorkflowPlan as Plan
    from models.workflow import Workflow

    def count(model):  # noqa: ANN001
        return sa.select(sa.func.count()).select_from(model).where(model.company_id == company)

    async with maker() as s:
        plan = (await s.execute(sa.select(Plan).where(Plan.company_id == company))).scalar_one()
        return {
            "workflows": (await s.execute(count(Workflow))).scalar_one(),
            "processes": (await s.execute(count(LLCProcess))).scalar_one(),
            "steps": sorted(x["key"] for x in plan.document["steps"]),
            "status": plan.status,
        }


async def _hold_edit(session, company) -> None:  # noqa: ANN001
    """The lock, taken the way every edit takes it, with a change that voids the approval."""
    from llc.services.company_os.plan_edit import PlanEditService
    from llc.services.company_os.plan_types import Step

    step = Step(key="held", lane_key="ops", label="held")
    await PlanEditService().add_step(session, company, PLAN, step, actor=ACTOR)


async def _hold_lock(session, company) -> None:  # noqa: ANN001
    from llc.services.company_os.plan_store import locked_plan

    await locked_plan(session, company, PLAN, ACTOR)


async def _count_waiters_behind(maker, holder_pid: int) -> int:  # noqa: ANN001
    """Backends queued, directly or through another waiter, behind the session *holder_pid*.

    Followed through ``pg_blocking_pids`` recursively: a second queued writer waits on the first one, so
    the holder alone would show one waiter. Nothing outside that chain is counted.
    """
    sql = """
        WITH RECURSIVE queued(pid) AS (
            SELECT pid FROM pg_stat_activity WHERE :holder = ANY(pg_blocking_pids(pid))
            UNION
            SELECT a.pid FROM pg_stat_activity a JOIN queued q ON q.pid = ANY(pg_blocking_pids(a.pid))
        )
        SELECT count(*) FROM queued
    """
    async with maker() as monitor:
        return (await monitor.execute(sa.text(sql), {"holder": holder_pid})).scalar_one()


async def _wait_for_waiters(maker, holder_pid: int, count: int, task: asyncio.Task) -> None:  # noqa: ANN001
    """Return once *count* backends are queued behind *holder_pid*; fail if *task* finished first."""
    deadline = asyncio.get_running_loop().time() + _DEADLINE_SECONDS
    while await _count_waiters_behind(maker, holder_pid) < count:
        assert not task.done(), "a racer finished without waiting on the session holding the row"
        assert asyncio.get_running_loop().time() < deadline, "the racer never waited on the holding session"
        await asyncio.sleep(_POLL_SECONDS)


async def _race(maker, company, hold, *racers) -> list:  # noqa: ANN001
    """Session A runs *hold* and stays open; each racer starts in turn and is seen waiting; A commits.

    Returns the racers' outcomes in the order they queued. Each racer is a coroutine function of
    (maker, company).
    """
    tasks: list = []
    async with maker() as a:
        await hold(a, company)
        holder_pid = await _backend_pid(a)
        for racer in racers:
            tasks.append(asyncio.create_task(racer(maker, company)))
            await _wait_for_waiters(maker, holder_pid, len(tasks), tasks[-1])
        await a.commit()
    return [await t for t in tasks]


async def _late(maker, company) -> str:  # noqa: ANN001
    return await _edit(maker, company, "late")


@pytest.fixture()
def no_row_lock(monkeypatch):
    """Drop ``FOR UPDATE`` from every plan read: the control for each race below."""
    from llc.services.company_os import plan_store

    real = plan_store.load_row

    async def _unlocked(session, company_id, plan_key, revision=None, *, lock=False):  # noqa: ANN001
        return await real(session, company_id, plan_key, revision, lock=False)

    monkeypatch.setattr(plan_store, "load_row", _unlocked)


async def test_a_convert_queued_behind_an_edit_sees_the_voided_approval_and_creates_nothing(maker):
    company = await _approved_plan(maker)
    assert await _race(maker, company, _hold_edit, _convert) == ["blocked"]
    rows = await _rows(maker, company)
    assert (rows["workflows"], rows["processes"]) == (0, 0) and rows["status"] != "converted"
    assert "held" in rows["steps"]


async def test_a_convert_and_an_edit_queued_on_one_lock_run_in_order_and_the_edit_is_refused(maker):
    company = await _approved_plan(maker)
    assert await _race(maker, company, _hold_lock, _convert, _late) == ["converted", "refused"]
    rows = await _rows(maker, company)
    assert rows["status"] == "converted" and "late" not in rows["steps"]


async def test_two_converts_queued_on_one_lock_create_one_set_of_rows_and_the_second_is_refused(maker):
    company = await _approved_plan(maker)
    assert await _race(maker, company, _hold_lock, _convert, _convert) == ["converted", "refused"]
    rows = await _rows(maker, company)
    assert (rows["workflows"], rows["processes"]) == (1, 1)


async def test_two_edits_queued_on_one_row_both_keep_their_change(maker):
    company = await _approved_plan(maker)
    assert await _race(maker, company, _hold_edit, _late) == ["edited"]
    assert {"held", "late"} <= set((await _rows(maker, company))["steps"])


async def test_control_without_the_lock_the_second_edit_overwrites_the_first(maker, no_row_lock):
    company = await _approved_plan(maker)
    assert await _race(maker, company, _hold_edit, _late) == ["edited"]
    steps = (await _rows(maker, company))["steps"]
    assert "late" in steps and "held" not in steps  # the first person's step is gone


async def test_control_without_the_lock_a_convert_goes_ahead_on_an_approval_the_edit_voided(maker, no_row_lock):
    company = await _approved_plan(maker)
    assert await _race(maker, company, _hold_edit, _convert) == ["converted"]
    rows = await _rows(maker, company)
    assert rows["status"] == "converted" and "held" not in rows["steps"]
    assert (rows["workflows"], rows["processes"]) == (1, 1)
