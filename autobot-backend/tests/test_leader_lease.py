# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the shared Redis leader lease (GH#12835).

Leader election was implemented twice with a byte-identical Lua script. These
tests cover the single extracted implementation, in particular the atomic
compare-and-extend that exists so a GC pause cannot produce two leaders.
"""

from unittest.mock import AsyncMock, patch

import pytest

from autobot_shared.leader_lease import LeaderLease


def _lease(**kw) -> LeaderLease:
    return LeaderLease(key="test:leader", database="knowledge", worker_id="worker-1", label="Test", **kw)


def _redis(**kw) -> AsyncMock:
    r = AsyncMock()
    for name, value in kw.items():
        getattr(r, name).return_value = value
    return r


@pytest.mark.asyncio
async def test_acquires_with_set_nx_when_not_leader():
    redis = _redis(set=True)
    with patch("autobot_shared.leader_lease.get_async_redis_client", return_value=redis):
        lease = _lease()
        assert await lease.try_acquire_or_refresh() is True

    kwargs = redis.set.call_args.kwargs
    assert kwargs["nx"] is True, "must not steal a lease another worker holds"
    assert kwargs["px"] == lease.ttl_ms
    redis.eval.assert_not_called()


@pytest.mark.asyncio
async def test_contended_acquisition_returns_false():
    """SET NX returns None when another worker already holds the key."""
    redis = _redis(set=None)
    with patch("autobot_shared.leader_lease.get_async_redis_client", return_value=redis):
        assert await _lease().try_acquire_or_refresh() is False


@pytest.mark.asyncio
async def test_refresh_uses_atomic_lua_when_already_leader():
    """The held path must compare-and-extend in ONE round-trip (the #12835 guarantee)."""
    redis = _redis(set=True, eval=1)
    with patch("autobot_shared.leader_lease.get_async_redis_client", return_value=redis):
        lease = _lease()
        await lease.update_leadership()
        assert lease.is_leader is True

        redis.set.reset_mock()
        assert await lease.try_acquire_or_refresh() is True

    redis.eval.assert_awaited_once()
    redis.set.assert_not_called()  # no non-atomic GET->PEXPIRE fallback
    script, numkeys, key, worker, ttl = redis.eval.call_args.args
    assert numkeys == 1 and key == "test:leader" and worker == "worker-1"
    assert ttl == str(lease.ttl_ms)


@pytest.mark.asyncio
async def test_lease_stolen_by_another_worker_is_not_extended():
    """Lua returns 0 when the key no longer holds our id — we must drop leadership."""
    redis = _redis(set=True, eval=0)
    with patch("autobot_shared.leader_lease.get_async_redis_client", return_value=redis):
        lease = _lease()
        await lease.update_leadership()
        assert lease.is_leader is True

        lost = []
        assert await lease.update_leadership(on_lost=lambda: lost.append(1)) is False
        assert lease.is_leader is False
        assert lost == [1], "on_lost must fire so the worker stops its work"


@pytest.mark.asyncio
async def test_transition_hooks_fire_once_per_change():
    redis = _redis(set=True, eval=1)
    with patch("autobot_shared.leader_lease.get_async_redis_client", return_value=redis):
        lease = _lease()
        acquired = []
        await lease.update_leadership(on_acquired=lambda: acquired.append(1))
        await lease.update_leadership(on_acquired=lambda: acquired.append(1))

    assert acquired == [1], "on_acquired must not re-fire while leadership is retained"


@pytest.mark.asyncio
async def test_async_hooks_are_awaited():
    redis = _redis(set=True)
    calls = []

    async def hook():
        calls.append("awaited")

    with patch("autobot_shared.leader_lease.get_async_redis_client", return_value=redis):
        await _lease().update_leadership(on_acquired=hook)

    assert calls == ["awaited"]


@pytest.mark.asyncio
async def test_unavailable_redis_does_not_grant_leadership():
    """No Redis must mean no leader — never a default-yes."""
    with patch("autobot_shared.leader_lease.get_async_redis_client", return_value=None):
        assert await _lease().try_acquire_or_refresh() is False


@pytest.mark.asyncio
async def test_redis_error_does_not_grant_leadership():
    redis = AsyncMock()
    redis.set.side_effect = RuntimeError("connection reset")
    with patch("autobot_shared.leader_lease.get_async_redis_client", return_value=redis):
        assert await _lease().try_acquire_or_refresh() is False


@pytest.mark.asyncio
async def test_release_only_deletes_a_lease_we_still_hold():
    redis = _redis(set=True, get=b"worker-1")
    with patch("autobot_shared.leader_lease.get_async_redis_client", return_value=redis):
        lease = _lease()
        await lease.update_leadership()
        await lease.release()

    redis.delete.assert_awaited_once_with("test:leader")


@pytest.mark.asyncio
async def test_release_does_not_delete_a_lease_another_worker_took():
    """Our lease expired and worker-2 took it — deleting would evict a live leader."""
    redis = _redis(set=True, get=b"worker-2")
    with patch("autobot_shared.leader_lease.get_async_redis_client", return_value=redis):
        lease = _lease()
        await lease.update_leadership()
        await lease.release()

    redis.delete.assert_not_called()
    assert lease.is_leader is False


@pytest.mark.asyncio
async def test_refresh_interval_is_shorter_than_the_lease():
    """A refresh slower than the TTL would drop a lease that is still held."""
    lease = _lease()
    assert lease.refresh_s * 1000 < lease.ttl_ms


def test_worker_id_defaults_are_unique_per_process():
    a = LeaderLease(key="k")
    assert a.worker_id and "-" in a.worker_id
