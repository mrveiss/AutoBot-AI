# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#22180: the per-workflow ACL subject is the principal id, never the mutable username."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from services import workflow_rbac

_GRANTS = {("wf-1", "id-alice"): "viewer"}  # alice's grant, keyed by her user id


class _Store:
    """The grant table as the service sees it: (workflow, subject) -> role."""

    def __init__(self, session) -> None:
        self.session = session

    async def check_permission(self, user_id: str, workflow_id: str, action: str) -> bool:
        return _GRANTS.get((workflow_id, user_id)) is not None and action == "view"


async def _check(user: dict) -> bool:
    request = SimpleNamespace(path_params={"workflow_id": "wf-1"})
    dependency = workflow_rbac.require_workflow_permission("view")
    with patch.object(workflow_rbac, "WorkflowPermissionService", _Store):
        return await dependency(request, user, object())


async def test_a_renamed_user_keeps_their_grant() -> None:
    assert await _check({"id": "id-alice", "username": "alice-renamed", "role": "user"}) is True


async def test_a_user_renamed_to_another_username_gains_nothing() -> None:
    with pytest.raises(HTTPException) as refused:
        await _check({"id": "id-mallory", "username": "alice", "role": "user"})
    assert refused.value.status_code == 403


async def test_an_identity_less_caller_is_a_401_not_the_empty_subject() -> None:
    with pytest.raises(HTTPException) as refused:
        await _check({"username": "alice", "role": "user"})
    assert refused.value.status_code == 401
