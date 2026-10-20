# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-call ``decode_responses`` override (#18553, #14187).

`decode_responses` used to be YAML-only per database, and pools were keyed by database name
alone, so no caller could get bytes from a database that decodes. The override must pick a
different pool for the opposite mode, and leave the default path (None) untouched.
"""

import asyncio
import threading

import pytest

from autobot_shared.redis_management.config import RedisDbConfig
from autobot_shared.redis_management.connection_manager import RedisConnectionManager


def _manager(decode: bool = True) -> RedisConnectionManager:
    """Pool-registry state only; no Redis, no YAML. `temp` is db 9."""
    m = object.__new__(RedisConnectionManager)
    m._configs = {"temp": RedisDbConfig(name="temp", db=9, host="127.0.0.1", decode_responses=decode)}
    m._sync_pools = {}
    m._async_pools = {}
    m._async_pool_tasks = {}
    m._async_lock = asyncio.Lock()
    m._init_lock = threading.Lock()
    m._tcp_keepalive_options = {}
    return m


def _decode(pool) -> bool:
    return pool.connection_kwargs["decode_responses"]


def test_the_two_decode_modes_get_two_distinct_sync_pools():
    m = _manager()
    m._ensure_sync_pool_exists("temp", True)
    m._ensure_sync_pool_exists("temp", False)
    assert len(m._sync_pools) == 2
    assert _decode(m._sync_pools[m._pool_key("temp", True)]) is True
    assert _decode(m._sync_pools[m._pool_key("temp", False)]) is False
    assert m._pool_key("temp", True) != m._pool_key("temp", False)


def test_the_default_path_is_unchanged_and_shares_the_yaml_mode_pool():
    m = _manager(decode=True)
    m._ensure_sync_pool_exists("temp")
    m._ensure_sync_pool_exists("temp", True)  # an override equal to the YAML value is the same pool
    assert list(m._sync_pools) == ["temp"]
    assert _decode(m._sync_pools["temp"]) is True


def test_the_default_follows_the_yaml_value_when_the_database_does_not_decode():
    m = _manager(decode=False)
    assert m._pool_key("temp", None) == "temp"
    assert m._pool_key("temp", False) == "temp"
    assert m._pool_key("temp", True) != "temp"


def test_the_override_reaches_the_async_pool_params():
    m = _manager()
    config = m._configs["temp"]
    assert m._build_async_pool_params(config, "temp")["decode_responses"] is True
    assert m._build_async_pool_params(config, "temp", False)["decode_responses"] is False
    assert m._build_async_pool_params(config, "temp", True)["decode_responses"] is True


def test_the_async_registry_holds_one_pool_per_decode_mode():
    m = _manager()
    made: list[tuple[str, bool | None]] = []

    async def _create(name, decode_responses=None):
        made.append((name, decode_responses))
        return object()

    m._create_async_pool = _create

    async def _run():
        await m._ensure_async_pool_exists("temp", True)
        await m._ensure_async_pool_exists("temp", False)
        await m._ensure_async_pool_exists("temp", False)  # reuses the bytes pool

    asyncio.run(_run())
    assert made == [("temp", True), ("temp", False)]
    assert len(m._async_pools) == 2


def test_pool_statistics_are_grouped_by_database_with_a_decode_field():
    m = _manager(decode=True)
    m._ensure_sync_pool_exists("temp")
    m._ensure_sync_pool_exists("temp", False)
    grouped = m.get_pool_statistics_by_database()
    assert list(grouped) == ["temp"]  # no "temp#decode=False" entry of its own
    assert sorted((s.database_name, s.decode_responses) for s in grouped["temp"]) == [("temp", False), ("temp", True)]


def test_the_pool_statistics_lookup_finds_both_decode_variants():
    m = _manager(decode=True)
    m._ensure_sync_pool_exists("temp")
    m._ensure_sync_pool_exists("temp", False)
    default = m.get_pool_statistics("temp")  # the existing call shape is unchanged
    assert (default.database_name, default.decode_responses) == ("temp", True)
    for stats in (m.get_pool_statistics("temp", False), m.get_pool_statistics("temp#decode=False")):
        assert (stats.database_name, stats.decode_responses) == ("temp", False)
    assert m.get_pool_statistics("temp", True).decode_responses is True


def test_the_pool_statistics_lookup_still_raises_for_a_missing_variant():
    m = _manager(decode=True)
    m._ensure_sync_pool_exists("temp")
    with pytest.raises(ValueError):
        m.get_pool_statistics("temp", False)
