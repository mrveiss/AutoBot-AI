# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The pip timeout message follows the configured timeout, not a fixed 300 s (#18056)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api import venv_reconcile


@pytest.mark.asyncio
async def test_a_configured_pip_timeout_is_the_one_reported(tmp_path):
    steps: list[str] = []
    proc = MagicMock()
    with (
        patch.object(venv_reconcile, "_PIP_INSTALL_TIMEOUT", 42.0),
        patch.object(venv_reconcile.provenance, "clear_venv_husks", return_value=[]),
        patch.object(venv_reconcile.asyncio, "create_subprocess_exec", AsyncMock(return_value=proc)),
        patch.object(venv_reconcile.asyncio, "wait_for", AsyncMock(side_effect=asyncio.TimeoutError)),
    ):
        ok = await venv_reconcile._run_pip_install("c", "req.txt", str(tmp_path / "venv/bin/pip"), steps)
    assert ok is False
    assert "pip: install timed out after 42s" in steps
