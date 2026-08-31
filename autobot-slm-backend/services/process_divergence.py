# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Runtime code-divergence detector (#15323).

A code-sync resolve job can rewrite a component's deployed tree and then, on
a post-sync failure whose revert also fails, never restart the service that
loaded it — the job row reads "failed" but nothing previously compared what
the RUNNING process actually loaded against what is now on disk. That
comparison is what this module answers, per component:

    Is the newest source file under the deployed tree newer than the moment
    the service that runs it last became active?

* ``"stale"``   — yes: the process is running code older than what is on
  disk (the exact divergence #14866/#14010/#13570/#13747 need to see).
* ``"healthy"`` — no: the process started at or after the newest file.
* ``"unknown"`` — either side could not be determined (no deployed dir, no
  ``.py`` file under it, systemd unavailable, unit never activated). This
  module never reports ``"healthy"`` when it cannot tell — a false
  "healthy" is the exact defect being fixed, so "cannot determine" must
  never collapse into the good answer.

Kept in ``services/`` (not ``api/code_sync.py``, already at its size ceiling)
and free of any ``api.*`` import — callers pass in the component -> systemd
unit and component -> deployed-dir mappings ``code_sync.py`` already owns,
so this stays a pure, layering-clean detector.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Dict, Literal, Mapping, Optional

from services.deploy_artifacts import ARTIFACT_DIR_SUFFIXES, ARTIFACT_DIRS

# Plain stdlib logging, deliberately (#15323). This module is real-loaded (not
# MagicMock-stubbed) by autobot-slm-backend/conftest.py so api/code_sync.py's
# tests exercise the genuine detector; `autobot_shared.logging_manager.get_logger`
# builds a RotatingFileHandler from config at call time and raises under that
# harness (config is itself a MagicMock there). Same trade as
# `autobot_shared/user_management/password_epoch.py`, which CLAUDE.md's pattern
# table names as the sanctioned exception for exactly this case.
logger = logging.getLogger(__name__)

DivergenceStatus = Literal["stale", "healthy", "unknown"]

# #15323: TTL for the per-component divergence scan, mirroring the existing
# _STALE_COMPONENTS_TTL_SECONDS pattern in api/code_sync.py — a full-tree
# mtime walk plus a systemctl round-trip per component is cheap but must not
# run on every /status poll.
PROCESS_DIVERGENCE_TTL_SECONDS = int(os.getenv("SLM_PROCESS_DIVERGENCE_TTL_SECONDS", "60"))

# Timeout for each `systemctl show` round-trip — a hung systemd must not hang
# the /status endpoint it is reported through.
_SYSTEMCTL_TIMEOUT_SECONDS = float(os.getenv("SLM_SYSTEMCTL_SHOW_TIMEOUT_SECONDS", "5"))

# Reuse the SAME artifact vocabulary drift_checker prunes its walk with
# (#11459) so a build cache or venv under the deployed tree can never read as
# a "newer" source file.
_SKIP_DIRS = set(ARTIFACT_DIRS)
_SKIP_DIR_SUFFIXES = ARTIFACT_DIR_SUFFIXES

_cache: dict = {"ts": -PROCESS_DIVERGENCE_TTL_SECONDS - 1.0, "value": {}}


def invalidate_process_divergence_cache() -> None:
    """Bust the TTL cache so the next call re-scans immediately (#15323).

    Mirrors ``_invalidate_stale_components_cache`` in api/code_sync.py — a
    caller that just resynced or restarted a component needs the fresh
    verdict, not a snapshot from before the change.
    """
    _cache["ts"] = -PROCESS_DIVERGENCE_TTL_SECONDS - 1.0


def _newest_py_mtime(deployed_dir: str) -> Optional[float]:
    """Newest ``.py`` mtime under *deployed_dir*; None if absent or no ``.py`` file."""
    root = Path(deployed_dir)
    if not root.is_dir():
        return None
    newest: Optional[float] = None
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.endswith(_SKIP_DIR_SUFFIXES)]
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            try:
                mtime = (Path(dirpath) / filename).stat().st_mtime
            except OSError as exc:
                logger.warning("process-divergence: cannot stat %s/%s: %s", dirpath, filename, exc)
                continue
            if newest is None or mtime > newest:
                newest = mtime
    return newest


async def _service_active_since_epoch(unit: str) -> Optional[float]:
    """Best-effort wall-clock epoch seconds *unit* last entered 'active'.

    Reads ``ActiveEnterTimestampMonotonic`` (microseconds since boot) rather
    than the human ``ActiveEnterTimestamp`` string — the monotonic form is a
    plain integer, immune to locale/timezone parsing, at the cost of being an
    estimate once converted to wall-clock (bounded by this call's own
    scheduling jitter, immaterial next to the minutes-to-days windows this
    detector distinguishes). Returns None on any systemd/parse failure or when
    the unit has never activated (value ``0``) — callers must treat that as
    "cannot determine", never as "started now".
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "systemctl",
            "show",
            unit,
            "--property=ActiveEnterTimestampMonotonic",
            "--value",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=_SYSTEMCTL_TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001 - a bad unit must report unknown, not raise
        logger.warning("process-divergence: systemctl show %s failed: %s", unit, exc)
        return None

    raw = (stdout.decode(errors="replace") if stdout else "").strip()
    try:
        active_since_boot_us = int(raw)
    except ValueError:
        logger.warning("process-divergence: unparsable ActiveEnterTimestampMonotonic for %s: %r", unit, raw)
        return None
    if active_since_boot_us <= 0:
        return None  # unit never activated

    now_monotonic_us = time.clock_gettime(time.CLOCK_MONOTONIC) * 1_000_000
    seconds_ago = (now_monotonic_us - active_since_boot_us) / 1_000_000
    return time.time() - seconds_ago


async def _component_divergence(component: str, unit: str, deployed_dir: Optional[str]) -> DivergenceStatus:
    """Single-component verdict — never "healthy" unless BOTH sides resolved."""
    if not deployed_dir:
        return "unknown"
    newest_mtime = _newest_py_mtime(deployed_dir)
    if newest_mtime is None:
        return "unknown"
    active_since = await _service_active_since_epoch(unit)
    if active_since is None:
        return "unknown"
    return "stale" if newest_mtime > active_since else "healthy"


async def compute_process_divergence(
    unit_by_component: Mapping[str, str],
    deployed_dir_by_component: Mapping[str, str],
    *,
    force: bool = False,
) -> Dict[str, DivergenceStatus]:
    """Per-component stale/healthy/unknown verdict, TTL-cached (#15323).

    *unit_by_component* and *deployed_dir_by_component* are supplied by the
    caller (api/code_sync.py already owns ``_COMPONENT_SERVICES`` and
    ``get_default_deployed_dir``) so this module never imports ``api.*``.
    """
    now = time.monotonic()
    if not force and now - _cache["ts"] < PROCESS_DIVERGENCE_TTL_SECONDS:
        return _cache["value"]

    result: Dict[str, DivergenceStatus] = {}
    for component, unit in unit_by_component.items():
        deployed_dir = deployed_dir_by_component.get(component)
        try:
            result[component] = await _component_divergence(component, unit, deployed_dir)
        except Exception:  # noqa: BLE001 - one bad component must not break the scan
            logger.exception("process-divergence: scan failed for %s", component)
            result[component] = "unknown"

    _cache["ts"] = now
    _cache["value"] = result
    return result
