# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Hierarchy refusals are 422, and the rule table and violation report are served (#20936, umbrella #18978)."""

import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.user_management.dependencies import get_current_user, require_org_context
from llc.api.work_item_hierarchy_routes import router as hierarchy_router
from llc.api.work_items import router as work_items_router
from llc.deps import get_session
from llc.services.work_item_hierarchy import ALLOWED_PARENT_TYPES, HierarchyViolation, ProjectRequired
from user_management.services import TenantContext

USER_ID = uuid.uuid4()
ORG = str(uuid.uuid4())
RULES = "/work-items/hierarchy-rules"
VIOLATIONS = "/work-items/hierarchy-violations"
FOUND = [
    {
        "id": str(uuid.uuid4()),
        "identifier": "WI-7",
        "code": "project_required",
        "reason": "a task has no project_id",
        "type": "task",
        "parent_type": None,
    }
]


def _client(*, org: str = ORG, role=None, platform_admin: bool = False) -> TestClient:
    app = FastAPI()
    app.include_router(hierarchy_router)  # the order llc/api/__init__.py includes them in
    app.include_router(work_items_router)
    session = AsyncMock()
    session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=role))

    async def _session():
        yield session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(USER_ID), "user_id": str(USER_ID)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=uuid.UUID(org), user_id=USER_ID, is_platform_admin=platform_admin
    )
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _stop_patches():
    yield
    patch.stopall()


def _url(client: TestClient, path: str) -> str:
    return path


# --- 422 on create and update ------------------------------------------------------------------


@pytest.mark.parametrize(
    "error, code",
    [
        (HierarchyViolation("a task cannot sit under an epic"), 422),
        (ProjectRequired("a task requires a project_id"), 422),
        (ValueError("unknown approval category"), 400),
    ],
)
def test_create_maps_a_hierarchy_breach_to_422_and_other_value_errors_to_400(error, code):
    patch("llc.services.work_item_service.WorkItemService.create", new=AsyncMock(side_effect=error)).start()
    client = _client()
    resp = client.post(_url(client, "/work-items"), json={"company_id": ORG, "type": "task", "title": "t"})
    assert resp.status_code == code, resp.text
    assert resp.json()["detail"] == str(error)


@pytest.mark.parametrize(
    "error, code",
    [
        (HierarchyViolation("a task cannot sit under an epic"), 422),
        (ProjectRequired("a task requires a project_id"), 422),
        (ValueError("unknown approval category"), 400),
    ],
)
def test_update_maps_a_hierarchy_breach_to_422_and_other_value_errors_to_400(error, code):
    existing = SimpleNamespace(company_id=ORG)
    patch("llc.services.work_item_service.WorkItemService.get", new=AsyncMock(return_value=existing)).start()
    patch("llc.services.work_item_service.WorkItemService.update", new=AsyncMock(side_effect=error)).start()
    client = _client()
    wid = str(uuid.uuid4())
    resp = client.patch(_url(client, f"/work-items/{wid}"), json={"parent_id": str(uuid.uuid4())})
    assert resp.status_code == code, resp.text


# --- GET hierarchy-rules --------------------------------------------------------------------------


def test_rules_are_served_from_the_constants_and_not_captured_by_the_id_route():
    client = _client()
    resp = client.get(_url(client, "/work-items/hierarchy-rules"), params={"company_id": ORG})
    assert resp.status_code == 200, resp.text
    served = {r["type"]: r for r in resp.json()["rules"]}
    assert set(served) == {k.value for k in ALLOWED_PARENT_TYPES}
    assert served["task"]["allowed_parent_types"] == ["pbi"]
    assert served["epic"]["allowed_parent_types"] == []
    assert all(r["project_required"] for r in served.values())


def test_rules_for_another_company_match_the_list_route_status():
    client = _client()
    other = str(uuid.uuid4())
    listed = client.get(_url(client, "/work-items"), params={"company_id": other})
    resp = client.get(_url(client, "/work-items/hierarchy-rules"), params={"company_id": other})
    assert resp.status_code == listed.status_code == 404


# --- GET hierarchy-violations ---------------------------------------------------------------------


def _violations(client: TestClient, company: str = ORG):
    return client.get(_url(client, "/work-items/hierarchy-violations"), params={"company_id": company})


def _report_mock():
    return patch(
        "llc.api.work_item_hierarchy_routes.find_hierarchy_violations", new=AsyncMock(return_value=(FOUND, False))
    ).start()


def test_a_plain_member_gets_403_and_no_report_is_read():
    report = _report_mock()
    assert _violations(_client(role="member")).status_code == 403
    report.assert_not_called()


def test_a_non_member_gets_403():
    assert _violations(_client(role=None)).status_code == 403


@pytest.mark.parametrize("role", ["owner", "admin"])
def test_a_company_owner_or_admin_gets_the_report(role):
    _report_mock()
    resp = _violations(_client(role=role))
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"violations": FOUND, "count": 1, "truncated": False}


def test_a_platform_admin_gets_the_report_without_a_membership():
    _report_mock()
    assert _violations(_client(role=None, platform_admin=True)).status_code == 200


def test_the_report_for_another_company_matches_the_list_route_status():
    report = _report_mock()
    client = _client(role="admin")
    other = str(uuid.uuid4())
    listed = client.get(_url(client, "/work-items"), params={"company_id": other})
    assert _violations(client, other).status_code == listed.status_code == 404
    report.assert_not_called()


# --- route order ----------------------------------------------------------------------------------


def test_the_package_includes_the_hierarchy_router_before_the_work_items_router():
    source = (Path(__file__).resolve().parents[1] / "api" / "__init__.py").read_text(encoding="utf-8")
    first = source.index("router.include_router(work_item_hierarchy_router)")
    assert first < source.index("router.include_router(work_items_router)")
