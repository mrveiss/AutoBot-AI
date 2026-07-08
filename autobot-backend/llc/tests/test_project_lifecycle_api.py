# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Archive→dispose lifecycle endpoints (#11129 P2)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from user_management.services import TenantContext

_USER = uuid.UUID("77777777-7777-7777-7777-777777777777")


def _mk_client(project):
    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from llc.api.sprints import router  # noqa: PLC0415
    from llc.deps import get_session  # noqa: PLC0415

    app = FastAPI()
    app.include_router(router)
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = project
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()

    async def _sess():
        yield session

    app.dependency_overrides[get_session] = _sess
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_USER)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=project.company_id, user_id=_USER, is_platform_admin=False
    )
    return TestClient(app), session


def _project(lifecycle="active"):
    from datetime import datetime, timezone  # noqa: PLC0415

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    org = uuid.uuid4()
    p = MagicMock()
    p.id = uuid.uuid4()
    p.company_id = org
    p.lifecycle_state = lifecycle
    p.code_source_id = None
    p.code_source = None
    # Pin all ProjectResponse fields so model_validate doesn't choke on Mocks.
    p.program_id = None
    p.goal_id = None
    p.name = "Test Project"
    p.description = None
    p.status = "active"
    p.lead_agent_id = None
    p.lead_user_id = None
    p.target_date = None
    p.auto_rollover = None
    p.created_at = now
    p.updated_at = now
    p.open_work_item_count = 0
    p.active_sprint_name = None
    p.archived_at = None
    p.disposal_scheduled_at = None
    p.disposal_approval_id = None
    return p


def test_archive_sets_state():
    p = _project("active")
    client, _ = _mk_client(p)
    resp = client.post(f"/projects/{p.id}/archive")
    assert resp.status_code == 200
    assert p.lifecycle_state == "archived"


def test_dispose_requires_archived():
    p = _project("active")
    client, _ = _mk_client(p)
    resp = client.post(f"/projects/{p.id}/dispose")
    assert resp.status_code == 409


def test_delete_requires_archived():
    p = _project("active")
    client, _ = _mk_client(p)
    resp = client.request("DELETE", f"/projects/{p.id}")
    assert resp.status_code == 409


def test_dispose_immediate_when_policy_default():
    p = _project("archived")
    client, _ = _mk_client(p)
    with (
        patch("llc.api.sprints.get_disposal_policy", AsyncMock(return_value=_policy(0, False))),
        patch("llc.api.sprints.dispose", AsyncMock()) as disp,
    ):
        resp = client.post(f"/projects/{p.id}/dispose")
    assert resp.status_code == 200
    disp.assert_awaited_once()
    assert resp.json()["result"] == "disposed"


def test_dispose_schedules_when_retention():
    p = _project("archived")
    client, _ = _mk_client(p)
    with (
        patch("llc.api.sprints.get_disposal_policy", AsyncMock(return_value=_policy(7, False))),
        patch("llc.api.sprints.dispose", AsyncMock()) as disp,
    ):
        resp = client.post(f"/projects/{p.id}/dispose")
    assert resp.status_code == 200
    disp.assert_not_awaited()
    assert resp.json()["result"] == "scheduled"
    assert p.lifecycle_state == "pending_disposal"


def test_dispose_pending_approval_when_policy_requires_it():
    from types import SimpleNamespace  # noqa: PLC0415

    p = _project("archived")
    client, _ = _mk_client(p)
    approval_id = uuid.uuid4()
    fake_svc = MagicMock()
    fake_svc.request_approval = AsyncMock(return_value=SimpleNamespace(id=approval_id))
    fake_svc.publish_requested = AsyncMock()
    with (
        patch("llc.api.sprints.get_disposal_policy", AsyncMock(return_value=_policy(0, True))),
        patch("llc.api.sprints.dispose", AsyncMock()) as disp,
        patch("llc.api.sprints._approval_svc", fake_svc),
    ):
        resp = client.post(f"/projects/{p.id}/dispose")
    assert resp.status_code == 200
    disp.assert_not_awaited()
    body = resp.json()
    assert body["result"] == "pending_approval"
    assert body["approval_id"] == str(approval_id)
    assert p.lifecycle_state == "pending_disposal"
    assert p.disposal_approval_id == approval_id
    fake_svc.request_approval.assert_awaited_once()
    fake_svc.publish_requested.assert_awaited_once()


def _policy(days, approval):
    from llc.services.disposal_policy import DisposalPolicy  # noqa: PLC0415

    return DisposalPolicy(retention_days=days, require_approval=approval)
