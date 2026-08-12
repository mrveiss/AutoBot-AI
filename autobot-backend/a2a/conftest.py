# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Shared pytest fixtures for the A2A test modules.

Issue #13162: ``TaskManager`` is Redis-backed (#4502) and batches its
round-trips with MGET/pipelines (#8162).  The fake Redis client used by the
A2A tests therefore has to model ``mget()`` and ``pipeline()`` as well as the
plain commands, otherwise tests silently exercise MagicMock defaults instead
of the real code paths.  This factory is the single canonical fake — both
``a2a_test.py`` and ``a2a_security_test.py`` build their managers from it.
"""

from typing import Any, Callable, Dict, List, Set
from unittest.mock import MagicMock

import pytest

# Commands TaskManager queues on a pipeline before calling execute().
_PIPELINED_COMMANDS = ("set", "get", "sadd", "srem", "expire", "rpush", "delete", "publish")


def _make_pipeline(client: MagicMock) -> MagicMock:
    """Return a fake pipeline that replays queued commands on execute().

    Mirrors redis-py semantics: commands are buffered, then applied against
    the same backing store when ``execute()`` is called.  Replaying through
    ``client`` keeps the top-level call records (e.g. ``client.expire``)
    authoritative, so assertions do not have to know whether production code
    pipelined a command or issued it directly.
    """
    pipe = MagicMock()
    queued: List[tuple] = []

    def _queue(name: str) -> Callable[..., MagicMock]:
        def _record(*args: Any, **kwargs: Any) -> MagicMock:
            queued.append((name, args, kwargs))
            return pipe

        return _record

    for command in _PIPELINED_COMMANDS:
        getattr(pipe, command).side_effect = _queue(command)

    def _execute() -> List[Any]:
        results = [getattr(client, name)(*args, **kwargs) for name, args, kwargs in queued]
        queued.clear()
        return results

    pipe.execute.side_effect = _execute
    pipe.__enter__.return_value = pipe
    pipe.__exit__.return_value = False
    return pipe


def make_redis_mock() -> MagicMock:
    """Return a MagicMock that mimics the subset of redis.Redis used by TaskManager."""
    store: Dict[str, str] = {}
    audit_lists: Dict[str, List[str]] = {}
    task_set: Set[str] = set()

    mock = MagicMock()

    def _decode(value: Any) -> str:
        return value if isinstance(value, str) else value.decode("utf-8")

    def _set(key, value, ex=None):
        store[key] = _decode(value)

    def _get(key):
        value = store.get(key)
        return value.encode("utf-8") if value is not None else None

    def _mget(keys):
        return [_get(key) for key in keys]

    def _sadd(key, member):
        task_set.add(_decode(member))

    def _srem(key, member):
        task_set.discard(_decode(member))

    def _smembers(key):
        return {member.encode("utf-8") for member in task_set}

    def _rpush(key, value):
        audit_lists.setdefault(key, []).append(_decode(value))

    def _lrange(key, start, end):
        entries = audit_lists.get(key, [])
        result = entries[start : end + 1 if end != -1 else None]
        return [entry.encode("utf-8") for entry in result]

    def _expire(key, ttl):
        pass  # TTL is asserted via call records, not simulated

    mock.set.side_effect = _set
    mock.get.side_effect = _get
    mock.mget.side_effect = _mget
    mock.sadd.side_effect = _sadd
    mock.srem.side_effect = _srem
    mock.smembers.side_effect = _smembers
    mock.rpush.side_effect = _rpush
    mock.lrange.side_effect = _lrange
    mock.expire.side_effect = _expire
    mock.pipeline.side_effect = lambda *args, **kwargs: _make_pipeline(mock)

    return mock


@pytest.fixture
def redis_mock() -> MagicMock:
    """Fresh fake Redis client for a single test."""
    return make_redis_mock()
