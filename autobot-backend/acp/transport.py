# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
ACP stdio transport (#14825).

ACP runs a local agent as a sub-process of the editor and speaks JSON-RPC 2.0
over stdin/stdout — one complete JSON message per line.  That framing choice is
what makes an agent installable without any network setup, and it is the reason
stdout must carry protocol traffic *only*: a stray ``print`` corrupts the
stream.  AutoBot's logging goes to stderr and the logging manager, so this holds
as long as nothing in the agent path writes to stdout directly.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any, AsyncIterator, Dict

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


class StdioTransport:
    """Line-delimited JSON-RPC over stdin/stdout."""

    def __init__(self) -> None:
        self._writer_lock = asyncio.Lock()

    async def messages(self) -> AsyncIterator[Dict[str, Any]]:
        """Yield each well-formed JSON message arriving on stdin.

        A malformed line is logged and skipped rather than killing the session:
        the peer may still send valid traffic, and ACP has no framing-level
        recovery of its own.  Skipping is safe here precisely because each line
        is an independent message.
        """
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        while True:
            line = await reader.readline()
            if not line:
                logger.debug("ACP stdin closed")
                return
            stripped = line.strip()
            if not stripped:
                continue
            try:
                yield json.loads(stripped)
            except json.JSONDecodeError:
                logger.warning("Discarding malformed ACP message (%d bytes)", len(stripped))

    async def send(self, message: Dict[str, Any]) -> None:
        """Write one JSON-RPC message as a single line on stdout.

        Serialised behind a lock: notifications are emitted from streaming
        tasks, and two interleaved writes would corrupt the framing.
        """
        payload = json.dumps(message, ensure_ascii=False, default=str)
        async with self._writer_lock:
            sys.stdout.write(payload + "\n")
            sys.stdout.flush()
