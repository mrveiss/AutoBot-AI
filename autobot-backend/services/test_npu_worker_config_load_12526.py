# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Regression tests for #12526.

`_load_workers_from_config` used to call the async `_save_workers_to_config`
without awaiting it when the config file was missing, silently discarding the
coroutine (and emitting a "coroutine was never awaited" RuntimeWarning). It is
now `async` and awaits the save directly.
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.npu_worker_manager import NPUWorkerManager

_WORKER_ID = "test-worker-1"


def _make_manager(config_file: Path) -> NPUWorkerManager:
    """Construct NPUWorkerManager with __init__ bypassed for heavy I/O."""
    mgr = NPUWorkerManager.__new__(NPUWorkerManager)
    mgr._workers = {}
    mgr._worker_clients = {}
    mgr._health_check_task = None
    mgr._failover_monitor_task = None
    mgr._pulse_task = None
    mgr._running = False
    mgr._load_balancing_config = MagicMock()
    mgr._load_balancing_config.health_check_interval = 30
    mgr._load_balancing_config.timeout_seconds = 10
    mgr._worker_failure_counts = {}
    mgr._worker_next_check = {}
    mgr._pulse_failure_counts = {}
    mgr._pulse_canaries = {}
    mgr._pulse_defaults = {}
    mgr.redis_client = None
    mgr.config_file = config_file
    return mgr


@pytest.mark.asyncio
async def test_load_workers_from_config_awaits_save_when_file_missing(tmp_path):
    """Missing config file: _load_workers_from_config must actually await the save."""
    missing_config = tmp_path / "npu_workers.yaml"
    assert not missing_config.exists()

    mgr = _make_manager(missing_config)
    mgr._save_workers_to_config = AsyncMock()

    await mgr._load_workers_from_config()

    mgr._save_workers_to_config.assert_awaited_once()


@pytest.mark.asyncio
async def test_load_workers_from_config_persists_file_end_to_end(tmp_path):
    """End-to-end (no mocking of the save): the config file must exist afterwards.

    This is the real regression check — before the fix, the save coroutine was
    created and discarded, so the file was never written.
    """
    missing_config = tmp_path / "npu_workers.yaml"
    mgr = _make_manager(missing_config)

    await mgr._load_workers_from_config()

    assert missing_config.exists(), "config file should have been created by the awaited save"


@pytest.mark.asyncio
async def test_load_workers_from_config_does_not_save_when_file_present(tmp_path):
    """Existing config file: the save path must not be invoked at all."""
    existing_config = tmp_path / "npu_workers.yaml"
    existing_config.write_text("workers: []\nload_balancing: {}\n", encoding="utf-8")

    mgr = _make_manager(existing_config)
    mgr._save_workers_to_config = AsyncMock()

    await mgr._load_workers_from_config()

    mgr._save_workers_to_config.assert_not_awaited()


@pytest.mark.asyncio
async def test_initialize_impl_awaits_load_workers_from_config():
    """_initialize_impl must directly await _load_workers_from_config (no fire-and-forget)."""
    # #12857: a real repo path here risks a write into the working tree.
    mgr = _make_manager(Path(tempfile.gettempdir()) / "autobot-test-npu-workers.yaml")
    mgr._load_workers_from_config = AsyncMock()

    result = await mgr._initialize_impl()

    assert result is True
    mgr._load_workers_from_config.assert_awaited_once()
