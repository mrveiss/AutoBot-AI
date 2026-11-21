# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""When this backend last started, for the upgrade-boot grandfather scope (#17421).

Order (owner ruling 2026-11-21): the start the database recorded; else the marker the builtin updater wrote
before restarting the backend; else the last ``PluginManager: starting plugin discovery`` line in the
backend logs that this boot did not write; else nothing, and the caller grandfathers nothing.

A plugin's age is read from file times, which an archive can preserve or forge: this is a heuristic.
"""

import asyncio
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple

import psutil

from autobot_shared.backend_start_marker import read_marker
from autobot_shared.log_dir import resolve_logs_dir
from autobot_shared.logging_manager import get_logger
from plugin_enable_state import PluginEnableStore

logger = get_logger(__name__)

#: The line ``PluginManager.startup`` logs first; one per backend start.
START_LINE = "PluginManager: starting plugin discovery"
_STAMP = "%Y-%m-%d %H:%M:%S"  # the default log format's asctime, to the second


def boot_started_at() -> float:
    """When this boot began: the earlier of this process and its parent (a worker's supervisor)."""
    started = [psutil.Process().create_time()]
    try:
        started.append(psutil.Process(os.getppid()).create_time())
    except psutil.Error:
        pass
    return min(started)


def _line_time(line: str) -> float | None:
    try:
        return time.mktime(time.strptime(line[:19], _STAMP))
    except ValueError:
        return None


def last_logged_start(logs_dir: Path, boot_started: float) -> datetime | None:
    """The newest start line in *logs_dir* written before *boot_started* (so never this boot's own)."""
    best = None
    for log in sorted(logs_dir.glob("*.log*"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        stamps = [_line_time(ln) for ln in lines if START_LINE in ln]
        earlier = [t for t in stamps if t is not None and t < boot_started]
        if earlier:
            best = max(earlier)
            break
    return datetime.fromtimestamp(best, tz=timezone.utc) if best else None


async def previous_start(store: PluginEnableStore) -> Tuple[datetime | None, str]:
    """``(when, source)``; ``(None, "none")`` when no source knows."""
    recorded = await store.last_start()
    if recorded is not None:
        return recorded, "recorded start"
    marker = await asyncio.to_thread(read_marker)
    if marker is not None:
        return marker, "updater marker"
    try:
        logged = await asyncio.to_thread(last_logged_start, resolve_logs_dir(), boot_started_at())
    except OSError as exc:
        logger.warning("Plugin gate: cannot read the backend logs for a previous start: %s", exc)
        logged = None
    return (logged, "backend log") if logged is not None else (None, "none")
