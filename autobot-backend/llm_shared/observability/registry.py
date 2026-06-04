# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Singleton registry with fan-out to all registered LLMObserver instances (GH#6593).

All notify_* functions are fire-and-forget — observer exceptions are suppressed
so a failing observer never blocks the request path.
"""

from __future__ import annotations

import asyncio
from typing import List

from .base import LLMObserver

_registry: List[LLMObserver] = []


def register(observer: LLMObserver) -> None:
    _registry.append(observer)


def clear() -> None:
    """Remove all observers (test helper)."""
    _registry.clear()


async def notify_request(request, metadata: dict) -> None:
    await asyncio.gather(
        *[o.on_request(request, metadata) for o in _registry],
        return_exceptions=True,
    )


async def notify_response(response, latency_ms: float, cost: float) -> None:
    await asyncio.gather(
        *[o.on_response(response, latency_ms, cost) for o in _registry],
        return_exceptions=True,
    )


async def notify_error(exc: Exception, request) -> None:
    await asyncio.gather(
        *[o.on_error(exc, request) for o in _registry],
        return_exceptions=True,
    )
