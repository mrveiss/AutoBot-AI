# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#14187: the Redis-cached checkpoint copy must not deserialize with pickle.

``OperationCheckpointManager`` cached the same dict it writes to the JSON
file store with ``pickle.dumps()``/``pickle.loads()`` -- whoever can write
the ``checkpoint:{operation_id}:{checkpoint_id}`` Redis hash key (a wider
set than "our own file on our own disk", #14124) got arbitrary code
execution the moment a checkpoint was read back. The cache is now JSON, the
same format the file store already used.

These tests never call the real Redis client -- ``_FakeAsyncRedis`` is a
minimal in-memory async stand-in supporting exactly the surface
``checkpoint_manager.py`` uses (``hset``/``hget``/``keys``/``expire``/
``delete``/``pipeline``). No shared ``tests/helpers/fake_redis.py`` class
supports glob ``keys()``, which this module relies on.
"""

from __future__ import annotations

import fnmatch
import json
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

from utils.long_running_operations.checkpoint_manager import OperationCheckpointManager


class _FakePipeline:
    """Buffers ``hget`` calls and replays them on ``execute()``."""

    def __init__(self, redis: "_FakeAsyncRedis") -> None:
        self._redis = redis
        self._ops: List[Tuple[str, str]] = []

    def hget(self, name: str, field: str) -> "_FakePipeline":
        self._ops.append((name, field))
        return self

    async def execute(self) -> List[Optional[bytes]]:
        return [await self._redis.hget(name, field) for name, field in self._ops]


class _FakeAsyncRedis:
    """Minimal in-memory async Redis stand-in for checkpoint hash storage."""

    def __init__(self) -> None:
        self._hashes: Dict[str, Dict[str, bytes]] = {}
        self.expire_calls: List[Tuple[str, int]] = []

    async def hset(self, name: str, mapping: Optional[Dict[str, Any]] = None, **kwargs: Any) -> int:
        payload = mapping or kwargs
        bucket = self._hashes.setdefault(name, {})
        for key, value in payload.items():
            bucket[key] = value.encode("utf-8") if isinstance(value, str) else value
        return len(payload)

    async def hget(self, name: str, field: str) -> Optional[bytes]:
        return self._hashes.get(name, {}).get(field)

    async def keys(self, pattern: str) -> List[str]:
        return [key for key in self._hashes if fnmatch.fnmatchcase(key, pattern)]

    async def expire(self, name: str, ttl: int) -> bool:
        self.expire_calls.append((name, ttl))
        return True

    async def delete(self, *names: str) -> int:
        removed = 0
        for name in names:
            if self._hashes.pop(name, None) is not None:
                removed += 1
        return removed

    def pipeline(self) -> _FakePipeline:
        return _FakePipeline(self)


def _manager(tmp_path: Path, redis_client: _FakeAsyncRedis) -> OperationCheckpointManager:
    """A checkpoint manager whose file store lives under ``tmp_path``.

    ``__init__`` always resolves ``checkpoint_dir`` under the real
    ``PATH.PROJECT_ROOT`` -- redirect it before any test writes through it.
    """
    manager = OperationCheckpointManager(redis_client=redis_client)
    manager.checkpoint_dir = tmp_path
    manager.checkpoint_dir.mkdir(parents=True, exist_ok=True)
    return manager


def _seed_legacy_redis_entry(
    redis_client: _FakeAsyncRedis,
    operation_id: str,
    checkpoint_id: str,
    checkpoint_data: Dict[str, Any],
) -> None:
    """Write a pre-#14187 (pickle-encoded) cache entry directly into the fake.

    Bypasses ``save_checkpoint`` -- this is what the *old* code path would
    have written, built from a real ``pickle.dumps()`` call (a fragment
    assembled at test run time), never a committed opaque blob.
    """
    redis_key = f"checkpoint:{operation_id}:{checkpoint_id}"
    redis_client._hashes[redis_key] = {
        "data": pickle.dumps(checkpoint_data, protocol=pickle.HIGHEST_PROTOCOL),
        "progress": str(checkpoint_data["progress_percent"]).encode("utf-8"),
        "timestamp": checkpoint_data["checkpoint_time"].encode("utf-8"),
    }


def _write_legacy_file(tmp_path: Path, checkpoint_id: str, checkpoint_data: Dict[str, Any]) -> None:
    """The JSON file store, unaffected by #14187, already held this shape."""
    (tmp_path / f"{checkpoint_id}.json").write_text(json.dumps(checkpoint_data), encoding="utf-8")


def _checkpoint_data(operation_id: str, checkpoint_id: str) -> Dict[str, Any]:
    return {
        "checkpoint_id": checkpoint_id,
        "operation_id": operation_id,
        "checkpoint_time": "2026-08-01T00:00:00+00:00",
        "progress_percent": 42.0,
        "state_data": {"step": 3},
        "metadata": {},
    }


def _spy_on_pickle_loads(monkeypatch: pytest.MonkeyPatch) -> List[bool]:
    """Record every ``pickle.loads`` call without breaking behaviour.

    A version that *raises* on any call is the wrong shape here: this
    module's Redis paths already wrap Redis access in a broad
    ``except Exception: logger.warning(...); <fall through to file store>``
    (pre-existing, not new to #14187) -- so a raised sentinel gets caught by
    that handler and the test still passes via the file-store fallback,
    silently blind to a regression that reintroduces ``pickle.loads``. A
    spy that still delegates to the real ``pickle.loads`` lets the call
    happen (so behaviour is unaffected either way) while recording that it
    happened, which is what the assertion below actually checks.
    """
    calls: List[bool] = []
    real_loads = pickle.loads

    def _spy(*args: Any, **kwargs: Any) -> Any:
        calls.append(True)
        return real_loads(*args, **kwargs)

    monkeypatch.setattr(pickle, "loads", _spy)
    return calls


# ---------------------------------------------------------------------------
# save_checkpoint: the Redis cache is JSON, not pickle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_checkpoint_caches_json_in_redis(tmp_path):
    redis_client = _FakeAsyncRedis()
    manager = _manager(tmp_path, redis_client)

    await manager.save_checkpoint("op-1", "cp-1", 50.0, {"k": "v"})

    redis_key = "checkpoint:op-1:cp-1"
    raw = redis_client._hashes[redis_key]["data"]
    # Must be parseable as JSON...
    parsed = json.loads(raw)
    assert parsed["checkpoint_id"] == "cp-1"
    assert parsed["state_data"] == {"k": "v"}
    # ...and must NOT be a pickle stream (bandit excludes *_test.py; #B301 does
    # not apply here -- this call only proves the stored bytes are not pickle).
    with pytest.raises(pickle.UnpicklingError):
        pickle.loads(raw)


# ---------------------------------------------------------------------------
# load_checkpoint: never unpickles; falls back to the file store
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_checkpoint_never_unpickles_and_recovers_from_file(tmp_path, monkeypatch):
    pickle_loads_calls = _spy_on_pickle_loads(monkeypatch)
    redis_client = _FakeAsyncRedis()
    manager = _manager(tmp_path, redis_client)

    data = _checkpoint_data("op-1", "cp-1")
    _seed_legacy_redis_entry(redis_client, "op-1", "cp-1", data)
    _write_legacy_file(tmp_path, "cp-1", data)

    result = await manager.load_checkpoint("cp-1")

    assert not pickle_loads_calls, "pickle.loads must never be called on Redis-cached checkpoint data"
    assert result is not None
    assert result.checkpoint_id == "cp-1"
    assert result.state_data == {"step": 3}
    # The stale cache entry is discarded, not left to warn on every read.
    assert "checkpoint:op-1:cp-1" not in redis_client._hashes


@pytest.mark.asyncio
async def test_load_checkpoint_returns_none_when_absent_everywhere(tmp_path):
    redis_client = _FakeAsyncRedis()
    manager = _manager(tmp_path, redis_client)

    assert await manager.load_checkpoint("does-not-exist") is None


# ---------------------------------------------------------------------------
# list_checkpoints: one bad Redis entry doesn't lose the others
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_checkpoints_from_redis_drops_legacy_entry_without_unpickling(tmp_path, monkeypatch):
    pickle_loads_calls = _spy_on_pickle_loads(monkeypatch)
    redis_client = _FakeAsyncRedis()
    manager = _manager(tmp_path, redis_client)

    legacy = _checkpoint_data("op-1", "cp-legacy")
    _seed_legacy_redis_entry(redis_client, "op-1", "cp-legacy", legacy)
    await manager.save_checkpoint("op-1", "cp-fresh", 10.0, {"k": "fresh"})
    # save_checkpoint above already wrote cp-fresh's file+redis entry; only
    # cp-legacy needs its (pre-#14187) file counterpart seeded by hand.
    _write_legacy_file(tmp_path, "cp-legacy", legacy)

    from_redis = await manager._list_checkpoints_from_redis("op-1")

    assert not pickle_loads_calls, "pickle.loads must never be called on Redis-cached checkpoint data"
    assert {c.checkpoint_id for c in from_redis} == {"cp-fresh"}
    assert "checkpoint:op-1:cp-legacy" not in redis_client._hashes


@pytest.mark.asyncio
async def test_list_checkpoints_recovers_legacy_entry_via_file_store(tmp_path, monkeypatch):
    """No data loss end-to-end: list_checkpoints() merges the file store."""
    pickle_loads_calls = _spy_on_pickle_loads(monkeypatch)
    redis_client = _FakeAsyncRedis()
    manager = _manager(tmp_path, redis_client)

    legacy = _checkpoint_data("op-1", "cp-legacy")
    _seed_legacy_redis_entry(redis_client, "op-1", "cp-legacy", legacy)
    _write_legacy_file(tmp_path, "cp-legacy", legacy)
    await manager.save_checkpoint("op-1", "cp-fresh", 10.0, {"k": "fresh"})

    all_checkpoints = await manager.list_checkpoints("op-1")

    assert not pickle_loads_calls, "pickle.loads must never be called on Redis-cached checkpoint data"
    assert {c.checkpoint_id for c in all_checkpoints} == {"cp-legacy", "cp-fresh"}
