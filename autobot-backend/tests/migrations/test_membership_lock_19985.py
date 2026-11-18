# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``lock_company_members`` stops a stale role read and a deadlock, on two real sessions (#19985).

#19654 made every membership write take ``lock_company_members`` before it reads any
role. The unit tests run on SQLite, which has no row locks, so they cannot show it works.
Here two sessions run the route's own sequence (lock, actor check, read the current role,
authorize, write) against Postgres:

* an admin demoting a user another session is promoting to owner waits for that session,
  then reads ``owner`` and is refused -- it never acts on the role it would have read before;
* two owners demoting each other, or themselves: the second change is held behind the first
  one's open transaction (confirmed through ``pg_blocking_pids``, so the overlap is forced),
  then refused once the first commits, and the company keeps an owner;
* the same races with the lock patched to a no-op end differently (promotion race, and the
  two-owner self-demotion), so those tests can fail. The mutual-demotion race has no
  deterministic control: each actor's own row lock already serializes it, and the unlocked
  deadlock needs a specific interleaving inside one call that a test cannot force.

Real Postgres only (``AUTOBOT_MIGRATION_TEST_ADMIN_URL``).
"""

import asyncio
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.asyncio, pytest.mark.migration_gate, requires_postgres]

#: Upper bound on waiting for a condition to become true; never the ordering itself.
_DEADLINE_SECONDS = 15.0
_POLL_SECONDS = 0.05


@pytest.fixture()
async def maker(fresh_db_url):
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _seed(maker, roles: dict) -> tuple:  # noqa: ANN001
    """One company with one user per name in *roles* (name -> MembershipRole); return (company, ids)."""
    from llc.models.company import CompanyCreate
    from llc.services.company import CompanyService
    from llc.services.membership_service import MembershipService

    tag = uuid.uuid4().hex[:6]
    ids = {name: uuid.uuid4() for name in roles}
    async with maker() as session:
        org = await CompanyService(session).create(CompanyCreate(name=f"co {tag}", slug=f"co-{tag}"))
        for name, role in roles.items():
            await MembershipService().add_member(session, str(org.id), str(ids[name]), role)
        await session.commit()
    return org.id, ids


async def _change_role(session, company, actor, target, new_role) -> None:  # noqa: ANN001
    """The route's sequence in ``llc/api/company_members.py::change_member_role``, minus HTTP."""
    import llc.services.membership_policy as membership_policy
    from llc.services.authz import require_company_admin_unless_platform
    from llc.services.membership_service import MemberNotFoundError, MembershipService

    svc = MembershipService()
    await membership_policy.lock_company_members(session, company)
    await require_company_admin_unless_platform(session, company, actor, platform_admin=False)
    existing = await svc.get_member(session, str(company), str(target))
    if existing is None:
        raise MemberNotFoundError(f"User {target} is not a member of company {company}")
    current = existing.role
    await membership_policy.authorize_member_change(
        session, company, actor, platform_admin=False, current_role=current, new_role=new_role
    )
    await svc.change_role(session, str(company), str(target), new_role, actor_id=str(actor))


async def _attempt(maker, company, actor, target, new_role) -> str:  # noqa: ANN001
    """Run one change in its own transaction; return how it ended."""
    from llc.services.authz import NotAuthorisedError
    from llc.services.membership_policy import LastOwnerError

    async with maker() as session:
        try:
            await _change_role(session, company, actor, target, new_role)
        except LastOwnerError:
            await session.rollback()
            return "last_owner"
        except NotAuthorisedError:
            await session.rollback()
            return "refused"
        await session.commit()
        return "changed"


async def _role_of(maker, company, user) -> str:  # noqa: ANN001
    from llc.models.membership import LLCCompanyMembership as M

    async with maker() as session:
        role = (await session.execute(sa.select(M.role).where(M.company_id == company, M.user_id == user))).scalar_one()
    return role.value


async def _backend_pid(session) -> int:  # noqa: ANN001
    return (await session.execute(sa.text("SELECT pg_backend_pid()"))).scalar_one()


async def _count_waiting_on(maker, pid: int) -> int:  # noqa: ANN001
    async with maker() as monitor:
        sql = "SELECT count(*) FROM pg_stat_activity WHERE :pid = ANY(pg_blocking_pids(pid))"
        return (await monitor.execute(sa.text(sql), {"pid": pid})).scalar_one()


async def _wait_until_blocked_on(maker, pid: int, task: asyncio.Task) -> None:  # noqa: ANN001
    """Return once some backend waits for *pid*'s locks; fail if *task* finished first (it did not wait)."""
    deadline = asyncio.get_running_loop().time() + _DEADLINE_SECONDS
    while await _count_waiting_on(maker, pid) == 0:
        assert not task.done(), "the second change finished without waiting on the first session's locks"
        assert asyncio.get_running_loop().time() < deadline, "no backend ever waited on the first session"
        await asyncio.sleep(_POLL_SECONDS)


async def _race_held_change(maker, company, held: tuple, racing: tuple, *, blocks: bool = True) -> str:  # noqa: ANN001
    """Session A applies *held* (actor, target, role) and keeps its transaction open while B tries *racing*.

    With *blocks*, B must be seen waiting on A through ``pg_blocking_pids`` before A commits; without it
    (the no-lock controls) B must finish on its own. Returns B's outcome.
    """
    async with maker() as a:
        await _change_role(a, company, *held)
        pid = await _backend_pid(a)
        late = asyncio.create_task(_attempt(maker, company, *racing))
        try:
            if blocks:
                await _wait_until_blocked_on(maker, pid, late)
            else:
                await asyncio.wait_for(asyncio.shield(late), _DEADLINE_SECONDS)
            await a.commit()
            return await late
        finally:
            if not late.done():
                late.cancel()
                await asyncio.gather(late, return_exceptions=True)


async def _no_lock(session, company_id):  # noqa: ANN001, ARG001
    return None


async def _promote_then_race_a_demotion(maker, *, blocks: bool = True) -> tuple:  # noqa: ANN001
    """A promotes ``u`` to owner and holds; admin B tries to demote ``u``. Returns (B's outcome, u's role)."""
    from llc.models.enums import MembershipRole as R

    company, ids = await _seed(maker, {"owner": R.OWNER, "admin": R.ADMIN, "u": R.MEMBER})
    held, racing = (ids["owner"], ids["u"], R.OWNER), (ids["admin"], ids["u"], R.GUEST)
    outcome = await _race_held_change(maker, company, held, racing, blocks=blocks)
    return outcome, await _role_of(maker, company, ids["u"])


async def _two_owner_race(maker, *, mutual: bool, blocks: bool = True) -> tuple:  # noqa: ANN001
    """Two owners each demote ``mutual`` ly the other or themselves; A holds first. Returns (B outcome, roles)."""
    from llc.models.enums import MembershipRole as R

    company, ids = await _seed(maker, {"o1": R.OWNER, "o2": R.OWNER})
    t1, t2 = (ids["o2"], ids["o1"]) if mutual else (ids["o1"], ids["o2"])
    outcome = await _race_held_change(
        maker, company, (ids["o1"], t1, R.MEMBER), (ids["o2"], t2, R.MEMBER), blocks=blocks
    )
    roles = [await _role_of(maker, company, ids["o1"]), await _role_of(maker, company, ids["o2"])]
    return outcome, sorted(roles)


async def test_an_admin_demotion_waits_then_reads_the_committed_owner_role(maker):  # noqa: ANN001
    outcome, role = await _promote_then_race_a_demotion(maker)

    assert outcome == "refused"
    assert role == "owner"


async def test_control_without_the_lock_the_admin_demotes_the_new_owner(maker, monkeypatch):  # noqa: ANN001
    """Same race, lock patched out: B reads ``member``, passes, and overwrites A's promotion."""
    import llc.services.membership_policy as membership_policy

    monkeypatch.setattr(membership_policy, "lock_company_members", _no_lock)

    # B still waits, but at its row write (A's promotion holds that row), after the stale read.
    outcome, role = await _promote_then_race_a_demotion(maker)

    assert (outcome, role) == ("changed", "guest")


async def test_two_owners_demoting_each_other_the_second_waits_then_is_refused(maker):  # noqa: ANN001
    outcome, roles = await _two_owner_race(maker, mutual=True)

    # The loser is no longer an owner once the winner commits, so the actor check refuses it.
    assert outcome == "refused"
    assert roles == ["member", "owner"]


async def test_two_owners_demoting_themselves_the_second_waits_then_gets_last_owner(maker):  # noqa: ANN001
    outcome, roles = await _two_owner_race(maker, mutual=False)

    assert outcome == "last_owner"
    assert roles == ["member", "owner"]


async def test_control_without_the_lock_two_owners_demote_themselves_to_no_owner(maker, monkeypatch):  # noqa: ANN001
    """Lock patched out: B counts two owners while A is uncommitted, so both land and none is left."""
    import llc.services.membership_policy as membership_policy

    monkeypatch.setattr(membership_policy, "lock_company_members", _no_lock)

    outcome, roles = await _two_owner_race(maker, mutual=False, blocks=False)

    assert (outcome, roles) == ("changed", ["member", "member"])
