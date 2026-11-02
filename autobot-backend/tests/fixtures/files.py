# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Async-safe fixture file I/O for tests (#7444).

``Path.read_text``/``write_text`` are synchronous; calling them inside an
``async def`` stalls the event loop and is rejected by
``tools/lint/check_no_blocking_io_in_async.py``. Tests that build fixture
files inside a coroutine use these wrappers instead of repeating
``asyncio.to_thread(...)`` at every call site.
"""

from __future__ import annotations

import asyncio
from pathlib import Path


async def write_text_async(path: Path, text: str) -> None:
    """Write *text* to *path* as UTF-8, off the event loop."""
    await asyncio.to_thread(path.write_text, text, encoding="utf-8")


async def read_text_async(path: Path) -> str:
    """Return the UTF-8 contents of *path*, read off the event loop."""
    return await asyncio.to_thread(path.read_text, encoding="utf-8")
