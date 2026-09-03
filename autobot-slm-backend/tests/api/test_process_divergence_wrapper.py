# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for api.code_sync._compute_process_divergence (#15323 review).

BLOCKING 1 from PR #15371 review: the wrapper originally passed only
``svcs[0]`` for each component, silently checking one unit (or the WRONG
unit — autobot-ai-stack's first-listed unit is the compiled chromadb
binary, not the Python process the detector needs) instead of every unit
_COMPONENT_SERVICES actually restarts for that component. The wrapper had
zero tests before this file — that is how it got through review the first
time.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

# ---------------------------------------------------------------------------
# #12572: import api.code_sync via the shared helper (see
# test_code_sync_symlink_restore.py's module docstring for the full
# rationale).
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _code_sync_import import import_code_sync  # noqa: E402

import_code_sync()

import asyncio  # noqa: E402

from api.code_sync import _compute_process_divergence  # noqa: E402


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_wrapper_passes_every_unit_not_just_the_first() -> None:
    """autobot_shared restarts 6 units — the wrapper must forward all 6, not
    just _COMPONENT_SERVICES["autobot_shared"][0]."""
    captured = {}

    async def _fake_compute(units_by_component, deployed_dir_by_component, **kw):
        captured.update(units_by_component)
        return {}

    with patch("services.process_divergence.compute_process_divergence", side_effect=_fake_compute):
        _run(_compute_process_divergence())

    import api.code_sync as cs

    assert captured["autobot_shared"] == cs._COMPONENT_SERVICES["autobot_shared"]
    assert len(captured["autobot_shared"]) == 6


def test_wrapper_passes_the_real_ai_stack_unit_not_just_chromadb() -> None:
    """autobot-ai-stack's FIRST unit is autobot-chromadb (a compiled binary);
    the actual Python unit, autobot-ai-stack, must also be forwarded."""
    captured = {}

    async def _fake_compute(units_by_component, deployed_dir_by_component, **kw):
        captured.update(units_by_component)
        return {}

    with patch("services.process_divergence.compute_process_divergence", side_effect=_fake_compute):
        _run(_compute_process_divergence())

    assert captured["autobot-ai-stack"] == ["autobot-chromadb", "autobot-ai-stack"]


def test_wrapper_excludes_nginx_only_frontend_components() -> None:
    captured = {}

    async def _fake_compute(units_by_component, deployed_dir_by_component, **kw):
        captured.update(units_by_component)
        return {}

    with patch("services.process_divergence.compute_process_divergence", side_effect=_fake_compute):
        _run(_compute_process_divergence())

    assert "autobot-frontend" not in captured
    assert "autobot-slm-frontend" not in captured


def test_wrapper_degrades_to_empty_dict_on_unexpected_failure() -> None:
    """#15323 review non-blocking item: a scan failure must degrade /status,
    not break it — matches _compute_stale_components' invariant."""
    with patch("services.process_divergence.compute_process_divergence", side_effect=RuntimeError("boom")):
        result = _run(_compute_process_divergence())

    assert result == {}


def test_wrapper_forwards_deployed_dir_per_component() -> None:
    captured_dirs = {}

    async def _fake_compute(units_by_component, deployed_dir_by_component, **kw):
        captured_dirs.update(deployed_dir_by_component)
        return {}

    with patch("services.process_divergence.compute_process_divergence", side_effect=_fake_compute):
        _run(_compute_process_divergence())

    import api.code_sync as cs

    assert captured_dirs["autobot-backend"] == cs.get_live_dir("autobot-backend")
