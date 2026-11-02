# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#10200: the first admin, password hash included, goes only to a holder of the internal key."""

import importlib.util
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

_SPEC = importlib.util.spec_from_file_location(
    "_first_admin_internal", Path(__file__).parents[2] / "api" / "first_admin_internal.py"
)
route = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(route)


def _session(admin):
    found = MagicMock()
    found.scalars.return_value.first.return_value = admin
    return SimpleNamespace(execute=AsyncMock(return_value=found))


async def _get(admin, key_ok=True):
    with patch.object(route, "verify_internal_api_key", return_value=key_ok):
        return await route.get_first_admin(_session(admin), "key")


@pytest.mark.asyncio
async def test_without_the_internal_key_nothing_is_read():
    session = _session("admin")
    with patch.object(route, "verify_internal_api_key", return_value=False), pytest.raises(HTTPException) as refused:
        await route.get_first_admin(session, None)
    assert refused.value.status_code == 403
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_key_holder_gets_the_admin():
    assert await _get("admin") == "admin"


@pytest.mark.asyncio
async def test_an_slm_without_an_admin_says_so():
    with pytest.raises(HTTPException) as missing:
        await _get(None)
    assert missing.value.status_code == 404


def _copy_body(is_active=False):
    return route.PersonCopyRequest(slm_user_id=uuid.uuid4(), password_hash="new", is_active=is_active)


@pytest.mark.asyncio
async def test_a_person_copy_needs_the_internal_key():
    session = SimpleNamespace(get=AsyncMock(), commit=AsyncMock())
    with patch.object(route, "verify_internal_api_key", return_value=False), pytest.raises(HTTPException) as refused:
        await route.update_person_copy(_copy_body(), session, None)
    assert refused.value.status_code == 403
    session.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_person_copy_updates_password_and_deactivates():
    user = SimpleNamespace(password_hash="old", is_active=True)
    session = SimpleNamespace(get=AsyncMock(return_value=user), commit=AsyncMock())
    with patch.object(route, "verify_internal_api_key", return_value=True):
        await route.update_person_copy(_copy_body(), session, "key")
    assert (user.password_hash, user.is_active) == ("new", False)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_person_copy_for_nobody_is_a_404():
    session = SimpleNamespace(get=AsyncMock(return_value=None), commit=AsyncMock())
    with patch.object(route, "verify_internal_api_key", return_value=True), pytest.raises(HTTPException) as missing:
        await route.update_person_copy(_copy_body(), session, "key")
    assert missing.value.status_code == 404
