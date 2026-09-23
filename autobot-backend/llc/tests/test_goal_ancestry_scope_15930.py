# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A cross-company parent edge must not leak the chain (#15930).

`GET /goals/{goal_id}/ancestors` authorised the **starting** goal and then walked
its parent chain with `company_id` omitted. `GoalService.get_ancestors` has a
tenant check gated on that argument, so the defence existed, was correct, and was
not switched on — and #13704's own docstring names this exact shape:

    Scoping only the leaf is not enough — a cross-company parent edge makes the
    chain itself the leak.

**The edge is creatable in the database.** `llc_goals.parent_goal_id` is a
self-referential FK with no company constraint; only the service `create` guard
stops new ones, and by #13704's account such edges existed before that guard. So
these tests build the edge directly rather than through `create`, which is the
state a pre-#13704 installation can be in.

**Every assertion is on the response contents**, not on a log line. "A warning
was emitted" and "the ancestor was withheld" are different claims, and only the
second is the fix.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.goal import GoalLevel, LLCGoal
from llc.services.goal import GoalService
from llc.tests import _e2e_harness as harness

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def engine():  # noqa: ANN201
    eng = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    await harness.create_loop_schema(eng)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:  # noqa: ANN001
    factory = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    async with factory() as s:
        yield s


async def _goal(session: AsyncSession, company: str, title: str, *, parent=None, level=GoalLevel.OBJECTIVE):
    """Seed directly, because `create` refuses the cross-company edge under test.

    That guard is #13704's and it is correct — it stops NEW edges. This
    reproduces the pre-guard state an existing installation may hold, which is
    the whole reason the walk needs its own check.
    """
    goal = LLCGoal(
        id=uuid.uuid4(),
        company_id=company,
        title=title,
        level=level.value,
        parent_goal_id=parent.id if parent is not None else None,
    )
    session.add(goal)
    await session.commit()
    return goal


async def test_a_foreign_ancestor_is_absent_from_the_walk(session):  # noqa: ANN001
    """The defect: the caller owns the leaf, the parent belongs elsewhere."""
    mine, theirs = str(uuid.uuid4()), str(uuid.uuid4())
    foreign_root = await _goal(session, theirs, "their strategy", level=GoalLevel.OBJECTIVE)
    leaf = await _goal(session, mine, "my objective", parent=foreign_root, level=GoalLevel.KEY_RESULT)

    ancestors = await GoalService().get_ancestors(session, leaf.id, company_id=mine)

    assert [a.title for a in ancestors] == [], "another company's goal was returned as an ancestor"


async def test_the_walk_is_scoped_even_when_the_caller_omits_the_company(session):  # noqa: ANN001
    """The actual defect at the route, and the reason the default changed.

    `goals.py` called this with no `company_id`. An optional tenant scope is off
    by default, so the check was skipped — not because anyone chose to skip it,
    but because the call site predated the parameter and no diff showed it.

    The scope now derives from the starting goal, which is the goal the caller
    was authorised for.
    """
    mine, theirs = str(uuid.uuid4()), str(uuid.uuid4())
    foreign_root = await _goal(session, theirs, "their strategy", level=GoalLevel.OBJECTIVE)
    leaf = await _goal(session, mine, "my objective", parent=foreign_root, level=GoalLevel.KEY_RESULT)

    ancestors = await GoalService().get_ancestors(session, leaf.id)

    assert [a.title for a in ancestors] == [], "the unscoped default leaked another company's ancestor"


async def test_an_own_company_chain_is_returned_in_full(session):  # noqa: ANN001
    """The contrast case. Without it, a walk that returned nothing satisfies
    both assertions above while breaking the feature."""
    mine = str(uuid.uuid4())
    root = await _goal(session, mine, "strategy", level=GoalLevel.OBJECTIVE)
    mid = await _goal(session, mine, "objective", parent=root, level=GoalLevel.KEY_RESULT)
    leaf = await _goal(session, mine, "key result", parent=mid, level=GoalLevel.KEY_RESULT)

    ancestors = await GoalService().get_ancestors(session, leaf.id)

    assert [a.title for a in ancestors] == ["strategy", "objective"], "root-first own-company chain"


async def test_the_walk_stops_at_the_edge_rather_than_skipping_it(session):  # noqa: ANN001
    """A foreign goal must terminate the walk, not be filtered out of it.

    Continuing past it would return the caller's own grandparent — reachable
    only *through* another company's row, which is the traversal the issue is
    about rather than the disclosure of one title.
    """
    mine, theirs = str(uuid.uuid4()), str(uuid.uuid4())
    my_root = await _goal(session, mine, "my root", level=GoalLevel.OBJECTIVE)
    foreign_mid = await _goal(session, theirs, "their middle", parent=my_root, level=GoalLevel.KEY_RESULT)
    leaf = await _goal(session, mine, "my leaf", parent=foreign_mid, level=GoalLevel.KEY_RESULT)

    ancestors = await GoalService().get_ancestors(session, leaf.id, company_id=mine)

    titles = [a.title for a in ancestors]
    assert "their middle" not in titles, "the foreign ancestor was returned"
    assert "my root" not in titles, "the walk continued THROUGH another company's row"


async def test_ancestry_for_a_work_item_refuses_a_foreign_goal(session):  # noqa: ANN001
    """The sibling method, whose KB caller also omitted the company.

    Its entry check answers a different question from the walk's — "is this goal
    the caller's?" — and cannot be derived from the goal itself without becoming
    a tautology. So it stays an argument, and `context_builder` now passes it.
    """
    mine, theirs = str(uuid.uuid4()), str(uuid.uuid4())
    foreign = await _goal(session, theirs, "their goal", level=GoalLevel.OBJECTIVE)

    chain = await GoalService().get_goal_ancestry_for_work_item(session, foreign.id, company_id=mine)

    assert chain == [], "another company's goal produced an ancestry chain"


async def test_ancestry_for_a_work_item_returns_own_goals(session):  # noqa: ANN001
    """The contrast for the check above."""
    mine = str(uuid.uuid4())
    root = await _goal(session, mine, "root", level=GoalLevel.OBJECTIVE)
    leaf = await _goal(session, mine, "leaf", parent=root, level=GoalLevel.KEY_RESULT)

    chain = await GoalService().get_goal_ancestry_for_work_item(session, leaf.id, company_id=mine)

    assert [c["title"] for c in chain] == ["root", "leaf"], "root-first, inclusive of the goal itself"


def _client(session: AsyncSession, org: str, *, is_admin: bool = False):
    """The mounted goals router, with *org* as the caller's tenant."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.user_management.dependencies import get_current_user, require_org_context
    from autobot_shared.user_management.base_service import TenantContext
    from llc.api.goals import router
    from user_management.database import get_async_session

    app = FastAPI()
    app.include_router(router, prefix="/api/llc")

    async def _fake_session():
        yield session

    app.dependency_overrides[get_async_session] = _fake_session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(uuid.uuid4())}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=uuid.UUID(org), user_id=uuid.uuid4(), is_platform_admin=is_admin
    )
    return TestClient(app)


async def test_the_route_gives_a_platform_admin_the_cross_company_chain(session):  # noqa: ANN001
    """Through the route, which is where the defect is.

    `_get_authorized_goal:119` exempts platform admins (`and not
    ctx.is_platform_admin`), so an admin legitimately reaches a goal whose
    company is not `ctx.org_id`. The route passing `ctx.org_id` down then stopped
    the walk at the first step and returned an empty chain — the truth is a
    chain, and "no ancestors" is a different answer.

    **The parameter's meaning inverted inside #15930's own fix.** Before the
    derived default existed, *omitting* `company_id` was the bug: the walk ran
    unscoped. After it exists, *supplying* it is. Deleting the argument is the
    fix, and a reader following that line to #15930 would otherwise read it as
    load-bearing tenant isolation.
    """
    admin_org, goal_company = str(uuid.uuid4()), str(uuid.uuid4())
    root = await _goal(session, goal_company, "their root", level=GoalLevel.OBJECTIVE)
    leaf = await _goal(session, goal_company, "their leaf", parent=root, level=GoalLevel.KEY_RESULT)

    body = _client(session, admin_org, is_admin=True).get(f"/api/llc/goals/{leaf.id}/ancestors").json()

    assert [g["title"] for g in body] == [
        "their root"
    ], "a platform admin authorised for this goal got no ancestry from the route"


async def test_the_route_still_refuses_a_non_admin_from_another_org(session):  # noqa: ANN001
    """The contrast, and the assurance that deleting the argument costs nothing.

    A normal caller is 404'd by `_get_authorized_goal` before the walk runs, so
    the derived scope never gets the chance to be more permissive than the
    passed one. Only the admin case moves.
    """
    other_org, goal_company = str(uuid.uuid4()), str(uuid.uuid4())
    root = await _goal(session, goal_company, "their root", level=GoalLevel.OBJECTIVE)
    leaf = await _goal(session, goal_company, "their leaf", parent=root, level=GoalLevel.KEY_RESULT)

    response = _client(session, other_org, is_admin=False).get(f"/api/llc/goals/{leaf.id}/ancestors")

    assert response.status_code == 404, "a non-admin reached another org's goal"


async def test_the_route_omits_a_foreign_ancestor_for_the_childs_own_owner(session):  # noqa: ANN001
    """#15930 criterion 2: the leak scenario, at the boundary a caller sees.

    Everything above proves this at the service layer. That is the same layer the
    defect hid behind — `get_ancestors` looked scoped because a caller *could*
    pass `company_id`, and the route did not. So the scenario is asserted here
    through the mounted router, as an ordinary tenant asking for its own goal's
    ancestry, with the assertion on the RESPONSE BODY rather than on a log line
    or a return value.

    The seeded shape is the pre-guard state #13704 stopped anyone creating new:
    a goal whose parent belongs to another company. `create` refuses that edge
    today, which is why `_goal` inserts directly — an installation that predates
    the guard can still hold one.
    """
    mine, theirs = str(uuid.uuid4()), str(uuid.uuid4())
    foreign_root = await _goal(session, theirs, "their objective", level=GoalLevel.OBJECTIVE)
    my_leaf = await _goal(session, mine, "my key result", parent=foreign_root, level=GoalLevel.KEY_RESULT)

    response = _client(session, mine, is_admin=False).get(f"/api/llc/goals/{my_leaf.id}/ancestors")

    assert response.status_code == 200, "the child's own owner must reach its own goal"
    titles = [g["title"] for g in response.json()]
    assert titles == [], (
        "another company's goal was returned in the ancestry response for a caller "
        f"who owns only the child: {titles}"
    )


async def test_the_route_returns_an_own_company_chain_in_full(session):  # noqa: ANN001
    """The contrast that stops the assertion above being satisfied by returning nothing.

    An empty list is the correct answer to the foreign-parent case and the wrong
    answer to this one. Without both, a route that always returned `[]` would
    pass the criterion.
    """
    mine = str(uuid.uuid4())
    root = await _goal(session, mine, "my objective", level=GoalLevel.OBJECTIVE)
    leaf = await _goal(session, mine, "my key result", parent=root, level=GoalLevel.KEY_RESULT)

    response = _client(session, mine, is_admin=False).get(f"/api/llc/goals/{leaf.id}/ancestors")

    assert response.status_code == 200
    assert [g["title"] for g in response.json()] == ["my objective"]
