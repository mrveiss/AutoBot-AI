# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Child goals must be reachable (#12739).

`GET /goals` forces `parent_goal_id IS NULL`, so it returns roots only. Children
persisted fine and a direct `GET /goals/{id}` worked, but nothing listed them —
so the Goal Tree UI could not render anything below the roots.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from user_management.services import TenantContext

_ORG = "22222222-2222-2222-2222-222222222222"
_USER = uuid.UUID("66666666-6666-6666-6666-666666666666")


def _goal(company_id: str, parent=None, title="Goal", level="vision", gid=None) -> MagicMock:
    g = MagicMock()
    g.id = gid or uuid.uuid4()
    g.company_id = company_id
    g.parent_goal_id = parent
    g.title = title
    g.description = None
    g.level = level
    g.status = "draft"
    g.owner_agent_id = None
    g.due_date = None
    g.created_at = datetime.now(timezone.utc)
    g.updated_at = datetime.now(timezone.utc)
    return g


def _client(all_goals=None, children=None, focus_goal=None, caller_org=_ORG) -> TestClient:
    from api.user_management.dependencies import get_current_user, require_org_context
    from llc.api.goals import router
    from user_management.database import get_async_session

    app = FastAPI()
    app.include_router(router, prefix="/api/llc")

    session = AsyncMock()
    session.commit = AsyncMock()

    async def _fake_session():
        yield session

    app.dependency_overrides[get_async_session] = _fake_session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_USER)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=uuid.UUID(caller_org), user_id=_USER, is_platform_admin=False
    )

    patch("llc.api.goals.GoalService.list_all_by_company", new=AsyncMock(return_value=all_goals or [])).start()
    patch("llc.api.goals.GoalService.list_by_company", new=AsyncMock(return_value=children or [])).start()
    patch("llc.api.goals.GoalService.get", new=AsyncMock(return_value=focus_goal)).start()
    return TestClient(app)


@pytest.fixture(autouse=True)
def _stop_patches():
    yield
    patch.stopall()


def _hierarchy():
    """mission (root) -> objective -> key_result, plus a second root."""
    mission = _goal(_ORG, title="Mission", level="mission")
    vision = _goal(_ORG, title="Vision", level="vision")
    objective = _goal(_ORG, parent=mission.id, title="Objective", level="objective")
    kr = _goal(_ORG, parent=objective.id, title="Key Result", level="key_result")
    return mission, vision, objective, kr


def test_tree_returns_nested_descendants():
    mission, vision, objective, kr = _hierarchy()
    resp = _client(all_goals=[mission, vision, objective, kr]).get(f"/api/llc/goals/tree?company_id={_ORG}")

    assert resp.status_code == 200
    roots = resp.json()
    assert {r["title"] for r in roots} == {"Mission", "Vision"}

    mission_node = next(r for r in roots if r["title"] == "Mission")
    assert [c["title"] for c in mission_node["children"]] == ["Objective"]
    assert [c["title"] for c in mission_node["children"][0]["children"]] == ["Key Result"]


def test_tree_route_is_not_shadowed_by_the_goal_id_route():
    """FastAPI matches in declaration order — a later /tree would bind to {goal_id}."""
    mission, vision, objective, kr = _hierarchy()
    resp = _client(all_goals=[mission, vision, objective, kr]).get(f"/api/llc/goals/tree?company_id={_ORG}")

    assert resp.status_code == 200, "'/tree' was parsed as a goal_id — route order regressed"
    assert isinstance(resp.json(), list)


def test_tree_is_tenant_scoped():
    resp = _client(all_goals=[], caller_org=_ORG).get(
        "/api/llc/goals/tree?company_id=99999999-9999-9999-9999-999999999999"
    )
    assert resp.status_code in (403, 404)


def test_orphan_is_surfaced_as_a_root_not_dropped():
    """A goal whose parent is absent must still appear, or the tree disagrees with the flat list."""
    orphan = _goal(_ORG, parent=uuid.uuid4(), title="Orphan", level="objective")
    roots = _client(all_goals=[orphan]).get(f"/api/llc/goals/tree?company_id={_ORG}").json()

    assert [r["title"] for r in roots] == ["Orphan"]


def test_empty_company_returns_an_empty_forest():
    resp = _client(all_goals=[]).get(f"/api/llc/goals/tree?company_id={_ORG}")
    assert resp.status_code == 200 and resp.json() == []


def test_children_endpoint_lists_direct_children():
    mission = _goal(_ORG, title="Mission", level="mission")
    objective = _goal(_ORG, parent=mission.id, title="Objective", level="objective")

    resp = _client(children=[objective], focus_goal=mission).get(f"/api/llc/goals/{mission.id}/children")

    assert resp.status_code == 200
    assert [c["title"] for c in resp.json()] == ["Objective"]


def test_children_of_a_cross_tenant_goal_is_404():
    """Tenant isolation must hold on the new read path too (GH#12136 class)."""
    foreign = _goal("99999999-9999-9999-9999-999999999999", title="Foreign")

    resp = _client(focus_goal=foreign).get(f"/api/llc/goals/{foreign.id}/children")

    assert resp.status_code == 404


def test_children_of_a_missing_goal_is_404():
    resp = _client(focus_goal=None).get(f"/api/llc/goals/{uuid.uuid4()}/children")
    assert resp.status_code == 404
