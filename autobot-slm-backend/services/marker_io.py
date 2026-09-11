# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tiny async read/write for a one-line marker file under a deployed dir.

Shared by ``services/sync_deletions.py`` for its dedicated deletion marker
and its read-only bootstrap of the legacy ``.deployed_commit`` (#16310) --
one place doing the blocking I/O off the event loop, rather than each caller
wrapping ``Path.read_text``/``write_text`` in its own ``asyncio.to_thread``.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

# Plain stdlib logging, deliberately -- see services/git_subprocess.py's
# comment: get_logger() crashes at creation time under a MagicMock `config`,
# the precedent autobot_shared/user_management/password_epoch.py:50-58 sets.
logger = logging.getLogger(__name__)


def _read(deployed_dir: str, name: str) -> str | None:
    try:
        text = (Path(deployed_dir) / name).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def _write(deployed_dir: str, name: str, value: str) -> None:
    marker = Path(deployed_dir) / name
    try:
        marker.write_text(f"{value}\n", encoding="utf-8")
    except OSError as exc:
        logger.warning("marker_io: could not write %s: %s", marker, exc)


async def read_marker(deployed_dir: str, name: str) -> str | None:
    """Return the stripped contents of ``<deployed_dir>/<name>``, or None."""
    return await asyncio.to_thread(_read, deployed_dir, name)


async def write_marker(deployed_dir: str, name: str, value: str) -> None:
    """Write *value* (newline-terminated) to ``<deployed_dir>/<name>``."""
    await asyncio.to_thread(_write, deployed_dir, name, value)
