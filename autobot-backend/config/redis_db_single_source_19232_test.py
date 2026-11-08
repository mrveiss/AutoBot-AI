# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The backend's Redis DB readers follow the one table (#19232).

These read ``ssot_config.RedisConfig.db_main`` / ``db_knowledge`` / ``db_tasks`` before
#19232 -- a parallel, env-backed table the canonical client never consulted. Each one is
shown moving when the one table moves (``AUTOBOT_REDIS_DB_MAIN`` / ``_KNOWLEDGE`` /
``_TASKS``), so none of them can be left behind on a second copy.
"""

import pytest

import config as config_pkg
from autobot_shared.redis_management import types as _types
from config import defaults

_OVERRIDES = {"AUTOBOT_REDIS_DB_MAIN": "12", "AUTOBOT_REDIS_DB_KNOWLEDGE": "0", "AUTOBOT_REDIS_DB_TASKS": "1"}


@pytest.fixture
def overridden(monkeypatch):
    """Rebuild THE table in place from the YAML plus ``_OVERRIDES``, as process start would."""
    monkeypatch.setattr(_types, "override_source", lambda: dict(_OVERRIDES))
    rebuilt = _types._build_database_mapping()
    saved = dict(_types.DATABASE_MAPPING)
    _types.DATABASE_MAPPING.clear()
    _types.DATABASE_MAPPING.update(rebuilt)
    yield
    _types.DATABASE_MAPPING.clear()
    _types.DATABASE_MAPPING.update(saved)


def test_the_canonical_redis_config_follows_main(overridden):
    assert config_pkg.unified_config_manager.get_redis_config()["db"] == 12


def test_the_reentry_stub_follows_main(overridden):
    assert config_pkg._ConfigStub().get_redis_config()["db"] == 12


def test_the_defaults_follow_main_knowledge_and_workflows(overridden):
    assert defaults._get_redis_config("h", 1)["db"] == 12
    assert defaults._get_memory_config("h", 1)["redis"]["db"] == 0
    assert defaults._get_task_transport_config("h", 1)["redis"]["db"] == 1


def test_the_cache_api_reports_the_moved_numbers(overridden):
    from api.cache_management import redis_databases

    databases = redis_databases()
    assert (databases["main"], databases["knowledge"]) == (12, 0)
    assert "websockets" not in databases, "a name nothing declares is not offered"
    assert None not in databases.values()


@pytest.mark.parametrize("database", ["websockets", "monitoring", "nonexistent"])
def test_clearing_an_undeclared_database_is_a_400_not_a_500(database):
    """#19232 review: an undeclared name used to reach get_redis_client, which refused it (500)."""
    import asyncio

    from fastapi import HTTPException

    from api.cache_management import clear_redis_cache

    with pytest.raises(HTTPException) as raised:
        asyncio.run(clear_redis_cache(database, admin_check=True, current_user={"username": "ops-admin"}))
    assert raised.value.status_code == 400
    assert "Clearable:" in raised.value.detail and "'cache'" in raised.value.detail


def test_the_service_registry_reports_the_resolved_redis_endpoint():
    """#19232: the registry's deployment-mode host patterns were a second Redis host path."""
    from urllib.parse import urlparse

    from autobot_shared.redis_management.endpoint import resolve_redis_endpoint
    from utils.service_registry import ServiceRegistry

    resolved = resolve_redis_endpoint()
    url = urlparse(ServiceRegistry().get_service_url("redis"))
    assert (url.scheme, url.hostname, url.port) == ("rediss" if resolved.tls else "redis", resolved.host, resolved.port)


def test_network_config_redis_url_is_the_resolvers():
    from autobot_shared.network_constants import NetworkConfig
    from autobot_shared.redis_management.endpoint import resolve_redis_endpoint

    assert NetworkConfig().redis_url == resolve_redis_endpoint().url(with_auth=False)
