# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Stop an asyncio subprocess whose wait timed out (#18056).

``asyncio.wait_for(process.communicate(), timeout=...)`` cancels the wait, not the
child: the process keeps running, and a caller that returns the timeout result
leaves it behind. Callers that start one child per request would stack them.
"""

from __future__ import annotations

import asyncio
import contextlib


async def kill_and_reap(process: asyncio.subprocess.Process) -> None:
    """Kill *process* if it is still running and wait for it to exit, so no zombie is left."""
    if process.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
    await process.wait()
