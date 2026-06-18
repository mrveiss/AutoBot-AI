# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Canonical async PromQL client for AutoBot backend services.

Provides two helpers:
- ``query_instant`` — instant PromQL (Prometheus /api/v1/query)
- ``query_range``   — range PromQL  (Prometheus /api/v1/query_range)

Both helpers degrade gracefully: any network / parse error returns an empty
result rather than raising so callers can return empty data to the frontend.

Prometheus host: ``ssot_config.vm.main`` (the backend VM, which is where the
``autobot-prometheus`` container runs per docker-compose.yml).  The earlier
``prometheus_mcp.py`` used ``vm.redis`` by mistake; that is a separate bug
(#10309 follow-up).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

import aiohttp

from autobot_shared.http_client import get_http_client
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import get_config

logger = get_logger(__name__)

_ssot = get_config()
_PROMETHEUS_BASE = f"http://{_ssot.vm.main}:{_ssot.port.prometheus}"

_INSTANT_TIMEOUT = aiohttp.ClientTimeout(total=10)
_RANGE_TIMEOUT = aiohttp.ClientTimeout(total=30)


async def query_instant(promql: str) -> Dict[str, Any] | None:
    """Execute an instant PromQL query.

    Args:
        promql: PromQL expression.

    Returns:
        Prometheus ``data`` dict (``{"resultType": ..., "result": [...]}``),
        or ``None`` on failure / empty response.
    """
    try:
        http_client = get_http_client()
        async with await http_client.get(
            f"{_PROMETHEUS_BASE}/api/v1/query",
            params={"query": promql},
            timeout=_INSTANT_TIMEOUT,
        ) as resp:
            if resp.status != 200:
                logger.warning("Prometheus instant query HTTP %s for %r", resp.status, promql)
                return None
            body = await resp.json()
            if body.get("status") != "success":
                logger.warning("Prometheus instant query non-success for %r: %s", promql, body.get("error"))
                return None
            return body.get("data")
    except aiohttp.ClientError as exc:
        logger.warning("Prometheus unreachable (instant): %s", exc)
        return None
    except Exception as exc:
        logger.error("Unexpected error in query_instant: %s", exc)
        return None


async def query_range(
    promql: str,
    hours: int,
    step: str = "5m",
) -> List[Dict[str, Any]]:
    """Execute a range PromQL query over the last *hours* hours.

    Args:
        promql: PromQL expression.
        hours: Look-back window in hours.
        step:  Resolution step (e.g. ``"5m"``, ``"1m"``).

    Returns:
        List of ``{"timestamp": ISO-str, "value": float, "labels": dict}``
        points, or ``[]`` on failure.
    """
    try:
        now = datetime.now(timezone.utc)
        start = now.timestamp() - hours * 3600
        http_client = get_http_client()
        params = {
            "query": promql,
            "start": start,
            "end": now.timestamp(),
            "step": step,
        }
        async with await http_client.get(
            f"{_PROMETHEUS_BASE}/api/v1/query_range",
            params=params,
            timeout=_RANGE_TIMEOUT,
        ) as resp:
            if resp.status != 200:
                logger.warning("Prometheus range query HTTP %s for %r", resp.status, promql)
                return []
            body = await resp.json()
            if body.get("status") != "success":
                logger.warning("Prometheus range query non-success for %r: %s", promql, body.get("error"))
                return []
            results = body.get("data", {}).get("result", [])
            points: List[Dict[str, Any]] = []
            for series in results:
                metric = series.get("metric", {})
                for ts, val in series.get("values", []):
                    points.append(
                        {
                            "timestamp": datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat(),
                            "value": float(val),
                            "labels": metric,
                        }
                    )
            return points
    except aiohttp.ClientError as exc:
        logger.warning("Prometheus unreachable (range): %s", exc)
        return []
    except Exception as exc:
        logger.error("Unexpected error in query_range: %s", exc)
        return []
