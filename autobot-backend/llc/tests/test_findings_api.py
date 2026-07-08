# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Findings API endpoint tests — scan/proposals/promote/dismiss (#11271).

Mirrors the TestClient + dependency_overrides pattern from test_project_lifecycle_api.py.
"""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from user_management.services import TenantContext

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ORG_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
_USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
_PROJECT_ID = uuid.uuid4()
_PROPOSAL_ID = uuid.uuid4()
_OTHER_ORG_ID = uuid.UUID("99999999-9999-9999-9999-999999999999")

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _mk_project(*, code_source_id="src-001", company_id=_ORG_ID):
    p = MagicMock()
    p.id = _PROJECT_ID
    p.company_id = company_id
    p.code_source_id = code_source_id
    p.program_id = None
    p.goal_id = None
    p.name = "Test"
    p.description = None
    p.status = "active"
    p.lead_agent_id = None
    p.lead_user_id = None
    p.target_date = None
    p.auto_rollover = None
    p.lifecycle_state = "active"
    p.archived_at = None
    p.disposal_scheduled_at = None
    p.disposal_approval_id = None
    p.open_work_item_count = 0
    p.active_sprint_name = None
    p.created_at = _NOW
    p.updated_at = _NOW
    return p


def _mk_proposal(*, status="pending", company_id=_ORG_ID, project_id=_PROJECT_ID):
    from llc.models.enums import FindingProposalStatus  # noqa: PLC0415

    prop = MagicMock()
    prop.id = _PROPOSAL_ID
    prop.company_id = company_id
    prop.project_id = project_id
    prop.source_id = "src-001"
    prop.finding_key = "src-001:main.py:10:bug"
    prop.finding_type = "bug"
    prop.severity = "high"
    prop.file_path = "main.py"
    prop.line_number = 10
    prop.description = "a bug"
    prop.suggestion = "fix it"
    prop.verdict_is_real = True
    prop.verdict_confidence = 0.9
    prop.verdict_rationale = "looks real"
    prop.status = FindingProposalStatus.PENDING if status == "pending" else status
    prop.work_item_id = None
    prop.dismiss_reason = None
    prop.created_at = _NOW
    prop.updated_at = _NOW
    return prop


def _mk_client(project, proposals=None):
    """Build a TestClient wired to the findings router."""
    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from llc.api.findings import router  # noqa: PLC0415
    from llc.deps import get_session  # noqa: PLC0415

    app = FastAPI()
    app.include_router(router)

    session = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()

    # Wire execute() to return project for project lookups and proposals for proposal lookups
    def _make_result(entity, is_list=False):
        result = MagicMock()
        if is_list:
            sc = MagicMock()
            sc.all = MagicMock(return_value=entity or [])
            result.scalars = MagicMock(return_value=sc)
        else:
            result.scalar_one_or_none = MagicMock(return_value=entity)
        return result

    async def _execute(stmt, *args, **kwargs):
        stmt_str = str(stmt).lower()
        if "llc_finding_proposals" in stmt_str:
            # List query (scalars) vs single-row (scalar_one_or_none)
            if proposals is not None and "select" in stmt_str:
                # If filtering by id (single) or project_id (list)
                try:
                    params = stmt.compile().params
                    param_vals = set(str(v) for v in params.values())
                except Exception:
                    param_vals = set()
                if str(_PROPOSAL_ID) in param_vals:
                    return _make_result(proposals[0] if proposals else None)
                return _make_result(proposals, is_list=True)
            return _make_result(proposals[0] if proposals else None)
        # Default: return project
        return _make_result(project)

    session.execute = _execute

    async def _sess():
        yield session

    app.dependency_overrides[get_session] = _sess
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_USER_ID)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=project.company_id, user_id=_USER_ID, is_platform_admin=False
    )
    return TestClient(app), session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_scan_403_when_policy_disabled():
    """POST /projects/{id}/findings/scan → 403 when policy.enabled=False."""
    from llc.services.findings_policy import FindingsPolicy  # noqa: PLC0415

    project = _mk_project()
    client, _ = _mk_client(project)
    with patch("llc.api.findings.get_findings_policy", AsyncMock(return_value=FindingsPolicy(enabled=False))):
        resp = client.post(f"/projects/{project.id}/findings/scan")
    assert resp.status_code == 403


def test_scan_409_when_no_code_source_id():
    """POST /projects/{id}/findings/scan → 409 when project has no code_source_id."""
    from llc.services.findings_policy import FindingsPolicy  # noqa: PLC0415

    project = _mk_project(code_source_id=None)
    client, _ = _mk_client(project)
    with patch("llc.api.findings.get_findings_policy", AsyncMock(return_value=FindingsPolicy(enabled=True))):
        resp = client.post(f"/projects/{project.id}/findings/scan")
    assert resp.status_code == 409


def test_scan_success_returns_counts():
    """POST /projects/{id}/findings/scan → 200 with gathered/verified_real/queued."""
    from llc.services.findings_policy import FindingsPolicy  # noqa: PLC0415

    project = _mk_project(code_source_id="src-001")
    client, _ = _mk_client(project)
    counts = {"gathered": 5, "verified_real": 3, "queued": 3}
    with (
        patch("llc.api.findings.get_findings_policy", AsyncMock(return_value=FindingsPolicy(enabled=True))),
        patch("llc.api.findings.scan", AsyncMock(return_value=counts)),
    ):
        resp = client.post(f"/projects/{project.id}/findings/scan")
    assert resp.status_code == 200
    assert resp.json() == counts


def test_list_proposals_returns_proposals():
    """GET /projects/{id}/findings/proposals → 200 with proposal list."""
    project = _mk_project()
    proposal = _mk_proposal()
    client, _ = _mk_client(project, proposals=[proposal])
    resp = client.get(f"/projects/{project.id}/findings/proposals")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["finding_type"] == "bug"


def test_list_proposals_filter_by_status():
    """GET /projects/{id}/findings/proposals?status=pending → 200."""
    project = _mk_project()
    proposal = _mk_proposal()
    client, _ = _mk_client(project, proposals=[proposal])
    resp = client.get(f"/projects/{project.id}/findings/proposals?status=pending")
    assert resp.status_code == 200


def test_promote_calls_service():
    """POST /findings/proposals/{id}/promote → 200; service invoked."""
    project = _mk_project()
    proposal = _mk_proposal()
    client, _ = _mk_client(project, proposals=[proposal])
    fake_item = SimpleNamespace(
        id=uuid.uuid4(),
        identifier="LLC-1",
        title="title",
        type="bug",
        status="open",
        description="desc",
        priority="high",
        project_id=_PROJECT_ID,
        company_id=_ORG_ID,
        created_at=_NOW,
        updated_at=_NOW,
        assignee_agent_id=None,
        assignee_user_id=None,
        sprint_id=None,
        story_points=None,
        labels=[],
        scheduled_start=None,
        scheduled_end=None,
        started_at=None,
        completed_at=None,
        due_date=None,
        estimated_hours=None,
        actual_hours=None,
        comment_count=0,
    )
    with patch("llc.api.findings.promote", AsyncMock(return_value=fake_item)):
        resp = client.post(f"/findings/proposals/{proposal.id}/promote")
    assert resp.status_code == 200


def test_dismiss_calls_service():
    """POST /findings/proposals/{id}/dismiss {reason} → 200."""
    project = _mk_project()
    proposal = _mk_proposal()
    client, _ = _mk_client(project, proposals=[proposal])
    with patch("llc.api.findings.dismiss", AsyncMock(return_value=None)):
        resp = client.post(f"/findings/proposals/{proposal.id}/dismiss", json={"reason": "not applicable"})
    assert resp.status_code == 200


def test_dismiss_requires_reason():
    """POST /findings/proposals/{id}/dismiss with missing reason → 422."""
    project = _mk_project()
    proposal = _mk_proposal()
    client, _ = _mk_client(project, proposals=[proposal])
    with patch("llc.api.findings.dismiss", AsyncMock(return_value=None)):
        resp = client.post(f"/findings/proposals/{proposal.id}/dismiss", json={})
    assert resp.status_code == 422


def test_scan_idor_404_wrong_org():
    """POST /projects/{id}/findings/scan → 404 when project.company_id != ctx.org_id."""
    from llc.services.findings_policy import FindingsPolicy  # noqa: PLC0415

    project = _mk_project(company_id=_OTHER_ORG_ID)
    project2 = _mk_project(company_id=_ORG_ID)  # client is wired to _ORG_ID
    client, _ = _mk_client(project2, proposals=[])

    # Override execute to return the project owned by OTHER org
    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from llc.api.findings import router  # noqa: PLC0415
    from llc.deps import get_session  # noqa: PLC0415

    app = FastAPI()
    app.include_router(router)
    session = AsyncMock()

    async def _execute(stmt, *args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=project)
        return result

    session.execute = _execute

    async def _sess():
        yield session

    app.dependency_overrides[get_session] = _sess
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_USER_ID)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=_ORG_ID, user_id=_USER_ID, is_platform_admin=False
    )
    idor_client = TestClient(app)

    with patch("llc.api.findings.get_findings_policy", AsyncMock(return_value=FindingsPolicy(enabled=True))):
        resp = idor_client.post(f"/projects/{project.id}/findings/scan")
    assert resp.status_code == 404
