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

Neither declares a ``period`` query parameter either. Both methods advertised one
and sent it on every call; FastAPI ignored it, so the window a caller asked for
was never the window they got, and nothing said so. The argument is gone rather
than renamed: there is no parameter on either route to map it to, and an argument
that cannot be honoured is worse than an absent one (#15119).
"""

from __future__ import annotations

from ..client import AutoBotClient
from ..models import AnalyticsPerformance, AnalyticsUsage


class AnalyticsResource:
    def __init__(self, client: AutoBotClient) -> None:
        self._c = client

    async def usage(self) -> AnalyticsUsage:
        """Usage statistics over the collector's own window.

        The route takes no arguments, so neither does this (#15119).
        """
        raw = await self._c.get("/analytics/usage/statistics")
        return AnalyticsUsage.model_validate(raw)

    async def performance(self) -> AnalyticsPerformance:
        """Performance metrics over the collector's own window (#15119)."""
        raw = await self._c.get("/analytics/performance/metrics")
        return AnalyticsPerformance.model_validate(raw)
