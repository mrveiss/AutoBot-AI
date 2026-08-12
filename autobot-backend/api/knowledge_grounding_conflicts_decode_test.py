# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GET /kb-conflicts must not 500 on the decode_responses=True client (#13272).

The shared async Redis client is built with ``decode_responses=True``
(``connection_manager.py:500`` -> ``redis_management/config.py:61,153``, with no
per-database override), so ``redis.keys("conflict:*")`` yields ``str``.

``list_conflicts`` called a bare ``key.decode()`` on those keys. Unlike the
sibling defect fixed in #13271 there is **no local try/except**, so the
``AttributeError`` propagated into ``@with_error_handling``, which converts any
non-``HTTPException`` into ``HTTPException(500)``. The endpoint therefore failed
outright for every non-empty conflict set — it only appeared to work when no
conflicts existed.

The tell was immediately below the offending line: ``description``, ``severity``,
``resolution`` and ``timestamp`` were all already ``isinstance(..., bytes)``
guarded. Only the key was not.
"""

import pytest
from fastapi import HTTPException

from api import knowledge_grounding

# The live wire shape: decode_responses=True means every field is already str.
DECODED_CONFLICTS = {
    "conflict:abc123": {
        "status": "pending",
        "severity": "high",
        "description": "KB says X, source says Y",
        "timestamp": "1700000000.0",
    },
}

# A client without decode_responses; the bytes branch must not regress.
BYTES_KEY_CONFLICTS = {
    b"conflict:def456": {
        "status": "pending",
        "severity": "low",
        "description": "legacy bytes key",
        "timestamp": "1700000001.0",
    },
}


class _FakeAsyncRedis:
    """Minimal stand-in for the shared async client used by list_conflicts."""

    def __init__(self, conflicts):
        self._conflicts = conflicts
        self.keys_called_with = None

    async def keys(self, pattern):
        self.keys_called_with = pattern
        return list(self._conflicts)

    async def hgetall(self, key):
        return self._conflicts[key]


def _install(monkeypatch, conflicts):
    """list_conflicts imports the factory inside the function body."""
    import autobot_shared.redis_client as rc

    fake = _FakeAsyncRedis(conflicts)

    async def _factory(*args, **kwargs):
        return fake

    monkeypatch.setattr(rc, "get_async_redis_client", _factory)
    return fake


async def _call(**overrides):
    """Invoke the endpoint with the values FastAPI would resolve the Query/Depends to."""
    kwargs = {
        "status": "pending",
        "severity": None,
        "limit": 20,
        "offset": 0,
        "current_user": "tester",
        "req": None,
    }
    kwargs.update(overrides)
    return await knowledge_grounding.list_conflicts(**kwargs)


@pytest.mark.asyncio
async def test_str_keys_do_not_500(monkeypatch):
    """The live configuration. Pre-fix this raised HTTPException(500)."""
    fake = _install(monkeypatch, DECODED_CONFLICTS)

    result = await _call()

    assert fake.keys_called_with == "conflict:*", "the conflict scan never ran"
    assert result["status"] == "success"
    assert result["total"] == 1
    conflict = result["conflicts"][0]
    assert conflict["conflict_id"] == "abc123"
    assert conflict["description"] == "KB says X, source says Y"
    assert conflict["severity"] == "high"
    assert conflict["resolution"] == "pending"
    assert conflict["timestamp"] == 1700000000.0


@pytest.mark.asyncio
async def test_non_empty_conflict_set_raises_no_http_error(monkeypatch):
    """Pin the exact live symptom: a populated conflict set used to 500."""
    _install(monkeypatch, DECODED_CONFLICTS)

    try:
        await _call()
    except HTTPException as exc:
        pytest.fail(f"GET /kb-conflicts raised HTTP {exc.status_code}: {exc.detail}")


@pytest.mark.asyncio
async def test_bytes_keys_still_work(monkeypatch):
    """A client without decode_responses must keep working."""
    _install(monkeypatch, BYTES_KEY_CONFLICTS)

    result = await _call()

    assert result["total"] == 1
    assert result["conflicts"][0]["conflict_id"] == "def456"


@pytest.mark.asyncio
async def test_empty_conflict_set_returns_empty_list(monkeypatch):
    """The only case that worked before the fix — it must still work."""
    _install(monkeypatch, {})

    result = await _call()

    assert result["total"] == 0
    assert result["conflicts"] == []
