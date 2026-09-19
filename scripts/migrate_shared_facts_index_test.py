# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""migrate_shared_facts_index carries over legacy shares with no data loss,
and is idempotent (#16709)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from migrate_shared_facts_index import migrate  # noqa: E402


class _FakeAsyncRedis:
    """Minimal async stand-in for redis-py's async client: hash + set ops."""

    def __init__(self) -> None:
        self._hashes: dict[str, dict[str, str]] = {}
        self._sets: dict[str, set[str]] = {}

    async def hget(self, key, field):
        return self._hashes.get(key, {}).get(field)

    async def hset(self, key, field, value):
        self._hashes.setdefault(key, {})[field] = value

    async def sadd(self, key, *values):
        self._sets.setdefault(key, set()).update(values)

    async def smembers(self, key):
        return set(self._sets.get(key, set()))

    async def delete(self, key):
        self._sets.pop(key, None)

    async def scan_iter(self, match: str):
        prefix = match.rstrip("*")
        for key in list(self._sets.keys()):
            if key.startswith(prefix):
                yield key


def _seed_legacy_share(redis: _FakeAsyncRedis, user_id: str, fact_id: str, visibility: str = "private") -> None:
    redis._hashes[f"fact:{fact_id}"] = {
        "metadata": json.dumps({"owner_id": "owner1", "visibility": visibility, "shared_with": []}),
        "content": "secret content",
    }
    redis._sets[f"user:shared_facts:{user_id}"] = {fact_id}


@pytest.mark.asyncio
async def test_migrate_promotes_visibility_and_writes_the_canonical_index():
    redis = _FakeAsyncRedis()
    _seed_legacy_share(redis, "u2", "f1")

    with patch("autobot_shared.redis_client.get_async_redis_client", new=AsyncMock(return_value=redis)):
        summary = await migrate(dry_run=False)

    assert summary == {"users_migrated": 1, "facts_migrated": 1, "visibility_fixed": 1, "dry_run": False}
    metadata = json.loads(redis._hashes["fact:f1"]["metadata"])
    assert metadata["visibility"] == "shared"
    assert "u2" in metadata["shared_with"]
    assert "f1" in redis._sets["user:kb:shared:u2"]
    assert "user:shared_facts:u2" not in redis._sets


@pytest.mark.asyncio
async def test_migrate_is_idempotent():
    redis = _FakeAsyncRedis()
    _seed_legacy_share(redis, "u2", "f1")

    with patch("autobot_shared.redis_client.get_async_redis_client", new=AsyncMock(return_value=redis)):
        await migrate(dry_run=False)
        second_run = await migrate(dry_run=False)

    assert second_run == {"users_migrated": 0, "facts_migrated": 0, "visibility_fixed": 0, "dry_run": False}
    assert "f1" in redis._sets["user:kb:shared:u2"]  # still there, not lost


@pytest.mark.asyncio
async def test_dry_run_makes_no_changes():
    redis = _FakeAsyncRedis()
    _seed_legacy_share(redis, "u2", "f1")

    with patch("autobot_shared.redis_client.get_async_redis_client", new=AsyncMock(return_value=redis)):
        summary = await migrate(dry_run=True)

    assert summary["facts_migrated"] == 1
    assert "user:kb:shared:u2" not in redis._sets  # nothing written
    assert "f1" in redis._sets["user:shared_facts:u2"]  # legacy key untouched
    metadata = json.loads(redis._hashes["fact:f1"]["metadata"])
    assert metadata["visibility"] == "private"  # not promoted


def test_migrate_defaults_to_dry_run():
    """This rewrites stored user data -- it must never run live by omission (#16709)."""
    import inspect

    assert inspect.signature(migrate).parameters["dry_run"].default is True


def test_cli_requires_explicit_apply_flag_to_write():
    """`python migrate_shared_facts_index.py` with no flags previews only;
    only `--apply` writes. Never the other way around (#16709)."""
    from migrate_shared_facts_index import _cli_dry_run

    assert _cli_dry_run(["migrate_shared_facts_index.py"]) is True
    assert _cli_dry_run(["migrate_shared_facts_index.py", "--apply"]) is False
