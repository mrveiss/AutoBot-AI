# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A finished asyncio subprocess with real, EOF-terminated output streams (#20740).

The bounded runner reads ``process.stdout`` / ``process.stderr`` to EOF. A bare
``AsyncMock()`` process answers every ``read()`` with a truthy mock and never reaches EOF, so
the drain loop grows without bound until the CI runner is OOM-killed. Tests that patch
``asyncio.create_subprocess_shell`` return this instead.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock


def _eof_stream(data: bytes) -> asyncio.StreamReader:
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()
    return reader


def finished_process(stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0) -> MagicMock:
    """A process that already exited with *returncode*; ``pid`` is None so no group kill can aim at a real group."""
    process = MagicMock()
    process.stdout = _eof_stream(stdout)
    process.stderr = _eof_stream(stderr)
    process.returncode = returncode
    process.pid = None
    process.wait = AsyncMock(return_value=returncode)
    return process
