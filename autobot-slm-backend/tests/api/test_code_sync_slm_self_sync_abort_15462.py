# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15462 — a failed frontend build must fail the WHOLE self-sync, loudly.

Before this fix, ``_sync_slm_from_code_source`` called ``_build_slm_frontend``
and ignored its outcome entirely (the function returned ``None``), then
unconditionally marked the node up to date and restarted services — so a
build that produced no ``index.html`` was reported as a success.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _code_sync_import import import_code_sync  # noqa: E402

import_code_sync()

import asyncio  # noqa: E402

from api.code_sync import _sync_slm_from_code_source  # noqa: E402


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_build_failure_skips_mark_up_to_date_and_restart() -> None:
    with (
        patch(
            "api.code_sync._fetch_code_source_connection_info",
            AsyncMock(return_value=("127.0.0.1", "autobot", "/opt/autobot/code_source")),
        ),
        patch("autobot_shared.network_utils.is_local_ip", return_value=True),
        patch("api.code_sync._rsync_component_local", AsyncMock(return_value=(True, "ok"))),
        patch("api.code_sync._install_slm_pip_dependencies", AsyncMock(return_value=False)),
        patch("api.code_sync._build_slm_frontend", AsyncMock(return_value=False)) as build_mock,
        patch("api.code_sync._mark_slm_node_up_to_date", AsyncMock()) as mark_mock,
        patch("api.code_sync._restart_slm_service", AsyncMock()) as restart_mock,
    ):
        _run(_sync_slm_from_code_source("slm-node-1", "job-1"))

    build_mock.assert_awaited_once()
    mark_mock.assert_not_awaited()
    restart_mock.assert_not_awaited()


def test_build_success_still_marks_up_to_date_and_restarts() -> None:
    with (
        patch(
            "api.code_sync._fetch_code_source_connection_info",
            AsyncMock(return_value=("127.0.0.1", "autobot", "/opt/autobot/code_source")),
        ),
        patch("autobot_shared.network_utils.is_local_ip", return_value=True),
        patch("api.code_sync._rsync_component_local", AsyncMock(return_value=(True, "ok"))),
        patch("api.code_sync._install_slm_pip_dependencies", AsyncMock(return_value=False)),
        patch("api.code_sync._build_slm_frontend", AsyncMock(return_value=True)),
        patch("api.code_sync._mark_slm_node_up_to_date", AsyncMock()) as mark_mock,
        patch("api.code_sync._restart_slm_service", AsyncMock()) as restart_mock,
    ):
        _run(_sync_slm_from_code_source("slm-node-1", "job-1"))

    mark_mock.assert_awaited_once()
    assert restart_mock.await_count == 2  # autobot-slm-backend + nginx
