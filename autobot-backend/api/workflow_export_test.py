# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#22181: unshare and export apply the owner-or-admin check the other workflow routes apply."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api import workflow_export as route

_OWNER = {"id": "u-owner", "role": "user"}
_OTHER = {"id": "u-other", "role": "user"}
_ADMIN = {"id": "u-admin", "role": "admin"}


def _sharing(stored_owner: str | None) -> MagicMock:
    sharing = MagicMock()
    sharing.get_share_owner = AsyncMock(return_value=stored_owner)
    sharing.unshare_workflow = AsyncMock(return_value=True)
    return sharing


async def test_the_share_owner_revokes_the_share() -> None:
    sharing = _sharing("u-owner")
    assert (await route.unshare_workflow("s1", _OWNER, sharing))["success"] is True
    sharing.unshare_workflow.assert_awaited_once_with("s1")


async def test_an_admin_revokes_any_share() -> None:
    assert (await route.unshare_workflow("s1", _ADMIN, _sharing("u-owner")))["success"] is True


async def test_a_non_owner_is_refused_and_the_share_survives() -> None:
    sharing = _sharing("u-owner")
    with pytest.raises(HTTPException) as refused:
        await route.unshare_workflow("s1", _OTHER, sharing)
    assert refused.value.status_code == 403
    sharing.unshare_workflow.assert_not_awaited()


async def test_a_missing_share_is_a_404() -> None:
    with pytest.raises(HTTPException) as refused:
        await route.unshare_workflow("s1", _OWNER, _sharing(None))
    assert refused.value.status_code == 404


async def test_an_identity_less_caller_cannot_unshare() -> None:
    with pytest.raises(HTTPException) as refused:
        await route.unshare_workflow("s1", {"username": "x", "role": "user"}, _sharing("u-owner"))
    assert refused.value.status_code == 401


def _manager() -> SimpleNamespace:
    workflow = SimpleNamespace(owner_id="u-owner", workflow_id="wf")
    return SimpleNamespace(active_workflows={"wf": workflow}, completed_workflows={})


async def _export(user: dict):
    serializer = MagicMock()
    serializer.export_workflow = AsyncMock(return_value=MagicMock(to_dict=MagicMock(return_value={"k": 1})))
    with patch.object(route, "get_workflow_manager", return_value=_manager()):
        return await route.export_workflow("wf", user, serializer), serializer


async def test_the_workflow_owner_and_an_admin_may_export() -> None:
    for user in (_OWNER, _ADMIN):
        result, _ = await _export(user)
        assert result == {"success": True, "export": {"k": 1}}


async def test_a_non_owner_is_refused_before_anything_is_serialised() -> None:
    serializer = MagicMock()
    serializer.export_workflow = AsyncMock()
    with patch.object(route, "get_workflow_manager", return_value=_manager()):
        with pytest.raises(HTTPException) as refused:
            await route.export_workflow("wf", _OTHER, serializer)
    assert refused.value.status_code == 403
    serializer.export_workflow.assert_not_awaited()


async def test_an_identity_less_caller_cannot_export() -> None:
    with pytest.raises(HTTPException) as refused:
        await route.export_workflow("wf", {"username": "x", "role": "user"}, MagicMock())
    assert refused.value.status_code == 401
