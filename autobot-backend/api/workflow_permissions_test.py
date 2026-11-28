# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#22180: grants take a user id, a name is resolved once server-side, and the remap is only proposed."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api import workflow_permissions as route
from api.schemas_workflows import GrantPermissionRequest

_ADMIN = {"id": "admin-id", "username": "root", "role": "admin"}


def _perm() -> SimpleNamespace:
    return SimpleNamespace(
        workflow_id="wf", user_id="u-1", role="viewer", granted_by="admin-id", created_at=None, updated_at=None
    )


async def _grant(ref: str, resolved: str | None):
    svc = MagicMock()
    svc.grant_permission = AsyncMock(return_value=_perm())
    svc.log_action = AsyncMock()
    with (
        patch.object(route, "resolve_user_ref", AsyncMock(return_value=resolved)),
        patch.object(route, "WorkflowPermissionService", return_value=svc),
    ):
        body = GrantPermissionRequest(user_id=ref, role="viewer")
        await route.grant_workflow_permission("wf", body, _ADMIN, MagicMock(), True)
    return svc


async def test_a_grant_by_name_is_stored_under_the_resolved_id() -> None:
    svc = await _grant("alice", "u-1")
    assert svc.grant_permission.await_args.kwargs["user_id"] == "u-1"
    assert svc.grant_permission.await_args.kwargs["granted_by"] == "admin-id"


async def test_a_grant_to_an_unknown_name_is_refused_and_stores_nothing() -> None:
    with pytest.raises(HTTPException) as refused:
        await _grant("nobody", None)
    assert refused.value.status_code == 422


async def test_an_identity_less_admin_cannot_grant() -> None:
    with pytest.raises(HTTPException) as refused:
        await route.grant_workflow_permission(
            "wf",
            GrantPermissionRequest(user_id="a", role="viewer"),
            {"username": "root", "role": "admin"},
            MagicMock(),
            True,
        )
    assert refused.value.status_code == 401


async def _propose(mappings, unmapped, user=_ADMIN):
    gate = MagicMock()
    gate.return_value.create_approval = AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4(), status="pending"))
    audit = AsyncMock(return_value=True)
    with (
        patch.object(route, "plan_remap", AsyncMock(return_value=(mappings, unmapped))),
        patch.object(route, "ApprovalGateService", gate),
        patch("services.kb_cleanup_proposals.audit_log", audit),
        patch("services.kb_cleanup_proposals.find_pending_proposal", AsyncMock(return_value=None)),
    ):
        response = await route.propose_grant_subject_remap(user, MagicMock())
    return response, gate, audit


async def test_the_proposal_audits_intent_creates_a_pending_approval_and_rewrites_nothing() -> None:
    mapping = {"permission_id": "p1", "workflow_id": "wf", "old": "alice", "new": "u-1"}
    unmapped = [{"permission_id": "p2", "workflow_id": "wf", "old": "ghost"}]
    response, gate, audit = await _propose([mapping], unmapped)
    kwargs = gate.return_value.create_approval.await_args.kwargs
    assert kwargs["context"]["mappings"] == [mapping]
    assert "ghost (wf)" in kwargs["description"]  # unmapped rows are reported in the proposal text
    assert audit.await_args.args[0] == "workflow.grant_remap_proposed"
    assert (response.mapped, response.status, response.unmapped[0].subject) == (1, "pending", "ghost")


async def test_a_proposal_with_nothing_mappable_is_refused() -> None:
    with pytest.raises(HTTPException) as refused:
        await _propose([], [{"permission_id": "p2", "workflow_id": "wf", "old": "ghost"}])
    assert refused.value.status_code == 409
