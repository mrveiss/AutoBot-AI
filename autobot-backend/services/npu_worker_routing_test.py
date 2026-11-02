# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""NPU requests reach every paired worker and survive one failing (#19706)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from services import npu_worker_manager, npu_worker_routing
from services.npu_client import NPUClient

CONFIGURED = "http://configured:1"


def _worker(url, status="online", priority=5, load=0):
    return SimpleNamespace(
        config=SimpleNamespace(url=url, priority=priority),
        status=SimpleNamespace(status=status, current_load=load),
    )


def _registry(*workers):
    return SimpleNamespace(get_healthy_workers_sorted=AsyncMock(return_value=list(workers)))


async def _urls(registry):
    with patch.object(npu_worker_manager, "_worker_manager", registry):
        return await npu_worker_routing.npu_worker_urls(CONFIGURED)


@pytest.mark.asyncio
async def test_a_process_without_a_registry_uses_the_configured_url():
    assert await _urls(None) == [CONFIGURED]


@pytest.mark.asyncio
async def test_no_paired_worker_uses_the_configured_url():
    assert await _urls(_registry()) == [CONFIGURED]


@pytest.mark.asyncio
async def test_an_unreadable_registry_uses_the_configured_url():
    registry = SimpleNamespace(get_healthy_workers_sorted=AsyncMock(side_effect=OSError("down")))
    assert await _urls(registry) == [CONFIGURED]


@pytest.mark.asyncio
async def test_equal_workers_take_turns():
    registry = _registry(_worker("http://a:1"), _worker("http://b:1"))
    assert {(await _urls(registry))[0] for _ in range(2)} == {"http://a:1", "http://b:1"}


@pytest.mark.asyncio
async def test_a_less_loaded_worker_stays_first():
    registry = _registry(_worker("http://a:1"), _worker("http://b:1", load=3))
    assert {(await _urls(registry))[0] for _ in range(3)} == {"http://a:1"}


@pytest.mark.asyncio
async def test_the_configured_url_is_not_listed_twice():
    assert await _urls(_registry(_worker(CONFIGURED + "/"))) == [CONFIGURED]


@pytest.mark.asyncio
async def test_inference_moves_to_the_next_worker_when_one_fails():
    post = AsyncMock(side_effect=[RuntimeError("dead"), {"answer": 1}])
    with (
        patch.object(npu_worker_routing, "npu_worker_urls", AsyncMock(return_value=["http://a:1", "http://b:1"])),
        patch.object(npu_worker_routing, "_post_inference", post),
    ):
        assert await npu_worker_routing.post_inference_with_failover(CONFIGURED, {}, 1) == {"answer": 1}
    assert [call.args[0] for call in post.await_args_list] == ["http://a:1", "http://b:1"]


@pytest.mark.asyncio
async def test_inference_raises_when_every_worker_fails():
    post = AsyncMock(side_effect=RuntimeError("dead"))
    with (
        patch.object(npu_worker_routing, "npu_worker_urls", AsyncMock(return_value=["http://a:1", "http://b:1"])),
        patch.object(npu_worker_routing, "_post_inference", post),
        pytest.raises(RuntimeError),
    ):
        await npu_worker_routing.post_inference_with_failover(CONFIGURED, {}, 1)


@pytest.mark.asyncio
async def test_embeddings_move_to_the_next_worker_when_one_fails():
    client = NPUClient()
    embed = AsyncMock(side_effect=[None, "result"])
    with (
        patch.object(client, "_worker_urls", AsyncMock(return_value=["http://a:1", "http://b:1"])),
        patch.object(client, "_embed_on_worker", embed),
    ):
        assert await client.generate_embeddings(["text"], model_name="m") == "result"
    assert [call.args[0] for call in embed.await_args_list] == ["http://a:1", "http://b:1"]


@pytest.mark.asyncio
async def test_a_client_built_for_one_url_stays_on_it():
    assert await NPUClient(base_url="http://only:1")._worker_urls() == ["http://only:1"]


@pytest.mark.asyncio
async def test_a_configured_url_with_a_trailing_slash_is_not_listed_twice():
    registry = _registry(_worker(CONFIGURED))
    with patch.object(npu_worker_manager, "_worker_manager", registry):
        assert await npu_worker_routing.npu_worker_urls(CONFIGURED + "/") == [CONFIGURED]


def test_workers_share_one_deadline():
    clock = iter([100.0, 100.0, 107.0, 111.0])
    with patch.object(npu_worker_routing, "time", SimpleNamespace(monotonic=lambda: next(clock))):
        attempts = list(npu_worker_routing.worker_attempts(["a", "b", "c"], 10))
    assert attempts == [("a", 10.0), ("b", 3.0)]


@pytest.mark.asyncio
async def test_inference_out_of_time_raises_without_a_call():
    post = AsyncMock()
    with (
        patch.object(npu_worker_routing, "npu_worker_urls", AsyncMock(return_value=["http://a:1"])),
        patch.object(npu_worker_routing, "_post_inference", post),
        pytest.raises(TimeoutError),
    ):
        await npu_worker_routing.post_inference_with_failover(CONFIGURED, {}, 0)
    post.assert_not_awaited()


@pytest.mark.asyncio
async def test_transcription_moves_to_the_next_worker_when_one_fails():
    client = NPUClient()
    transcribe = AsyncMock(side_effect=[None, "words"])
    with (
        patch.object(client, "_worker_urls", AsyncMock(return_value=["http://a:1", "http://b:1"])),
        patch.object(client, "_transcribe_on_worker", transcribe),
    ):
        assert await client.transcribe_audio("/a.wav") == "words"
    assert [call.args[0] for call in transcribe.await_args_list] == ["http://a:1", "http://b:1"]


@pytest.mark.asyncio
async def test_one_worker_down_leaves_the_npu_available():
    from ai_hardware_accelerator import AIHardwareAccelerator, HardwareDevice

    manager = AIHardwareAccelerator.__new__(AIHardwareAccelerator)
    manager.npu_worker_url = CONFIGURED
    manager.device_status = {HardwareDevice.NPU: {"available": False}}

    async def probe(url):
        manager.device_status[HardwareDevice.NPU]["available"] = url == "http://b:1"

    with (
        patch("ai_hardware_accelerator.npu_worker_urls", AsyncMock(return_value=["http://a:1", "http://b:1"])),
        patch.object(manager, "_probe_npu_worker", probe),
    ):
        await manager._check_npu_availability()
    assert manager.device_status[HardwareDevice.NPU]["available"] is True
