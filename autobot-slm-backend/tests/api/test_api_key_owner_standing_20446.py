# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A key is refused when its owner is deactivated or deleted (#20446, owner ruling 17).

The REAL ``get_api_key_user`` and ``_get_user_for_api_key`` run against a fake session (the
testkit one) that answers the owner lookup with a user row. The owner stands in as a small class
carrying the REAL ``UserCore.is_deleted`` property, so "deleted" is judged by the model's own
predicate and ``deleted_at`` rather than by a flag invented here. Key validation is the one stand-in
(as in ``test_api_key_route_scope_16040.py``): ``APIKey.is_valid`` judges the key, never its owner,
so a perfectly valid key is what reaches the owner lookup in every case below.
"""

import secrets
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _real_auth_import import load_real_auth  # noqa: E402
from _real_orm_import import import_modules_with_real_orm  # noqa: E402

from testkit.fake_async_session import FakeAsyncSession, FakeResult  # noqa: E402

_auth = load_real_auth(secrets.token_hex(32))
(_user_core,) = import_modules_with_real_orm(import_names=("autobot_shared.user_management.models.user",))
_KEY = "ak_test_plaintext"


class _Owner:
    """A user row: plain attributes plus the model's own ``is_deleted``."""

    is_deleted = _user_core.UserCore.is_deleted

    def __init__(self, *, is_active=True, deleted_at=None):
        self.username = "owner"
        self.is_platform_admin = False
        self.is_active = is_active
        self.deleted_at = deleted_at


@pytest.fixture
def authenticate(monkeypatch):
    monkeypatch.setattr(_auth, "audit_key_request", AsyncMock())
    monkeypatch.setattr(_auth, "_legacy_grace_or_401", AsyncMock(return_value=None))
    key = SimpleNamespace(
        id=uuid.uuid4(), user_id=uuid.uuid4(), scopes=["knowledge:read"], has_scope=lambda scope: False
    )
    service = MagicMock()
    service.return_value.validate_key = AsyncMock(return_value=key)
    for name, attr, value in (
        ("user_management.services.api_key_service", "APIKeyService", service),
        ("user_management.services.base_service", "TenantContext", MagicMock()),
    ):
        module = ModuleType(name)
        setattr(module, attr, value)
        monkeypatch.setitem(sys.modules, name, module)

    async def _authenticate(owner):
        request = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "client": ("t", 1)})
        db = FakeAsyncSession(results=[FakeResult([] if owner is None else [owner])], strict=True)
        return await _auth.get_api_key_user(request, x_api_key=_KEY, db=db)

    return _authenticate


@pytest.mark.asyncio
async def test_active_owner_is_allowed(authenticate):
    assert (await authenticate(_Owner()))["sub"] == "owner"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "owner",
    [
        pytest.param(_Owner(is_active=False), id="deactivated"),
        pytest.param(_Owner(deleted_at=datetime.now(timezone.utc)), id="soft-deleted"),
        pytest.param(_Owner(is_active=False, deleted_at=datetime.now(timezone.utc)), id="soft-delete-clears-active"),
        pytest.param(None, id="no-row"),
    ],
)
async def test_a_valid_key_of_an_unfit_owner_is_refused_401(authenticate, owner):
    with pytest.raises(HTTPException) as caught:
        await authenticate(owner)
    assert caught.value.status_code == 401
