# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Audit and requester actors are the canonical principal id, never the mutable username (#22338).

Each test gives the caller a username that differs from its id and asserts the recorded actor is the id
(or ``service:<caller>`` for an admitted service principal).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Request

import api.admin_oauth_bundle_strip as bundle_strip
import api.admin_orphan_storage as orphan_storage_route
from api import approval_gates_approver, conversation_file_cleanup_admin, knowledge_source_liveness, memory_privacy
from api.conversation_files import _audit_file_operation
from api.quarantine_read_audit import INTERNAL_SERVICE_ACTOR, request_actor
from middleware import audit_middleware
from plugin_enable_state import _persist_and_apply

_HUMAN = {"id": "u-123", "username": "alice-renamed", "role": "admin"}
_SERVICE = {"username": "service:ci-runner", "service": True}
_NAME_ONLY = {"username": "mallory"}


def _gate_service():
    service = MagicMock()
    service.return_value.create_approval = AsyncMock(return_value=SimpleNamespace(id="a1", status="pending"))
    return service


@pytest.mark.asyncio
async def test_bundle_strip_proposal_requester_is_the_id():
    service = _gate_service()
    body = SimpleNamespace(reason="r", backup_reference="b")
    with patch.object(bundle_strip, "ApprovalGateService", service):
        await bundle_strip.propose_oauth_bundle_strip(body, _HUMAN, MagicMock())
    assert service.return_value.create_approval.await_args.kwargs["requested_by_agent"] == "u-123"


@pytest.mark.asyncio
async def test_bundle_strip_proposal_refuses_a_bare_username():
    with patch.object(bundle_strip, "ApprovalGateService", _gate_service()):
        with pytest.raises(HTTPException) as err:
            await bundle_strip.propose_oauth_bundle_strip(SimpleNamespace(reason=None), _NAME_ONLY, MagicMock())
    assert err.value.status_code == 401


@pytest.mark.asyncio
async def test_orphan_storage_proposal_requester_is_the_id_or_the_service_name():
    service = _gate_service()
    body = SimpleNamespace(provider="p", candidate_id="c", reason=None)
    with (
        patch.object(orphan_storage_route, "ApprovalGateService", service),
        patch.object(orphan_storage_route, "registered_providers", return_value=["p"]),
    ):
        await orphan_storage_route.propose_orphan_storage_deletion(body, _HUMAN, MagicMock())
        await orphan_storage_route.propose_orphan_storage_deletion(body, _SERVICE, MagicMock())
    calls = service.return_value.create_approval.await_args_list
    assert [c.kwargs["requested_by_agent"] for c in calls] == ["u-123", "service:ci-runner"]


@pytest.mark.asyncio
async def test_denied_approval_audit_records_the_id():
    approval = SimpleNamespace(id="x", context={"action": "a"})
    user = {**_HUMAN, "role": "user"}
    with (
        patch.object(approval_gates_approver, "action_needs_elevated_approver", return_value=True),
        patch.object(approval_gates_approver, "audit_log", AsyncMock()) as audit,
        pytest.raises(HTTPException),
    ):
        await approval_gates_approver.require_action_approver_role(approval, user)
    assert audit.await_args.kwargs["user_id"] == "u-123"


@pytest.mark.asyncio
async def test_source_liveness_sweep_audit_records_the_id():
    result = {"probed": 1, "outcomes": {}, "superseded": 0}
    with (
        patch.object(knowledge_source_liveness, "sweep_source_liveness", AsyncMock(return_value=result)),
        patch.object(knowledge_source_liveness, "audit_log", AsyncMock()) as audit,
    ):
        await knowledge_source_liveness.post_source_liveness_sweep(limit=5, admin=_HUMAN)
    assert audit.await_args.kwargs["user_id"] == "u-123"


@pytest.mark.asyncio
async def test_cleanup_reset_audit_records_the_id():
    mod = conversation_file_cleanup_admin
    with (
        patch.object(mod, "_manager", MagicMock()),
        patch.object(mod, "reset_cleanup_attempts", AsyncMock(return_value=True)),
        patch.object(mod, "resolve_human_user", AsyncMock(return_value=_HUMAN)),
        patch.object(mod, "audit_log", AsyncMock()) as audit,
        patch("services.conversation_file_cleanup_proposals.propose_due_cleanups_logged", AsyncMock()),
    ):
        await mod.reset_stuck_cleanup(MagicMock(spec=Request), "f1")
    assert audit.await_args.kwargs["user_id"] == "u-123"


@pytest.mark.asyncio
async def test_quarantine_read_actor_is_the_id_and_a_bare_name_is_the_service_actor():
    with patch("api.quarantine_read_audit.resolve_human_user", AsyncMock(return_value=_HUMAN)):
        assert await request_actor(MagicMock()) == "u-123"
    with patch("api.quarantine_read_audit.resolve_human_user", AsyncMock(return_value=_NAME_ONLY)):
        assert await request_actor(MagicMock()) == INTERNAL_SERVICE_ACTOR


@pytest.mark.asyncio
async def test_plugin_enable_decision_actor_is_the_id():
    store = MagicMock()
    store.put = AsyncMock()
    with patch("plugin_enable_state.audit_decision", AsyncMock()) as audit:
        await _persist_and_apply("p", True, _HUMAN, None, store)
    assert audit.await_args.args[2] == "u-123"
    assert store.put.await_args.args[0][0][3] == "u-123"


@pytest.mark.asyncio
async def test_memory_privacy_scope_and_audit_use_the_id():
    assert await memory_privacy._resolve_target_user(_HUMAN, None, MagicMock()) == "u-123"
    with pytest.raises(HTTPException) as err:
        await memory_privacy._resolve_target_user(_NAME_ONLY, None, MagicMock())
    assert err.value.status_code == 401


def test_file_operation_audit_user_is_the_id():
    layer = MagicMock()
    with patch("api.conversation_files.get_security_layer", return_value=layer):
        _audit_file_operation(MagicMock(client=None), "upload", _HUMAN, "s1", {})
    assert layer.audit_log.call_args.kwargs["user"] == "u-123"


def _request_with(user):
    return SimpleNamespace(state=SimpleNamespace(user=user), headers={})


def test_audit_middleware_actor_is_the_id():
    assert audit_middleware._extract_user(_request_with(_HUMAN)) == "u-123"
    middleware = object.__new__(audit_middleware.AuditMiddleware)
    assert middleware._get_user_from_request(_request_with(_SERVICE)) == "service:ci-runner"


def test_audit_middleware_identity_less_request_still_audits_as_anonymous():
    middleware = object.__new__(audit_middleware.AuditMiddleware)
    assert middleware._get_user_from_request(_request_with(_NAME_ONLY)) is None
    assert middleware._get_user_from_request(_request_with({})) is None
    assert audit_middleware._extract_user(_request_with(_NAME_ONLY)) is None
