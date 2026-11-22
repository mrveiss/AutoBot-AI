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
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Tuple

import psutil

from autobot_shared.backend_start_marker import read_marker
from autobot_shared.log_dir import resolve_logs_dir
from autobot_shared.logging_manager import get_logger
from plugin_enable_state import PluginEnableStore

logger = get_logger(__name__)

#: ``PluginManager.startup`` logs this first, once per backend start, through this logger.
START_LOGGER = "autobot_shared.plugin_sdk.plugin_manager"
START_MESSAGE = "PluginManager: starting plugin discovery"
#: The default log format is ``<asctime> - <logger> - <level> - <message>``.
START_LINE = re.compile(rf" - {re.escape(START_LOGGER)} - [A-Z]+ - {re.escape(START_MESSAGE)}")
#: Only the end of a log file is read: the previous start is recent, and a rotated file can be large.
LOG_TAIL_BYTES = 8 * 1024 * 1024
#: ``asctime`` is the process's LOCAL time with no zone, so it is read with ``mktime`` as local time. A
#: host whose zone changed since the line was written shifts the result by the difference.
_STAMP = "%Y-%m-%d %H:%M:%S"


#: A parent with one of these names is a service manager, not the backend's own worker supervisor.
INIT_PROCESS_NAMES = frozenset({"systemd", "init", "launchd"})


def _is_service_manager(parent: psutil.Process) -> bool:
    """True for PID 1 or a systemd/init process: its start time is the host's (or user session's), not ours."""
    return parent.pid == 1 or parent.name() in INIT_PROCESS_NAMES


def boot_started_at() -> float:
    """When this boot began: the earlier of this process and its parent, when the parent supervises workers.

    A uvicorn worker's parent is the backend's own supervisor, so its start line is a sibling's from the
    same boot. Started directly by systemd, the parent is the service manager, whose start time is the
    host boot: using it would reject every earlier start line in this boot, so only this process counts.
    """
    started = [psutil.Process().create_time()]
    try:
        parent = psutil.Process(os.getppid())
        if not _is_service_manager(parent):
            started.append(parent.create_time())
    except psutil.Error:
        pass
    return min(started)


def _line_time(line: str) -> float | None:
    try:
        return time.mktime(time.strptime(line[:19], _STAMP))
    except (ValueError, OverflowError):
        return None


def _tail_lines(log: Path) -> Iterator[str]:
    """The lines in the last ``LOG_TAIL_BYTES`` of *log*, streamed; a cut first line is dropped."""
    with log.open("rb") as handle:
        size = handle.seek(0, os.SEEK_END)
        cut = size > LOG_TAIL_BYTES
        handle.seek(max(0, size - LOG_TAIL_BYTES))
        for index, raw in enumerate(handle):
            if not (cut and index == 0):
                yield raw.decode("utf-8", errors="replace")


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def last_logged_start(logs_dir: Path, boot_started: float) -> datetime | None:
    """The newest start line in *logs_dir* written before *boot_started* (so never this boot's own).

    Newest file first, compressed rotations skipped. A start line whose timestamp cannot be read is
    counted and logged, then ignored.
    """
    candidates = [p for p in logs_dir.glob("*.log*") if p.suffix != ".gz"]
    for log in sorted(candidates, key=_mtime, reverse=True):
        stamps, unparsable = [], 0
        try:
            for line in _tail_lines(log):
                if START_LINE.search(line):
                    stamp = _line_time(line)
                    if stamp is None:
                        unparsable += 1
                    else:
                        stamps.append(stamp)
        except OSError as exc:
            logger.warning("Plugin gate: cannot read %s for a previous start: %s", log, exc)
            continue
        if unparsable:
            logger.warning("Plugin gate: %d start line(s) in %s had an unreadable timestamp", unparsable, log)
        earlier = [t for t in stamps if t < boot_started]
        if earlier:
            return datetime.fromtimestamp(max(earlier), tz=timezone.utc)
    return None


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
