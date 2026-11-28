# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The cache API's settings persist, and a clear never flushes a database it did not name (#19497).

The settings were written to ``config``, a database nothing declares, so every save reported
success and stored nothing. ``locks`` and ``conversations`` are aliases, so clearing ``locks``
flushed the sessions DB and ``clear/all`` flushed sessions and agents twice each.
"""

import asyncio
import inspect
from collections import Counter

import pytest
from fastapi import HTTPException

from api import cache_management, cache_redis_databases
from auth_middleware import check_admin_permission, get_current_user
from autobot_shared.redis_management import types as _types
from autobot_shared.redis_management.types import DATABASE_MAPPING

_CONFIG = {"defaultTTLMinutes": 7, "settingsTTLMinutes": 11, "autoCleanupEnabled": False, "maxCacheSizeMB": 64}


class _FakeRedis:
    """One Redis database: a dict, and a log of the flushes it received."""

    def __init__(self, number: int, flushes: Counter):
        self.number, self.flushes, self.data = number, flushes, {}

    def set(self, key, value):
        self.data[key] = value

    def get(self, key):
        return self.data.get(key)

    def dbsize(self):
        return len(self.data)

    def flushdb(self):
        self.flushes[self.number] += 1
        self.data.clear()


@pytest.fixture
def redis(monkeypatch):
    """A fake server: one database per NUMBER, so an alias reaches its target's database."""
    flushes: Counter = Counter()
    databases: dict = {}

    def get_redis_client(async_client, database):
        number = DATABASE_MAPPING[database]  # refuses an undeclared name, as the real client does
        return databases.setdefault(number, _FakeRedis(number, flushes))

    monkeypatch.setattr(cache_redis_databases, "get_redis_client", get_redis_client)
    monkeypatch.setattr(cache_redis_databases, "audit_log", _record_audit)
    _AUDITED.clear()
    return databases, flushes


_ADMIN = {"username": "ops-admin"}
_AUDITED: list = []


async def _record_audit(**entry):
    _AUDITED.append(entry)
    return True


def _clear(database: str) -> dict:
    return asyncio.run(cache_management.clear_redis_cache(database, admin_check=True, current_user=_ADMIN))


def test_a_saved_config_loads_back_from_the_declared_cache_db(redis):
    databases, _ = redis
    asyncio.run(cache_management.save_cache_config(dict(_CONFIG)))
    loaded = asyncio.run(cache_management.get_cache_config())
    assert (loaded["config"], loaded["source"]) == (_CONFIG, "redis")
    stored = databases[DATABASE_MAPPING[cache_redis_databases.CACHE_CONFIG_DATABASE]]
    assert list(stored.data) == ["cache:config"], "one namespaced key in the cache DB, nothing else"


def test_a_saved_config_survives_a_cache_clear(redis):
    cache_redis_databases.save_config(dict(_CONFIG))
    asyncio.run(cache_redis_databases.clear_and_audit("cache", "ops-admin"))
    assert cache_redis_databases.load_config() == _CONFIG


def test_a_failed_flush_is_audited_as_a_failure_not_a_flush(redis, monkeypatch):
    monkeypatch.setattr(
        cache_redis_databases,
        "clear_single_redis_database",
        lambda name, number: {"name": name, "database": number, "error": "boom", "keys_cleared": 0},
    )
    asyncio.run(cache_redis_databases.clear_and_audit("cache", "ops-admin"))
    assert (_AUDITED[-1]["result"], _AUDITED[-1]["details"]["flushed"], _AUDITED[-1]["details"]["failed"]) == (
        "failure",
        {},
        ["cache"],
    )


def test_a_failed_save_is_an_error_not_a_success(monkeypatch):
    def unavailable(async_client, database):
        raise ConnectionError("redis down")

    monkeypatch.setattr(cache_redis_databases, "get_redis_client", unavailable)
    with pytest.raises(HTTPException) as raised:
        asyncio.run(cache_management.save_cache_config(dict(_CONFIG)))
    assert raised.value.status_code == 503


def test_the_cache_config_is_stored_in_a_declared_database():
    assert cache_redis_databases.CACHE_CONFIG_DATABASE in _types.DECLARED_DATABASES


def test_no_alias_is_offered_for_clearing_or_stats():
    offered = set(cache_redis_databases.redis_databases())
    assert offered and offered <= set(_types.DECLARED_DATABASES)
    assert not offered & set(_types._ALIASES)


@pytest.mark.parametrize("alias", sorted(_types._ALIASES))
def test_clearing_an_alias_is_a_400_naming_its_target_and_flushes_nothing(redis, alias):
    _, flushes = redis
    with pytest.raises(HTTPException) as raised:
        _clear(alias)
    assert raised.value.status_code == 400
    assert f"alias of '{_types._ALIASES[alias]}'" in raised.value.detail
    assert not flushes


def test_clearing_one_cache_flushes_exactly_that_one_and_audits_the_actor(redis):
    _, flushes = redis
    _clear("cache")
    assert flushes == Counter({DATABASE_MAPPING["cache"]: 1})
    assert [(e["user_id"], e["resource"], e["details"]["flushed"]) for e in _AUDITED] == [
        ("ops-admin", "redis-cache:cache", {"cache": DATABASE_MAPPING["cache"]})
    ]


@pytest.mark.parametrize("durable", ["main", "knowledge", "prompts", "agents", "sessions"])
def test_a_durable_database_is_a_400_and_flushes_nothing(redis, durable):
    """Owner decision 2026-10-25 (#19365): only real caches are clearable; durable data is a deletion proposal."""
    _, flushes = redis
    with pytest.raises(HTTPException) as raised:
        _clear(durable)
    assert raised.value.status_code == 400, "with_error_handling must keep the 400, not turn it into a 500"
    assert "durable data" in raised.value.detail
    assert not flushes and not _AUDITED


def test_only_real_caches_are_clearable():
    assert set(cache_redis_databases.clearable_databases()) == {"cache", "analytics"}


def test_the_clear_route_requires_an_admin_and_an_authenticated_user():
    defaults = inspect.signature(cache_management.clear_redis_cache.__wrapped__).parameters
    assert defaults["admin_check"].default.dependency is check_admin_permission
    assert defaults["current_user"].default.dependency is get_current_user


def test_clear_all_flushes_each_distinct_cache_exactly_once(redis):
    _, flushes = redis
    result = _clear("all")
    expected = set(cache_redis_databases.clearable_databases().values())
    assert flushes == Counter({number: 1 for number in expected})
    assert len(result["cleared_databases"]) == len(expected)


def test_clear_all_flushes_a_shared_number_once(redis, monkeypatch):
    """Two names an override puts on one number are one database: flushed once, reported once."""
    _, flushes = redis
    monkeypatch.setitem(DATABASE_MAPPING, "analytics", DATABASE_MAPPING["cache"])
    _clear("all")
    assert max(flushes.values()) == 1
    assert flushes[DATABASE_MAPPING["cache"]] == 1
