# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Telemetry Prompt Middleware Plugin — Issue #3405.

Registers ON_FULL_PROMPT_READY to inspect live CPU load from Prometheus.
When average CPU usage across all nodes exceeds the configured threshold,
a one-sentence hint is appended to the prompt asking the model to keep its
response concise to reduce wall-clock processing time on a loaded host.

Configuration (via plugin config or environment variables):
    cpu_threshold_pct  — float, default 80.  Percent CPU above which the
                         hint fires.  Set to 0 to always inject; 100 to
                         effectively disable.
    prometheus_url     — str, overrides the PROMETHEUS_URL env var when set.

Environment variables:
    PROMETHEUS_URL     — Base URL of the Prometheus instance, e.g.
                         "http://192.168.1.10:9090".
    TELEMETRY_CPU_THRESHOLD — Override threshold without touching plugin config.
"""

import logging
import os
from typing import Dict, Optional

import aiohttp

from extensions.base import Extension, HookContext

logger = logging.getLogger(__name__)

_CPU_PROMQL = "100 - (avg(rate(node_cpu_seconds_total{mode='idle'}[2m])) * 100)"
_HIGH_LOAD_HINT = (
    "[System note: host CPU is currently under high load. "
    "Please keep your response concise to minimise processing time.]"
)
_QUERY_TIMEOUT = aiohttp.ClientTimeout(total=2.0)


class TelemetryPromptMiddleware(Extension):
    """Prompt middleware that injects a load-aware hint via ON_FULL_PROMPT_READY."""

    name = "telemetry_prompt_middleware"
    priority = 200

    def __init__(self, config: Optional[Dict] = None) -> None:
        self._config = config or {}
        self._threshold = float(
            os.getenv(
                "TELEMETRY_CPU_THRESHOLD",
                self._config.get("cpu_threshold_pct", 80),
            )
        )
        self._prometheus_url = (self._config.get("prometheus_url") or os.getenv("PROMETHEUS_URL", "")).rstrip("/")

    async def on_full_prompt_ready(self, ctx: HookContext) -> Optional[str]:
        """Append a concise-response hint when CPU load exceeds threshold."""
        prompt = ctx.get("prompt", "")
        if not prompt:
            return None

        cpu_pct = await self._fetch_cpu_percent()
        if cpu_pct is None:
            logger.debug("[#3405] Telemetry plugin: Prometheus unavailable, skipping")
            return None

        logger.debug(
            "[#3405] Telemetry plugin: current CPU %.1f%% (threshold %.1f%%)",
            cpu_pct,
            self._threshold,
        )
        if cpu_pct < self._threshold:
            return None

        logger.info(
            "[#3405] Telemetry plugin: CPU %.1f%% > threshold %.1f%% — injecting hint",
            cpu_pct,
            self._threshold,
        )
        return f"{prompt}\n\n{_HIGH_LOAD_HINT}"

    async def _fetch_cpu_percent(self) -> Optional[float]:
        """Query Prometheus for the current cluster-wide CPU usage percentage."""
        if not self._prometheus_url:
            return None
        url = f"{self._prometheus_url}/api/v1/query"
        try:
            async with aiohttp.ClientSession(timeout=_QUERY_TIMEOUT) as session:
                async with session.get(url, params={"query": _CPU_PROMQL}) as resp:
                    if resp.status != 200:
                        return None
                    payload = await resp.json()
            results = payload.get("data", {}).get("result", [])
            if not results:
                return None
            return float(results[0]["value"][1])
        except Exception as exc:
            logger.debug("[#3405] Telemetry plugin: Prometheus query failed: %s", exc)
            return None
