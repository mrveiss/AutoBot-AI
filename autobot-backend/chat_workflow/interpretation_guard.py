# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A failed post-command interpretation is an auxiliary-step failure, never a tool failure (#21938).

The interpretation is a second LLM call made while the ``execute_command`` tool is still running. An exception
leaving it was caught by the tool's own handler (``TOOL_ERROR`` hook, then re-raised) and ended the turn, although
the command had succeeded and its output was in hand.
"""

from __future__ import annotations

import asyncio
import functools
from typing import Any, AsyncIterator, Callable

from autobot_shared.env_utils import env_float_clamped
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: Own budget of one interpretation, so an auxiliary call cannot use up the turn's (#21938).
INTERPRETATION_TIMEOUT_SECONDS: float = env_float_clamped(
    "AUTOBOT_INTERPRETATION_TIMEOUT_SECONDS", default=60.0, positive_finite=True
)


def interpretation_never_fails_the_tool(stream: Callable[..., AsyncIterator[Any]]) -> Callable[..., AsyncIterator[Any]]:
    """Wrap an interpretation stream: a failure is logged and the stream ends, so the command's result stands.

    The stream runs under its own deadline (``AUTOBOT_INTERPRETATION_TIMEOUT_SECONDS``); only that deadline is
    absorbed. Cancellation (a client cancel or the turn deadline) is a ``BaseException`` and still propagates.
    """

    @functools.wraps(stream)
    async def guarded(*args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        try:
            async with asyncio.timeout(INTERPRETATION_TIMEOUT_SECONDS):
                async for chunk in stream(*args, **kwargs):
                    yield chunk
        except Exception as exc:  # noqa: BLE001 - auxiliary step; the command already succeeded
            logger.error("[interpretation] failed, the command result is kept without it: %s", exc)

    return guarded
