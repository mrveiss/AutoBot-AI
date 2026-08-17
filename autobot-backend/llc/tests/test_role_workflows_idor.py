# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""HTTP-level proof that attaching another company's workflow is indistinguishable
from attaching a nonexistent one (#14271 review finding 3).

``test_role_workflows.py`` proves the service-layer refusal
(``RoleWorkflowService._require_workflow``) is correct — this file proves the
*route* (``POST /llc/roles/{company_id}/{role_id}/workflows``) does not
re-introduce a status-code or body differential on top of it. Mirrors
``test_workflows_idor.py``'s ``_make_client`` harness for the sibling router:
``RoleWorkflowService.attach`` is mocked to raise the exact ``ValueError``
shape the real (fixed) service now raises for each case, and the two
responses are asserted byte-for-byte identical.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from user_management.services import TenantContext

_FIXED_USER_ID = uuid.UUID("77777777-7777-7777-7777-777777777777")


def _make_client(caller_company_id: str) -> TestClient:
    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from llc.api.roles import router as roles_router  # noqa: PLC0415
    from user_management.database import get_async_session  # noqa: PLC0415

    app = FastAPI()
    app.include_router(roles_router, prefix="/api/llc")

    async def _fake_session():
        yield AsyncMock()

    app.dependency_overrides[get_async_session] = _fake_session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_FIXED_USER_ID)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=uuid.UUID(caller_company_id), user_id=_FIXED_USER_ID, is_platform_admin=False
    )
    return TestClient(app)


@pytest.fixture(autouse=True)
def _stop_patches():
    yield
    patch.stopall()


class TestAttachWorkflowIdorIndistinguishability:
    """#14271: a client must not be able to tell "belongs to another company"
    apart from "does not exist" by posting a workflow_id and reading the
    response — same status, same body, in both cases."""

    def _attach(self, company_id: str, workflow_id: str, *, service_raises: ValueError):
        client = _make_client(company_id)
        with patch(
            "llc.api.roles.RoleWorkflowService.attach",
            new=AsyncMock(side_effect=service_raises),
        ):
            role_id = uuid.uuid4()
            return client.post(
                f"/api/llc/roles/{company_id}/{role_id}/workflows",
                json={"workflow_id": workflow_id},
            )

    def test_another_companys_workflow_and_a_missing_one_get_identical_responses(self):
        company_id = str(uuid.uuid4())

        # This is the exact ValueError RoleWorkflowService._require_workflow
        # now raises for BOTH "belongs to another company" and "does not
        # exist at all" (#14271) — the route must not layer a distinction
        # back on top of a service that deliberately collapsed one.
        cross_company_response = self._attach(
            company_id, "theirs", service_raises=ValueError("workflow 'theirs' does not exist")
        )
        missing_response = self._attach(
            company_id, "nope", service_raises=ValueError("workflow 'nope' does not exist")
        )

        assert cross_company_response.status_code == missing_response.status_code == 400
        # Body text differs only in the workflow_id it echoes back (client-
        # supplied input, not tenant data) — the *shape* and every other
        # word must be identical, which is what a presence oracle would break.
        assert cross_company_response.json()["detail"].replace("theirs", "X") == missing_response.json()[
            "detail"
        ].replace("nope", "X")
