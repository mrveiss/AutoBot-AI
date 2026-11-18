# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Fail-closed wiring and reconfiguration of the shared RBAC middleware (#18088)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.user_management.middleware import rbac_middleware as mod


def _deps(config: object = None) -> mod.RBACDependencies:
    return mod.RBACDependencies(
        db_session_context=MagicMock(),
        user_service_cls=MagicMock(),
        tenant_context_cls=MagicMock(),
        get_deployment_config=lambda: config,
    )


@pytest.fixture(autouse=True)
def _restore_module_state():
    saved_deps, saved_config = mod._dependencies, mod.rbac_middleware._config
    mod._permission_cache.clear()
    yield
    mod._dependencies, mod.rbac_middleware._config = saved_deps, saved_config
    mod._permission_cache.clear()


@pytest.fixture
def cache_miss():
    """L1 is cleared by the autouse fixture; make L2 miss and skip the listener."""
    redis = MagicMock()
    redis.get = AsyncMock(return_value=None)
    with (
        patch.object(mod, "get_async_redis_client", AsyncMock(return_value=redis)),
        patch.object(mod, "_ensure_listener_started", AsyncMock()),
    ):
        yield


async def test_check_permission_fails_closed_when_unconfigured_on_a_miss(cache_miss) -> None:
    mod._dependencies = None
    with pytest.raises(mod.RBACNotConfiguredError):
        await mod.rbac_middleware.check_permission(uuid.uuid4(), "any.permission")


async def test_denied_audit_fails_loudly_when_unconfigured() -> None:
    mod._dependencies = None
    with pytest.raises(mod.RBACNotConfiguredError):
        await mod._emit_permission_denied_audit(uuid.uuid4(), "any.permission", "/x")


async def test_an_l1_hit_returns_real_permissions_even_when_unconfigured() -> None:
    """The raise holds on a MISS; a hit is cached truth, not fail-open."""
    mod._dependencies = None
    user_id = uuid.uuid4()
    import time

    mod._permission_cache[str(user_id)] = ({"a.b"}, time.time())
    with patch.object(mod, "_ensure_listener_started", AsyncMock()):
        assert await mod.rbac_middleware.check_permission(user_id, "a.b") is True
        assert await mod.rbac_middleware.check_permission(user_id, "c.d") is False


def test_reconfiguring_with_different_deps_resets_config_and_warns() -> None:
    first, second = _deps("first-config"), _deps("second-config")
    mod._dependencies = None
    mod.configure_rbac(first)
    assert mod.rbac_middleware._deployment_config() == "first-config"

    with patch.object(mod, "logger") as log:
        mod.configure_rbac(second)
    assert mod.rbac_middleware._config is None
    assert mod.rbac_middleware._deployment_config() == "second-config"
    log.warning.assert_called_once()


def test_reconfiguring_with_the_same_deps_is_silent() -> None:
    deps = _deps("cfg")
    mod._dependencies = None
    with patch.object(mod, "logger") as log:
        mod.configure_rbac(deps)
        mod.configure_rbac(deps)
    log.warning.assert_not_called()
