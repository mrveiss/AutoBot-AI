# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Card-enrichment aggregation tests for the browser list endpoints (GH#10232).

Asserts that list_portfolios / list_programs / list_company_projects attach the
aggregate counts (program_count, project_count, open_work_item_count,
active_sprint_name) to each card via a single grouped query (no N+1).
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from user_management.services import TenantContext

_USER_ID = uuid.UUID("66666666-6666-6666-6666-666666666666")
_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _portfolio(company_id):
    m = MagicMock()
    m.id = uuid.uuid4()
    m.company_id = company_id
    m.name = "PF"
    m.description = None
    m.status = "active"
    m.created_at = _NOW
    m.updated_at = _NOW
    # Real ORM rows lack the enrichment fields (Pydantic uses the default); a
    # MagicMock auto-vivifies every attr, so pin them to valid defaults.
    m.program_count = 0
    return m


def _program(company_id):
    m = _portfolio(company_id)
    m.portfolio_id = uuid.uuid4()
    m.project_count = 0
    return m


def _project(company_id):
    m = _program(company_id)
    m.program_id = uuid.uuid4()
    m.goal_id = None
    m.lead_agent_id = None
    m.lead_user_id = None
    m.target_date = None
    m.auto_rollover = None
    m.open_work_item_count = 0
    m.active_sprint_name = None
    return m


def _client(org, entities, *agg_rows):
    """Mount the sprints router with a call-sequenced session.execute:
    call 0 → the entity query (scalars().all()); calls 1.. → the grouped
    aggregate queries (.all() → list of tuples), one per *agg_rows*.
    """
    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from llc.api.sprints import router  # noqa: PLC0415
    from llc.deps import get_session  # noqa: PLC0415

    app = FastAPI()
    app.include_router(router)

    calls = {"n": 0}

    async def _execute(stmt, *a, **kw):
        result = MagicMock()
        idx = calls["n"]
        calls["n"] += 1
        if idx == 0:
            result.scalars.return_value.all.return_value = entities
        else:
            result.all.return_value = list(agg_rows[idx - 1])
        return result

    session = AsyncMock()
    session.execute = _execute

    async def _fake_session():
        yield session

    app.dependency_overrides[get_session] = _fake_session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_USER_ID)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=uuid.UUID(org), user_id=_USER_ID, is_platform_admin=False
    )
    return TestClient(app)


def test_list_portfolios_attaches_program_count():
    org = str(uuid.uuid4())
    p1, p2 = _portfolio(org), _portfolio(org)
    client = _client(org, [p1, p2], [(p1.id, 3)])  # p2 absent → 0
    resp = client.get(f"/companies/{org}/portfolios")
    assert resp.status_code == 200
    by_id = {c["id"]: c for c in resp.json()}
    assert by_id[str(p1.id)]["program_count"] == 3
    assert by_id[str(p2.id)]["program_count"] == 0


def test_list_programs_attaches_project_count():
    org = str(uuid.uuid4())
    pf_id = uuid.uuid4()
    g1 = _program(org)
    # portfolio ownership check is call 0 (scalar_one_or_none); entity list is call 1.
    # Re-wire: the endpoint runs the IDOR portfolio fetch first, so sequence differs.
    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from llc.api.sprints import router  # noqa: PLC0415
    from llc.deps import get_session  # noqa: PLC0415

    app = FastAPI()
    app.include_router(router)
    pf = _portfolio(org)

    calls = {"n": 0}

    async def _execute(stmt, *a, **kw):
        result = MagicMock()
        idx = calls["n"]
        calls["n"] += 1
        if idx == 0:  # IDOR portfolio fetch
            result.scalar_one_or_none.return_value = pf
        elif idx == 1:  # program list
            result.scalars.return_value.all.return_value = [g1]
        else:  # project_count aggregate
            result.all.return_value = [(g1.id, 7)]
        return result

    session = AsyncMock()
    session.execute = _execute

    async def _fake_session():
        yield session

    app.dependency_overrides[get_session] = _fake_session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_USER_ID)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=uuid.UUID(org), user_id=_USER_ID, is_platform_admin=False
    )
    client = TestClient(app)
    resp = client.get(f"/portfolios/{pf_id}/programs")
    assert resp.status_code == 200
    assert resp.json()[0]["project_count"] == 7


def test_list_company_projects_attaches_open_count_and_active_sprint():
    org = str(uuid.uuid4())
    pr1, pr2 = _project(org), _project(org)
    client = _client(
        org,
        [pr1, pr2],
        [(pr1.id, 5)],  # open work items: pr1=5, pr2=0
        [(pr1.id, "Sprint 7")],  # active sprint: pr1 only
    )
    resp = client.get(f"/companies/{org}/projects")
    assert resp.status_code == 200
    by_id = {c["id"]: c for c in resp.json()}
    assert by_id[str(pr1.id)]["open_work_item_count"] == 5
    assert by_id[str(pr1.id)]["active_sprint_name"] == "Sprint 7"
    assert by_id[str(pr2.id)]["open_work_item_count"] == 0
    assert by_id[str(pr2.id)]["active_sprint_name"] is None
