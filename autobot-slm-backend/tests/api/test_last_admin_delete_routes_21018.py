# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SLM user delete routes answer 409, not their 404 catch-all, for the last platform admin (#21018)."""

import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from autobot_shared.user_management.last_platform_admin import LAST_PLATFORM_ADMIN_CODE, LastPlatformAdminError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _real_orm_import import import_modules_with_real_orm  # noqa: E402

_SLM_ROOT = Path(__file__).resolve().parents[2]
slm_users, autobot_users = import_modules_with_real_orm(
    ("api.slm_users", "api.autobot_users"),
    path_loaded={
        "user_management.schemas.user": _SLM_ROOT / "user_management/schemas/user.py",
        "user_management.services.autobot_database_user_service": _SLM_ROOT
        / "user_management/services/autobot_database_user_service.py",
    },
)[2:]

_ROUTES = [
    (slm_users, "delete_slm_user", "UserService"),
    (autobot_users, "delete_autobot_user", "AutobotDatabaseUserService"),
]


def _db():
    return MagicMock(commit=AsyncMock(), rollback=AsyncMock())


def _service(error):
    return MagicMock(return_value=MagicMock(delete_user=AsyncMock(side_effect=error)))


@pytest.mark.asyncio
@pytest.mark.parametrize(("module", "route", "service_name"), _ROUTES)
async def test_the_last_admin_delete_is_a_409_with_the_stable_code_and_commits_the_refusal(
    module, route, service_name, monkeypatch
):
    monkeypatch.setattr(module, service_name, _service(LastPlatformAdminError()))
    db = _db()
    with pytest.raises(HTTPException) as refused:
        await getattr(module, route)(uuid.uuid4(), {}, db)
    assert refused.value.status_code == 409 and refused.value.detail["code"] == LAST_PLATFORM_ADMIN_CODE
    db.commit.assert_awaited_once()  # the denied audit row is kept


@pytest.mark.asyncio
@pytest.mark.parametrize(("module", "route", "service_name"), _ROUTES)
async def test_any_other_delete_error_is_still_the_existing_404(module, route, service_name, monkeypatch):
    monkeypatch.setattr(module, service_name, _service(RuntimeError("boom")))
    db = _db()
    with pytest.raises(HTTPException) as failed:
        await getattr(module, route)(uuid.uuid4(), {}, db)
    assert failed.value.status_code == 404
    db.commit.assert_not_awaited()
