# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for SLM RBAC middleware Redis L2 cache + pub/sub invalidation (MVA-313 / GH#7568).

Verifies that:
- L1 per-worker cache is checked before Redis (no Redis call on L1 hit)
- L2 Redis cache is checked before the database (no DB call on L2 hit)
- Database fallback populates both L1 and L2
- clear_cache removes from L1, deletes the Redis key, and publishes to pub/sub
- The pub/sub invalidation listener clears the L1 cache on message receipt

Import strategy: rbac_middleware imports autobot_shared + SLM service modules at module
level, which pull in pydantic settings that try to read /etc/autobot/*.env (not present in
CI).  We patch those heavy modules into sys.modules before loading rbac_middleware directly
via importlib — matching the approach used in other SLM unit tests that avoid FastAPI imports.
"""

import asyncio
import importlib.util
import json
import sys
import time
import types
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Bootstrap — must happen before any import of rbac_middleware
# ---------------------------------------------------------------------------

_SLM_ROOT = Path(__file__).parent.parent
_SHARED_ROOT = _SLM_ROOT.parent / "autobot_shared"

for _p in (str(_SLM_ROOT), str(_SHARED_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Stub out the modules that pull in pydantic settings or FastAPI's python_multipart.
# Note: test_require_permission.py documents the same python_multipart env conflict.
_MOCK_NAMES = [
    # fastapi pulls in starlette → multipart (broken in this env)
    "fastapi",
    "fastapi.exceptions",
    "fastapi.responses",
    # autobot_shared pulls in pydantic-settings → /etc/autobot/ reads
    "autobot_shared",
    "autobot_shared.redis_client",
    "autobot_shared.auth",
    "autobot_shared.auth.permissions",
    # SLM service/config modules pull in DB models and pydantic settings
    "user_management.services",
    "user_management.database",
    "user_management.config",
]
for _name in _MOCK_NAMES:
    if _name not in sys.modules:
        sys.modules[_name] = MagicMock()

# fastapi.HTTPException, Request, status must be real enough for isinstance checks
import http  # noqa: E402

_fastapi_mock = sys.modules["fastapi"]
_fastapi_mock.HTTPException = type("HTTPException", (Exception,), {"__init__": lambda s, **kw: None})
_fastapi_mock.Request = type("Request", (), {})
_fastapi_mock.status = http.HTTPStatus

# Load the module under test directly (bypasses __init__ import chain)
_SPEC = importlib.util.spec_from_file_location(
    "user_management.middleware.rbac_middleware",
    _SLM_ROOT / "user_management" / "middleware" / "rbac_middleware.py",
)
_rbac_mod: types.ModuleType = types.ModuleType(_SPEC.name)
_SPEC.loader.exec_module(_rbac_mod)

# Aliases for readability
_CACHE_TTL = _rbac_mod.CACHE_TTL_SECONDS
_REDIS_PREFIX = _rbac_mod._REDIS_KEY_PREFIX
_PUBSUB_CHANNEL = _rbac_mod._PUBSUB_CHANNEL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_uuid() -> uuid.UUID:
    return uuid.uuid4()


def _make_redis(get_return=None):
    r = AsyncMock()
    r.get = AsyncMock(return_value=get_return)
    r.setex = AsyncMock()
    r.delete = AsyncMock()
    r.publish = AsyncMock()

    async def _empty_scan(*_a, **_kw):
        return
        yield  # make it an async generator

    r.scan_iter = _empty_scan
    return r


async def _async_keys(*keys):
    for k in keys:
        yield k


# ---------------------------------------------------------------------------
# Fixtures — reset module-level state between tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_module_state():
    _rbac_mod._permission_cache.clear()
    _rbac_mod._listener_task = None
    yield
    _rbac_mod._permission_cache.clear()
    _rbac_mod._listener_task = None


# ---------------------------------------------------------------------------
# 1. L1 cache hit — Redis is never called
# ---------------------------------------------------------------------------


class TestL1CacheHit:
    @pytest.mark.asyncio
    async def test_l1_hit_returns_cached_permissions(self):
        user_id = _fresh_uuid()
        perms = {"agents.read", "workflows.read"}
        _rbac_mod._permission_cache[str(user_id)] = (perms, time.time())

        middleware = _rbac_mod.RBACMiddleware()

        with patch.object(_rbac_mod, "get_async_redis_client", AsyncMock()) as mock_redis:
            result = await middleware.get_user_permissions(user_id)

        assert result == perms
        mock_redis.assert_not_called()

    @pytest.mark.asyncio
    async def test_l1_expired_entry_falls_through_to_redis(self):
        user_id = _fresh_uuid()
        stale_ts = time.time() - _CACHE_TTL - 1
        _rbac_mod._permission_cache[str(user_id)] = ({"old.perm"}, stale_ts)

        fresh = ["agents.write"]
        redis = _make_redis(get_return=json.dumps(fresh))

        with (
            patch.object(_rbac_mod, "get_async_redis_client", AsyncMock(return_value=redis)),
            patch.object(_rbac_mod, "_ensure_listener_started", AsyncMock()),
        ):
            middleware = _rbac_mod.RBACMiddleware()
            result = await middleware.get_user_permissions(user_id)

        assert result == set(fresh)
        redis.get.assert_awaited_once()


# ---------------------------------------------------------------------------
# 2. L2 Redis cache hit — database is never called
# ---------------------------------------------------------------------------


class TestL2CacheHit:
    @pytest.mark.asyncio
    async def test_l2_hit_skips_database(self):
        user_id = _fresh_uuid()
        perms_list = ["agents.read", "workflows.write"]
        redis = _make_redis(get_return=json.dumps(perms_list))

        with (
            patch.object(_rbac_mod, "get_async_redis_client", AsyncMock(return_value=redis)),
            patch.object(_rbac_mod, "_ensure_listener_started", AsyncMock()),
        ):
            middleware = _rbac_mod.RBACMiddleware()
            result = await middleware.get_user_permissions(user_id)

        assert result == set(perms_list)
        redis.get.assert_awaited_once_with(f"{_REDIS_PREFIX}{user_id}")

    @pytest.mark.asyncio
    async def test_l2_hit_populates_l1(self):
        user_id = _fresh_uuid()
        perms_list = ["security.manage"]
        redis = _make_redis(get_return=json.dumps(perms_list))

        with (
            patch.object(_rbac_mod, "get_async_redis_client", AsyncMock(return_value=redis)),
            patch.object(_rbac_mod, "_ensure_listener_started", AsyncMock()),
        ):
            middleware = _rbac_mod.RBACMiddleware()
            await middleware.get_user_permissions(user_id)

        cached_perms, _ = _rbac_mod._permission_cache[str(user_id)]
        assert cached_perms == set(perms_list)


# ---------------------------------------------------------------------------
# 3. Database fallback — L1 miss + L2 miss → DB → populate both caches
# ---------------------------------------------------------------------------


class TestDatabaseFallback:
    @pytest.mark.asyncio
    async def test_db_fallback_populates_l1_and_l2(self):
        user_id = _fresh_uuid()
        db_perms = {"admin.users.write", "api.read"}

        redis = _make_redis(get_return=None)

        class FakeUserService:
            def __init__(self, *a, **kw):
                pass

            async def get_user_permissions(self, uid):
                return db_perms

        ctx_mock = MagicMock()
        ctx_mock.__aenter__ = AsyncMock(return_value=MagicMock())
        ctx_mock.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(_rbac_mod, "get_async_redis_client", AsyncMock(return_value=redis)),
            patch.object(_rbac_mod, "_ensure_listener_started", AsyncMock()),
            patch.object(_rbac_mod, "UserService", FakeUserService),
            patch.object(_rbac_mod, "db_session_context", return_value=ctx_mock),
        ):
            middleware = _rbac_mod.RBACMiddleware()
            middleware._config = SimpleNamespace(postgres_enabled=True)
            result = await middleware.get_user_permissions(user_id)

        assert result == db_perms
        # L1 populated
        assert str(user_id) in _rbac_mod._permission_cache
        # L2 Redis setex called with the right key prefix
        redis.setex.assert_awaited_once()
        key = redis.setex.call_args[0][0]
        assert str(user_id) in key

    @pytest.mark.asyncio
    async def test_db_fallback_returns_empty_when_postgres_disabled(self):
        user_id = _fresh_uuid()
        redis = _make_redis(get_return=None)

        with (
            patch.object(_rbac_mod, "get_async_redis_client", AsyncMock(return_value=redis)),
            patch.object(_rbac_mod, "_ensure_listener_started", AsyncMock()),
        ):
            middleware = _rbac_mod.RBACMiddleware()
            middleware._config = SimpleNamespace(postgres_enabled=False)
            result = await middleware.get_user_permissions(user_id)

        assert result == set()


# ---------------------------------------------------------------------------
# 4. clear_cache — L1, L2, pub/sub
# ---------------------------------------------------------------------------


class TestClearCache:
    @pytest.mark.asyncio
    async def test_clear_single_user_removes_l1_and_publishes(self):
        user_id = _fresh_uuid()
        _rbac_mod._permission_cache[str(user_id)] = ({"agents.read"}, time.time())

        redis = _make_redis()
        with patch.object(_rbac_mod, "get_async_redis_client", AsyncMock(return_value=redis)):
            middleware = _rbac_mod.RBACMiddleware()
            await middleware.clear_cache(user_id)

        assert str(user_id) not in _rbac_mod._permission_cache
        redis.delete.assert_awaited_once_with(f"{_REDIS_PREFIX}{user_id}")
        redis.publish.assert_awaited_once()
        published = json.loads(redis.publish.call_args[0][1])
        assert published == {"user_id": str(user_id)}

    @pytest.mark.asyncio
    async def test_clear_all_users_clears_l1_and_publishes_empty(self):
        for _ in range(3):
            _rbac_mod._permission_cache[str(_fresh_uuid())] = ({"perm"}, time.time())

        redis = _make_redis()

        async def _two_keys(_pattern):
            for k in [f"{_REDIS_PREFIX}key1", f"{_REDIS_PREFIX}key2"]:
                yield k

        redis.scan_iter = _two_keys

        with patch.object(_rbac_mod, "get_async_redis_client", AsyncMock(return_value=redis)):
            middleware = _rbac_mod.RBACMiddleware()
            await middleware.clear_cache(None)

        assert _rbac_mod._permission_cache == {}
        redis.publish.assert_awaited_once()
        published = json.loads(redis.publish.call_args[0][1])
        assert published == {}

    @pytest.mark.asyncio
    async def test_clear_cache_no_redis_still_clears_l1(self):
        user_id = _fresh_uuid()
        _rbac_mod._permission_cache[str(user_id)] = ({"perm"}, time.time())

        with patch.object(_rbac_mod, "get_async_redis_client", AsyncMock(return_value=None)):
            middleware = _rbac_mod.RBACMiddleware()
            await middleware.clear_cache(user_id)

        assert str(user_id) not in _rbac_mod._permission_cache


# ---------------------------------------------------------------------------
# 5. check_permission / check_any_permission / check_all_permissions
# ---------------------------------------------------------------------------


class TestPermissionCheckHelpers:
    @pytest.mark.asyncio
    async def test_check_permission_true_when_granted(self):
        user_id = _fresh_uuid()
        _rbac_mod._permission_cache[str(user_id)] = ({"agents.read"}, time.time())

        middleware = _rbac_mod.RBACMiddleware()
        result = await middleware.check_permission(user_id, "agents.read")
        assert result is True

    @pytest.mark.asyncio
    async def test_check_permission_false_when_not_granted(self):
        user_id = _fresh_uuid()
        _rbac_mod._permission_cache[str(user_id)] = ({"agents.read"}, time.time())

        middleware = _rbac_mod.RBACMiddleware()
        result = await middleware.check_permission(user_id, "admin.system")
        assert result is False

    @pytest.mark.asyncio
    async def test_allow_all_grants_any_permission(self):
        user_id = _fresh_uuid()
        _rbac_mod._permission_cache[str(user_id)] = ({"allow_all"}, time.time())

        middleware = _rbac_mod.RBACMiddleware()
        assert await middleware.check_permission(user_id, "admin.system")
        assert await middleware.check_any_permission(user_id, ["x", "y"])
        assert await middleware.check_all_permissions(user_id, ["x", "y", "z"])

    @pytest.mark.asyncio
    async def test_check_any_permission(self):
        user_id = _fresh_uuid()
        _rbac_mod._permission_cache[str(user_id)] = ({"agents.read", "workflows.read"}, time.time())

        middleware = _rbac_mod.RBACMiddleware()
        assert await middleware.check_any_permission(user_id, ["agents.read", "admin.system"])
        assert not await middleware.check_any_permission(user_id, ["admin.system", "users.write"])

    @pytest.mark.asyncio
    async def test_check_all_permissions(self):
        user_id = _fresh_uuid()
        _rbac_mod._permission_cache[str(user_id)] = ({"agents.read", "workflows.read"}, time.time())

        middleware = _rbac_mod.RBACMiddleware()
        assert await middleware.check_all_permissions(user_id, ["agents.read", "workflows.read"])
        assert not await middleware.check_all_permissions(user_id, ["agents.read", "workflows.read", "admin.system"])

    @pytest.mark.asyncio
    async def test_none_user_id_returns_empty(self):
        middleware = _rbac_mod.RBACMiddleware()
        result = await middleware.get_user_permissions(None)
        assert result == set()


# ---------------------------------------------------------------------------
# 6. Pub/sub invalidation listener clears L1
#
# Strategy: after yielding test messages, fake_listen raises CancelledError so
# the while-True reconnect loop terminates cleanly without needing a real timer.
# ---------------------------------------------------------------------------


class TestPubSubListener:
    @pytest.mark.asyncio
    async def test_listener_clears_single_user_on_message(self):
        user_id = _fresh_uuid()
        _rbac_mod._permission_cache[str(user_id)] = ({"perm"}, time.time())

        messages = [
            {"type": "subscribe", "data": 1},
            {"type": "message", "data": json.dumps({"user_id": str(user_id)})},
        ]

        async def fake_listen():
            for msg in messages:
                yield msg
            raise asyncio.CancelledError

        pubsub = MagicMock()
        pubsub.subscribe = AsyncMock()
        pubsub.listen = fake_listen

        redis = AsyncMock()
        redis.pubsub = MagicMock(return_value=pubsub)

        with patch.object(_rbac_mod, "get_async_redis_client", AsyncMock(return_value=redis)):
            try:
                await _rbac_mod._run_invalidation_listener()
            except asyncio.CancelledError:
                pass

        assert str(user_id) not in _rbac_mod._permission_cache

    @pytest.mark.asyncio
    async def test_listener_clears_all_on_empty_user_id_message(self):
        for _ in range(3):
            _rbac_mod._permission_cache[str(_fresh_uuid())] = ({"perm"}, time.time())

        messages = [{"type": "message", "data": json.dumps({})}]

        async def fake_listen():
            for msg in messages:
                yield msg
            raise asyncio.CancelledError

        pubsub = MagicMock()
        pubsub.subscribe = AsyncMock()
        pubsub.listen = fake_listen

        redis = AsyncMock()
        redis.pubsub = MagicMock(return_value=pubsub)

        with patch.object(_rbac_mod, "get_async_redis_client", AsyncMock(return_value=redis)):
            try:
                await _rbac_mod._run_invalidation_listener()
            except asyncio.CancelledError:
                pass

        assert _rbac_mod._permission_cache == {}


# ---------------------------------------------------------------------------
# 7. Structural invariants
# ---------------------------------------------------------------------------


class TestStructuralInvariants:
    def test_redis_key_prefix_is_rbac_perm(self):
        assert _rbac_mod._REDIS_KEY_PREFIX == "rbac:perm:"

    def test_pubsub_channel_is_autobot_rbac_invalidate(self):
        assert _rbac_mod._PUBSUB_CHANNEL == "autobot:rbac:invalidate"

    def test_cache_ttl_is_five_minutes(self):
        assert _rbac_mod.CACHE_TTL_SECONDS == 300

    def test_l1_cache_is_module_level_dict(self):
        assert isinstance(_rbac_mod._permission_cache, dict)

    def test_middleware_uses_get_async_redis_client(self):
        """rbac_middleware.py must import from autobot_shared.redis_client."""
        src = (_SLM_ROOT / "user_management" / "middleware" / "rbac_middleware.py").read_text(encoding="utf-8")
        assert "get_async_redis_client" in src
        assert "autobot_shared.redis_client" in src
