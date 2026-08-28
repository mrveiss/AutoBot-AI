# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Analytics resource operations.

Paths are written without the ``/api`` root — ``AutoBotClient`` adds it.

``/analytics/usage`` and ``/analytics/performance`` are not routes: the
analytics router serves ``usage/statistics`` and ``performance/metrics``
under its ``/analytics`` mount (#15053).

Neither route wraps its body in a ``DataResponse`` envelope, so parsing one out
of it left ``data`` permanently ``None`` while ``success`` read ``True``
(#15116).
"""

from __future__ import annotations

from ..client import AutoBotClient
from ..models import AnalyticsPerformance, AnalyticsUsage


class AnalyticsResource:
    def __init__(self, client: AutoBotClient) -> None:
        self._c = client

    async def usage(self, period: str = "day") -> AnalyticsUsage:
        raw = await self._c.get("/analytics/usage/statistics", period=period)
        return AnalyticsUsage.model_validate(raw)

    async def performance(self, period: str = "day") -> AnalyticsPerformance:
        raw = await self._c.get("/analytics/performance/metrics", period=period)
        return AnalyticsPerformance.model_validate(raw)
