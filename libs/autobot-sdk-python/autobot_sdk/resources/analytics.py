# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Analytics resource operations."""

from __future__ import annotations

from ..client import AutoBotClient
from ..models import AnalyticsPerformance, AnalyticsUsage, DataResponse


class AnalyticsResource:
    def __init__(self, client: AutoBotClient) -> None:
        self._c = client

    async def usage(self, period: str = "day") -> DataResponse[AnalyticsUsage]:
        raw = await self._c.get("/analytics/usage", period=period)
        return DataResponse[AnalyticsUsage].model_validate(raw)

    async def performance(self, period: str = "day") -> DataResponse[AnalyticsPerformance]:
        raw = await self._c.get("/analytics/performance", period=period)
        return DataResponse[AnalyticsPerformance].model_validate(raw)
