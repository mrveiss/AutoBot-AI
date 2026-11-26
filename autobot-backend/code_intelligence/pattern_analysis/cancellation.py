# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Cooperative cancel token for the pattern analyzer (#22094).

``asyncio.wait_for`` stops an AWAIT, not the executor threads behind it. The token is the one every
analytics route shares (``utils.cancel_tokens``: a plain ``threading.Event``); the analyzer checks it
before each file and each phase, and stops by raising :class:`AnalysisCancelled`. That is a
``CancelledError``, a ``BaseException``, so the per-file ``except Exception`` handlers cannot swallow it.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Callable

from utils.cancel_tokens import CancelTokenSet
from utils.io_executor import get_analytics_executor


class AnalysisCancelled(CancelTokenSet):
    """The caller stopped waiting for the analysis and signalled its cancel token."""


class CancellableAnalysis:
    """Gives an analyzer a ``cancel_token`` and the two helpers that honour it."""

    cancel_token: threading.Event | None = None

    def _check_cancelled(self) -> None:
        """Raise :class:`AnalysisCancelled` once the token is set."""
        if self.cancel_token is not None and self.cancel_token.is_set():
            raise AnalysisCancelled("pattern analysis cancelled by its caller")

    async def _run_file(self, func: Callable[..., Any], *args: Any) -> Any:
        """Run ``func(*args)`` on the analytics executor, unless the analysis was cancelled first."""
        self._check_cancelled()
        return await asyncio.get_running_loop().run_in_executor(get_analytics_executor(), func, *args)
