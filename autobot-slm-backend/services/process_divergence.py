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

    Is the deployed tree's newest file-write newer than the moment the
    unit(s) that run it last became active?

* ``"stale"``   — yes for at least one of the component's units: some
  process backing this component is running code older than what is on
  disk (the exact divergence #14866/#14010/#13570/#13747 need to see).
* ``"healthy"`` — every one of the component's units resolved and started
  at or after the newest deployed file.
* ``"unknown"`` — no unit came back "stale", but at least one side could
  not be determined for at least one unit (no deployed dir, no ``.py``
  file under it, systemd unavailable, unit never activated). This module
  never reports ``"healthy"`` when it cannot tell — a false "healthy" is
  the exact defect being fixed, so "cannot determine" must never collapse
  into the good answer, and neither may a partial "healthy" from checking
  only SOME of a multi-unit component's processes.

Deploy-time signal — ctime, not mtime (#15323 review)
-------------------------------------------------------
Every rsync invocation in ``api/code_sync.py`` uses ``-a``/``-avz``, and
``-a`` implies ``-t``: a deployed file keeps its SOURCE mtime (when the
line was last edited in git), not the moment it landed on this host. A file
last edited 10 days ago and deployed 5 minutes ago has an mtime from 10
days ago — comparing that against a process that started 5 days ago would
read "healthy" moments after that exact file was overwritten with new code.

ctime (inode change time) is used instead. rsync cannot preserve it — there
is no syscall that lets a caller set another file's ctime to an arbitrary
value; every write() and every explicit utime() call (which is exactly how
rsync applies the preserved mtime) stamps ctime to "now" as a side effect.
So ctime tracks the moment content actually landed on THIS filesystem,
which is precisely "was this file deployed here", while remaining stable
(not bumped) for any file rsync left untouched because it already matched.
The alternative of a separate deploy-time marker file/stamp was rejected as
a detector-side fix should not also require changing the sync's own rsync
flags (behavioural change, out of scope for a read-only detector) or adding
a new write path that could itself go stale.

Kept in ``services/`` (not ``api/code_sync.py``, already at its size ceiling)
and free of any ``api.*`` import — callers pass in the component -> systemd
unit(s) and component -> deployed-dir mappings ``code_sync.py`` already owns,
so this stays a pure, layering-clean detector.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Dict, Literal, Mapping, Optional, Sequence

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
# ctime walk plus a systemctl round-trip per unit is cheap but must not run
# on every /status poll.
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


def _newest_py_deploy_time(deployed_dir: str) -> Optional[float]:
    """Newest ``.py`` ctime under *deployed_dir*; None if absent or no ``.py`` file.

    ctime, not mtime — see the module docstring's "Deploy-time signal"
    section. rsync's ``-a`` (implies ``-t``) preserves the SOURCE mtime, so
    mtime answers "when was this line last edited", not "when did this
    file land on this host"; ctime answers the latter and is the one this
    detector needs.
    """
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
                ctime = (Path(dirpath) / filename).stat().st_ctime
            except OSError as exc:
                logger.warning("process-divergence: cannot stat %s/%s: %s", dirpath, filename, exc)
                continue
            if newest is None or ctime > newest:
                newest = ctime
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


def _unit_divergence(newest_deploy_time: Optional[float], active_since: Optional[float]) -> DivergenceStatus:
    """Single-unit verdict — "healthy" only when both sides resolved."""
    if newest_deploy_time is None or active_since is None:
        return "unknown"
    return "stale" if newest_deploy_time > active_since else "healthy"


def _aggregate_unit_statuses(statuses: Sequence[DivergenceStatus]) -> DivergenceStatus:
    """Conservative reduction over a component's units (#15323 review).

    A component restarts MULTIPLE units (autobot_shared fans out to every
    Python service; autobot-ai-stack pairs a compiled chromadb binary with
    the actual Python autobot-ai-stack unit). Checking only one unit let a
    healthy chromadb restart mask a still-stale Python process — the wrong
    process entirely for the ai-stack case. "stale" beats "unknown" beats
    "healthy" so any one bad unit is enough to withhold "healthy".
    """
    if any(status == "stale" for status in statuses):
        return "stale"
    if any(status == "unknown" for status in statuses):
        return "unknown"
    return "healthy"


async def _component_divergence(component: str, units: Sequence[str], deployed_dir: Optional[str]) -> DivergenceStatus:
    """Component verdict — aggregated over EVERY unit that backs it (#15323 review)."""
    if not deployed_dir or not units:
        return "unknown"
    newest_deploy_time = _newest_py_deploy_time(deployed_dir)
    statuses = [_unit_divergence(newest_deploy_time, await _service_active_since_epoch(unit)) for unit in units]
    return _aggregate_unit_statuses(statuses)


async def compute_process_divergence(
    units_by_component: Mapping[str, Sequence[str]],
    deployed_dir_by_component: Mapping[str, str],
    *,
    force: bool = False,
) -> Dict[str, DivergenceStatus]:
    """Per-component stale/healthy/unknown verdict, TTL-cached (#15323).

    *units_by_component* and *deployed_dir_by_component* are supplied by the
    caller (api/code_sync.py already owns ``_COMPONENT_SERVICES`` and
    ``get_live_dir``) so this module never imports ``api.*``.
    Every unit listed for a component is checked — see
    ``_aggregate_unit_statuses`` — not just the first.
    """
    now = time.monotonic()
    if not force and now - _cache["ts"] < PROCESS_DIVERGENCE_TTL_SECONDS:
        return _cache["value"]

    result: Dict[str, DivergenceStatus] = {}
    for component, units in units_by_component.items():
        deployed_dir = deployed_dir_by_component.get(component)
        try:
            result[component] = await _component_divergence(component, units, deployed_dir)
        except Exception:  # noqa: BLE001 - one bad component must not break the scan
            logger.exception("process-divergence: scan failed for %s", component)
            result[component] = "unknown"

    _cache["ts"] = now
    _cache["value"] = result
    return result
