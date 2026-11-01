# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A user deprovisioned through the SLM's user service loses the tokens already issued (#20443).

A real HS256 token goes through the real ``decode_token_async``; the user is deactivated or
soft-deleted through the SLM's ``UserService`` lifecycle (the one SCIM ``PATCH active:false`` and
``DELETE`` call). Only storage is stood in for: the epoch store, the jti denylist, the session.
"""

import importlib
import re
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.db_session import POST_COMMIT_CALLBACKS, _run_post_commit_callbacks
from autobot_shared.user_management import password_epoch
from autobot_shared.user_management.base_service import TenantContext

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
from _real_auth_import import load_real_auth  # noqa: E402

# The slm-backend conftest stubs ``sqlalchemy``; the shared service needs the real package only while it is imported.
_STUBBED = {n: m for n, m in sys.modules.items() if n == "sqlalchemy" or n.startswith("sqlalchemy.")}
for _name in _STUBBED:
    del sys.modules[_name]
try:
    UserService = importlib.import_module("autobot_shared.user_management.user_service").UserService
finally:
    for _name in [n for n in sys.modules if n == "sqlalchemy" or n.startswith("sqlalchemy.")]:
        del sys.modules[_name]
    sys.modules.update(_STUBBED)

_REAL_AUTH = load_real_auth("s" * 40, expire_minutes=60 * 24)
auth_service = _REAL_AUTH.auth_service


class _SlmUserService(UserService):
    """What the SLM's ``UserService`` adds is only the bound model; the lifecycle is the shared one."""

    user_model = MagicMock()


@pytest.fixture()
def epochs():
    store: dict[str, int] = {}

    async def get_epoch(subject):
        return store.get(subject)

    async def set_epoch(subject, *, now=None):
        store[subject] = int(time.time()) if now is None else now
        return store[subject]

    password_epoch.use_epoch_store(get_epoch=get_epoch, set_epoch=set_epoch)
    with patch.object(_REAL_AUTH, "is_jti_revoked", AsyncMock(return_value=False)):
        yield store
    password_epoch.reset_epoch_store()


def _token(age_seconds: int = 60) -> str:
    return auth_service.create_access_token({"sub": "alice", "iat": int(time.time()) - age_seconds})


def _service() -> _SlmUserService:
    session = MagicMock(flush=AsyncMock())
    session.info = {POST_COMMIT_CALLBACKS: []}
    svc = _SlmUserService(session, TenantContext(is_platform_admin=True))
    svc.get_user = AsyncMock(return_value=SimpleNamespace(username="alice", is_active=True, deleted_at=None))
    svc._audit_log = AsyncMock()
    return svc


@pytest.mark.asyncio
async def test_a_live_users_token_decodes(epochs):
    assert (await auth_service.decode_token_async(_token()))["sub"] == "alice"


@pytest.mark.asyncio
async def test_a_scim_deactivated_users_token_is_refused(epochs):
    token = _token()
    service = _service()
    await service.deactivate_user(uuid.uuid4())
    assert (await auth_service.decode_token_async(token))["sub"] == "alice", "nothing is written before the commit"
    await _run_post_commit_callbacks(service.session)

    assert await auth_service.decode_token_async(token) is None


@pytest.mark.asyncio
async def test_a_scim_deleted_users_token_is_refused(epochs):
    token = _token()
    service = _service()
    await service.delete_user(uuid.uuid4(), hard_delete=False)
    await _run_post_commit_callbacks(service.session)

    assert await auth_service.decode_token_async(token) is None


@pytest.mark.asyncio
async def test_reactivation_needs_a_new_token(epochs):
    old, service = _token(), _service()
    await service.deactivate_user(uuid.uuid4())
    await _run_post_commit_callbacks(service.session)
    await service.activate_user(uuid.uuid4())

    assert await auth_service.decode_token_async(old) is None
    assert (await auth_service.decode_token_async(_token(age_seconds=-5)))["sub"] == "alice"


class _AutobotDbService(_SlmUserService):
    """What ``AutobotDatabaseUserService`` adds: its users' tokens are checked against Redis, not the SLM database."""

    epoch_in_redis = True


@pytest.mark.asyncio
async def test_a_backend_database_users_marker_goes_to_redis_not_the_slm_store(epochs):
    """The route that deletes an ``autobot_users`` user runs in the SLM, whose store is its own database (#20443)."""
    redis = MagicMock(eval=AsyncMock(return_value=1))
    session = MagicMock(flush=AsyncMock())
    session.info = {POST_COMMIT_CALLBACKS: []}
    service = _AutobotDbService(session, TenantContext(is_platform_admin=True))
    service.get_user = AsyncMock(return_value=SimpleNamespace(username="alice", is_active=True, deleted_at=None))
    service._audit_log = AsyncMock()

    with patch("autobot_shared.user_management.password_epoch.get_async_redis_client", AsyncMock(return_value=redis)):
        await service.delete_user(uuid.uuid4(), hard_delete=False)
        await _run_post_commit_callbacks(session)

    assert epochs == {}, "the SLM's own store must not receive it"
    assert redis.eval.await_args.args[2] == f"{password_epoch.PASSWORD_EPOCH_PREFIX}alice"


def test_the_autobot_users_routes_use_the_service_that_writes_to_redis():
    """Read from source: this harness stubs the SLM's ``user_management`` package, so the class is not importable."""
    root = Path(__file__).resolve().parents[2]
    service = (root / "user_management" / "services" / "autobot_database_user_service.py").read_text(encoding="utf-8")
    assert re.search(r"class AutobotDatabaseUserService\(UserService\):.*?epoch_in_redis = True", service, re.S)
    routes = (root / "api" / "autobot_users.py").read_text(encoding="utf-8")
    assert routes.count("AutobotDatabaseUserService(db, context)") == 6
    assert " UserService(db, context)" not in routes
