# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Org conversation review audits every transcript open and stops at the org boundary (#17832).

The org-review screen only calls ``GET /chat/sessions/{id}``; the gate and the audit trail
are ``SessionOwnershipValidator``'s. These pin the two claims the screen relies on instead of
assuming them: an org admin opening a session in their own org writes a
``conversation_accessed`` audit record naming them, and a session in another org is not
served and writes no success record.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from security.session_ownership import SessionOwnershipValidator

SESSION_ID = "0123456789abcdef0123456789abcdef"


def _validator(session_org: str) -> SessionOwnershipValidator:
    validator = SessionOwnershipValidator.__new__(SessionOwnershipValidator)
    validator.get_session_context = AsyncMock(return_value={"org_id": session_org})
    validator.is_shared_with_user = AsyncMock(return_value=False)
    validator._handle_unauthorized_access = AsyncMock(return_value={"authorized": False})
    return validator


async def _open(validator: SessionOwnershipValidator, role: str, org_id: str):
    audit = MagicMock()
    middleware = MagicMock()
    middleware.security_layer.audit_log = audit
    request = MagicMock()
    request.client.host = "203.0.113.7"
    enforcement = MagicMock(mode="enforced")
    user = {"username": "reviewer", "user_id": "u-1", "role": role, "org_id": org_id}
    with patch("security.session_ownership.get_auth_middleware", return_value=middleware):
        result = await validator._check_ownership_mismatch(
            "reviewer", SESSION_ID, "someone-else", user, request, enforcement
        )
    return result, audit


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["admin", "org_admin"])
async def test_org_admin_open_is_audit_logged_with_the_reviewer(role):
    result, audit = await _open(_validator("org-1"), role, "org-1")

    assert result["authorized"] is True
    assert result["reason"] == "org_admin"
    audit.assert_called_once()
    kwargs = audit.call_args.kwargs
    assert kwargs["action"] == "conversation_accessed"
    assert kwargs["user"] == "reviewer"
    assert kwargs["outcome"] == "success"
    assert kwargs["details"]["session_id"].startswith(SESSION_ID[:16])


@pytest.mark.asyncio
async def test_a_session_in_another_org_is_not_served_and_not_logged_as_a_success():
    validator = _validator("org-2")
    result, audit = await _open(validator, "admin", "org-1")

    assert result == {"authorized": False}
    validator._handle_unauthorized_access.assert_awaited_once()
    assert all(call.kwargs.get("action") != "conversation_accessed" for call in audit.call_args_list)


@pytest.mark.asyncio
async def test_a_non_admin_role_is_not_served_even_inside_its_own_org():
    validator = _validator("org-1")
    result, audit = await _open(validator, "user", "org-1")

    assert result == {"authorized": False}
    assert all(call.kwargs.get("action") != "conversation_accessed" for call in audit.call_args_list)
