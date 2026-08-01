# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""`get_stale_skills` must handle str keys from a decode_responses client.

The shared Redis client is created with ``decode_responses=True``, so ``keys()``
returns ``str``. The comprehension called ``.decode()`` unconditionally, raising
``AttributeError: 'str' object has no attribute 'decode'`` on every call — and
the surrounding ``except Exception`` swallowed it into ``[]``.

The caller therefore saw "no stale skills" rather than an error, while the live
backend logged the failure 3612 times. Both halves are pinned here: the str path
must work, and it must return the real skill ids rather than an empty list.
"""

from unittest.mock import AsyncMock

import pytest

from services.skill_management import skill_metrics as sm

PREFIX = sm.REDIS_SKILL_HEALTH_PREFIX


def _metrics(keys):
    inst = sm.SkillMetrics() if hasattr(sm, "SkillMetrics") else None
    if inst is None:  # pragma: no cover - class name guard
        pytest.skip("SkillMetrics not exported")
    redis = AsyncMock()
    redis.keys = AsyncMock(return_value=keys)
    inst._get_redis = AsyncMock(return_value=redis)
    return inst


@pytest.mark.asyncio
async def test_str_keys_are_handled(monkeypatch):
    """decode_responses=True yields str — the live configuration."""
    inst = _metrics([f"{PREFIX}alpha:stale", f"{PREFIX}beta:stale"])

    assert sorted(await inst.get_stale_skills()) == ["alpha", "beta"]


@pytest.mark.asyncio
async def test_bytes_keys_still_work():
    """A client without decode_responses must not regress."""
    inst = _metrics([f"{PREFIX}alpha:stale".encode(), f"{PREFIX}beta:stale".encode()])

    assert sorted(await inst.get_stale_skills()) == ["alpha", "beta"]


@pytest.mark.asyncio
async def test_no_stale_keys_returns_empty():
    inst = _metrics([])

    assert await inst.get_stale_skills() == []
