# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Two opposite concurrent reparents cannot both commit, so no org cycle forms (#19593).

A under B and B under A, each in its own transaction. Before #19593 ``move``
locked only the moved org, so each mover's cycle check read a tree in which the
other move had not happened, both passed, and A -> B -> A committed. ``move``
now locks the moved org and the new parent's whole ancestor chain ``FOR UPDATE``
in one id-ordered statement and checks for a cycle under that lock: one mover
waits, then sees the other's committed move and gets ``CompanyCycleError``.

Each shape runs in both orders, and fully concurrently as well: a lock taken
out of id order would deadlock there, and Postgres would abort a mover with a
deadlock error instead of a cycle error.

Real Postgres only -- SQLite has no row locks (``AUTOBOT_MIGRATION_TEST_ADMIN_URL``).
"""

import asyncio
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.asyncio, pytest.mark.migration_gate, requires_postgres]

#: Long enough that a move which is NOT waiting on the lock has finished.
_BLOCKED_PROBE_SECONDS = 1.0
#: Owner of both orgs, so authorization (#19634) never decides the outcome here.
_ACTOR = uuid.uuid4()


@pytest.fixture()
async def maker(fresh_db_url):
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


#: Two trees and the two moves that, both committed, would close a cycle.
#: ``pair``: A under B and B under A. The FK check on ``parent_org_id`` already
#: share-locks the new parent, so on Postgres this pair serialized even before
#: #19593. ``chains`` is the case only the ancestor-chain lock closes: Y sits under
#: Z and W under X; X under Y and Z under W touch four different rows, so neither
#: the moved-row lock nor the FK lock overlaps, and X -> Y -> Z -> W -> X commits.
_SHAPES = {
    "pair": ({"a": None, "b": None}, ("a", "b"), ("b", "a")),
    "chains": ({"x": None, "z": None, "y": "z", "w": "x"}, ("x", "y"), ("z", "w")),
}


async def _seed(maker, tree: dict) -> dict:  # noqa: ANN001
    """Create *tree* (name -> parent name), every org owned by ``_ACTOR``; return name -> id."""
    from llc.models.company import CompanyCreate
    from llc.models.enums import MembershipRole
    from llc.services.company import CompanyService
    from llc.services.membership_service import MembershipService

    tag = uuid.uuid4().hex[:6]
    ids: dict = {}
    async with maker() as session:
        svc = CompanyService(session)
        for name, parent in tree.items():  # parents precede children in every shape
            create = CompanyCreate(name=f"{name} {tag}", slug=f"{name}-{tag}", parent_org_id=ids.get(parent))
            org = await svc.create(create)
            await MembershipService().add_member(session, str(org.id), str(_ACTOR), MembershipRole.OWNER)
            ids[name] = org.id
        await session.commit()
    return ids


async def _assert_acyclic(maker, ids: dict) -> dict:  # noqa: ANN001
    from user_management.models.organization import Organization

    async with maker() as session:
        parents = {i: (await session.get(Organization, i)).parent_org_id for i in ids.values()}
    for start in parents:
        seen, current = set(), start
        while current is not None:
            assert current not in seen, f"cycle committed: {parents}"
            seen.add(current)
            current = parents[current]
    return parents


async def _move_and_commit(maker, org_id: uuid.UUID, parent_id: uuid.UUID) -> str:  # noqa: ANN001
    from llc.services.company import CompanyCycleError, CompanyService

    async with maker() as session:
        try:
            await CompanyService(session).move(org_id, parent_id, actor_user_id=_ACTOR)
        except CompanyCycleError:
            await session.rollback()
            return "cycle"
        await session.commit()
        return "moved"


def _ordered(shape: str, order: str) -> tuple:
    tree, one, two = _SHAPES[shape]
    return (tree, one, two) if order == "forward" else (tree, two, one)


@pytest.mark.parametrize("shape", sorted(_SHAPES))
@pytest.mark.parametrize("order", ["forward", "reverse"])
async def test_the_second_opposite_move_waits_then_gets_the_cycle_error(maker, shape, order):  # noqa: ANN001
    from llc.services.company import CompanyCycleError, CompanyService

    tree, (org1, par1), (org2, par2) = _ordered(shape, order)
    ids = await _seed(maker, tree)

    async with maker() as a, maker() as b:
        await CompanyService(a).move(ids[org1], ids[par1], actor_user_id=_ACTOR)
        late = asyncio.create_task(CompanyService(b).move(ids[org2], ids[par2], actor_user_id=_ACTOR))
        done, _ = await asyncio.wait({late}, timeout=_BLOCKED_PROBE_SECONDS)
        assert not done, "the opposite move did not wait for the first move's locks"
        await a.commit()
        with pytest.raises(CompanyCycleError):
            await late
        await b.rollback()

    parents = await _assert_acyclic(maker, ids)
    assert parents[ids[org1]] == ids[par1]
    assert parents[ids[org2]] == ids.get(tree[org2])  # unmoved: still where it was seeded


@pytest.mark.parametrize("shape", sorted(_SHAPES))
@pytest.mark.parametrize("order", ["forward", "reverse"])
async def test_fully_concurrent_opposite_moves_commit_exactly_one_without_deadlock(maker, shape, order):  # noqa: ANN001
    tree, (org1, par1), (org2, par2) = _ordered(shape, order)
    ids = await _seed(maker, tree)

    outcomes = await asyncio.gather(
        _move_and_commit(maker, ids[org1], ids[par1]),
        _move_and_commit(maker, ids[org2], ids[par2]),
    )

    assert sorted(outcomes) == ["cycle", "moved"]
    await _assert_acyclic(maker, ids)


async def _revoke(session, org_id: uuid.UUID) -> None:  # noqa: ANN001
    from llc.models.membership import LLCCompanyMembership

    stmt = sa.delete(LLCCompanyMembership).where(
        LLCCompanyMembership.company_id == org_id, LLCCompanyMembership.user_id == _ACTOR
    )
    await session.execute(stmt)


#: (tree, moved org, new parent, the org whose membership is revoked mid-move).
_REVOKES = {
    "top_level_authority": ({"p": None, "o": None}, "o", "p", "o"),
    "top_level_new_parent": ({"p": None, "o": None}, "o", "p", "p"),
    "sideways_new_parent": ({"q": None, "p": None, "o": "q"}, "o", "p", "p"),
    "sideways_authority": ({"q": None, "p": None, "o": "q"}, "o", "p", "q"),
}


@pytest.mark.parametrize("case", sorted(_REVOKES))
async def test_a_revoke_waits_for_the_moves_membership_lock(maker, case):  # noqa: ANN001
    """#19634 review: under the lock the move holds BOTH deciding membership rows (the
    authority's and the new parent's), so a concurrent revoke of either role serializes
    behind the move instead of racing it."""
    from llc.services.company import CompanyService

    tree, moved, new_parent, revoked = _REVOKES[case]
    ids = await _seed(maker, tree)
    async with maker() as a, maker() as b:
        await CompanyService(a).move(ids[moved], ids[new_parent], actor_user_id=_ACTOR)
        revoke = asyncio.create_task(_revoke(b, ids[revoked]))
        done, _ = await asyncio.wait({revoke}, timeout=_BLOCKED_PROBE_SECONDS)
        assert not done, f"the revoke of {revoked!r} did not wait for the move's membership lock"
        await a.commit()
        await revoke
        await b.commit()
    parents = await _assert_acyclic(maker, ids)
    assert parents[ids[moved]] == ids[new_parent]
