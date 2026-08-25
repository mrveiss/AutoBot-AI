# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Analytics resource operations.

Paths are written without the ``/api`` root — ``AutoBotClient`` adds it.

``/analytics/usage`` and ``/analytics/performance`` are not routes: the
analytics router serves ``usage/statistics`` and ``performance/metrics``
under its ``/analytics`` mount (#15053).
"""

from __future__ import annotations

from ..client import AutoBotClient
from ..models import AnalyticsPerformance, AnalyticsUsage, DataResponse


class AnalyticsResource:
    def __init__(self, client: AutoBotClient) -> None:
        self._c = client

    async def usage(self, period: str = "day") -> DataResponse[AnalyticsUsage]:
        raw = await self._c.get("/analytics/usage/statistics", period=period)
        return DataResponse[AnalyticsUsage].model_validate(raw)

    async def performance(self, period: str = "day") -> DataResponse[AnalyticsPerformance]:
        raw = await self._c.get("/analytics/performance/metrics", period=period)
        return DataResponse[AnalyticsPerformance].model_validate(raw)
