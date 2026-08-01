# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Auth + IDOR hardening tests for review_gate_policies.py routes (GH#12148).

Prior to this fix every handler in llc/api/review_gate_policies.py depended
only on ``get_session`` — no authentication and no tenant-authorization —
allowing an unauthenticated caller to read/create/update/delete review-gate
policies for ANY company. The mutators key on ``policy_id`` alone, so a caller
could also pass their own ``company_id`` in the path while targeting another
company's ``policy_id`` (IDOR). Policy config is a user-facing admin action.

  - no auth at all                            -> 401
  - authenticated, cross-tenant company_id    -> 404
  - authenticated, policy owned by other org  -> 404
  - authenticated, same-tenant                -> success
"""

import uuid
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from user_management.services import TenantContext

_FIXED_USER_ID = uuid.UUID("66666666-6666-6666-6666-666666666666")
_OTHER_ORG = "99999999-9999-9999-9999-999999999999"


def _make_policy(company_id: str) -> MagicMock:
    now = datetime.now(timezone.utc)
    policy = MagicMock()
    policy.id = uuid.uuid4()
    policy.company_id = uuid.UUID(company_id)
    policy.item_type = "task"
    policy.requires_human_review = True
    policy.reviewer_role = None
    policy.requires_cross_vendor_review = False
    policy.created_at = now
    policy.updated_at = now
    return policy


def _make_client(
    caller_org_id: str,
    policy_company_id: Optional[str] = None,
    policy_exists: bool = True,
    is_platform_admin: bool = False,
) -> TestClient:
    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from llc.api.review_gate_policies import router as rgp_router  # noqa: PLC0415
    from llc.deps import get_session  # noqa: PLC0415

    app = FastAPI()
    app.include_router(rgp_router, prefix="/api/llc")

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()

    async def _fake_session():
        yield mock_session

    app.dependency_overrides[get_session] = _fake_session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_FIXED_USER_ID)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=uuid.UUID(caller_org_id), user_id=_FIXED_USER_ID, is_platform_admin=is_platform_admin
    )

    pcid = policy_company_id if policy_company_id is not None else caller_org_id
    policy = _make_policy(pcid) if policy_exists else None

    patch(
        "llc.api.review_gate_policies.ReviewGatePolicyService.list_policies",
        new=AsyncMock(return_value=[policy] if policy else []),
    ).start()
    patch(
        "llc.api.review_gate_policies.ReviewGatePolicyService.create_policy", new=AsyncMock(return_value=policy)
    ).start()
    patch(
        "llc.api.review_gate_policies.ReviewGatePolicyService.get_policy_by_id", new=AsyncMock(return_value=policy)
    ).start()
    patch(
        "llc.api.review_gate_policies.ReviewGatePolicyService.update_policy", new=AsyncMock(return_value=policy)
    ).start()
    patch(
        "llc.api.review_gate_policies.ReviewGatePolicyService.delete_policy", new=AsyncMock(return_value=True)
    ).start()

    return TestClient(app)


@pytest.fixture(autouse=True)
def _stop_patches():
    yield
    patch.stopall()


def _base(org: str) -> str:
    return f"/api/llc/companies/{org}/review-gate-policies"


class TestReviewGatePoliciesNoAuth:
    def _make_unauthenticated_client(self) -> TestClient:
        from llc.api.review_gate_policies import router as rgp_router
        from llc.deps import get_session

        app = FastAPI()
        app.include_router(rgp_router, prefix="/api/llc")

        async def _fake_session():
            yield AsyncMock()

        app.dependency_overrides[get_session] = _fake_session
        return TestClient(app)

    def test_list_no_token_returns_401(self):
        with patch("api.user_management.dependencies.get_auth_middleware") as mock_mw:
            mock_mw.return_value.get_user_from_request.return_value = None
            client = self._make_unauthenticated_client()
            resp = client.get(_base(str(uuid.uuid4())))
        assert resp.status_code == 401

    def test_delete_no_token_returns_401(self):
        with patch("api.user_management.dependencies.get_auth_middleware") as mock_mw:
            mock_mw.return_value.get_user_from_request.return_value = None
            client = self._make_unauthenticated_client()
            resp = client.delete(f"{_base(str(uuid.uuid4()))}/{uuid.uuid4()}")
        assert resp.status_code == 401


class TestReviewGatePoliciesIdor:
    # --- list ---

    def test_list_own_company_returns_200(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.get(_base(org))
        assert resp.status_code == 200

    def test_list_cross_tenant_returns_404(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.get(_base(_OTHER_ORG))
        assert resp.status_code == 404

    def test_list_platform_admin_cross_tenant_allowed(self):
        org = str(uuid.uuid4())
        client = _make_client(org, is_platform_admin=True)
        resp = client.get(_base(_OTHER_ORG))
        assert resp.status_code == 200

    # --- create ---

    def test_create_own_company_returns_201(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.post(_base(org), json={"item_type": "task", "requires_human_review": True})
        assert resp.status_code == 201

    def test_create_cross_tenant_returns_404(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.post(_base(_OTHER_ORG), json={"item_type": "task"})
        assert resp.status_code == 404

    # --- update (id-keyed IDOR) ---

    def test_update_own_tenant_returns_200(self):
        org = str(uuid.uuid4())
        client = _make_client(org, policy_company_id=org)
        resp = client.patch(f"{_base(org)}/{uuid.uuid4()}", json={"requires_human_review": False})
        assert resp.status_code == 200

    def test_update_cross_tenant_company_returns_404(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.patch(f"{_base(_OTHER_ORG)}/{uuid.uuid4()}", json={"requires_human_review": False})
        assert resp.status_code == 404

    def test_update_policy_owned_by_other_org_returns_404(self):
        # company_id in path matches caller, but the policy belongs to a
        # different company -> IDOR must be rejected.
        org = str(uuid.uuid4())
        client = _make_client(org, policy_company_id=_OTHER_ORG)
        resp = client.patch(f"{_base(org)}/{uuid.uuid4()}", json={"requires_human_review": False})
        assert resp.status_code == 404

    def test_update_policy_not_found_returns_404(self):
        org = str(uuid.uuid4())
        client = _make_client(org, policy_exists=False)
        resp = client.patch(f"{_base(org)}/{uuid.uuid4()}", json={"requires_human_review": False})
        assert resp.status_code == 404

    # --- delete (id-keyed IDOR) ---

    def test_delete_own_tenant_returns_204(self):
        org = str(uuid.uuid4())
        client = _make_client(org, policy_company_id=org)
        resp = client.delete(f"{_base(org)}/{uuid.uuid4()}")
        assert resp.status_code == 204

    def test_delete_policy_owned_by_other_org_returns_404(self):
        org = str(uuid.uuid4())
        client = _make_client(org, policy_company_id=_OTHER_ORG)
        resp = client.delete(f"{_base(org)}/{uuid.uuid4()}")
        assert resp.status_code == 404
