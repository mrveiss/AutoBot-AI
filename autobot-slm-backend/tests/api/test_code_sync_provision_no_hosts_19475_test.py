# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The python-provision play reports success only when its recap proves localhost ran (#19475)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _code_sync_import import import_code_sync  # noqa: E402

import_code_sync()

import asyncio  # noqa: E402

from api.code_sync import _run_python_provision_playbook  # noqa: E402

_NO_HOSTS = b"[WARNING]: No inventory was parsed\nskipping: no hosts matched\nPLAY RECAP ****\n"
_GOOD = b"PLAY RECAP ***\nlocalhost : ok=11 changed=1 unreachable=0 failed=0\n"


def _provision(output: bytes) -> tuple[bool, list]:
    async def fake_exec(*_cmd, **_kw):
        proc = MagicMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(output, b""))
        return proc

    steps: list = []
    loop = asyncio.new_event_loop()
    try:
        with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
            return loop.run_until_complete(_run_python_provision_playbook("python3.14", steps)), steps
    finally:
        loop.close()


def test_a_no_hosts_run_that_exits_zero_is_a_failed_provision() -> None:
    ok, steps = _provision(_NO_HOSTS)
    assert ok is False
    assert any("FAILED" in s for s in steps)


def test_a_recap_listing_localhost_is_a_successful_provision() -> None:
    ok, _steps = _provision(_GOOD)
    assert ok is True
