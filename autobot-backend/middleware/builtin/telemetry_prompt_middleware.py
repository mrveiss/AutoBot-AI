# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Telemetry Prompt Middleware Extension — Issue #3405, relocated by #14280.

Registers ON_FULL_PROMPT_READY to inspect live CPU load from Prometheus.
When average CPU usage across all nodes exceeds the configured threshold,
a one-sentence hint is appended to the prompt asking the model to keep its
response concise to reduce wall-clock processing time on a loaded host.

Issue #14280: this component was shipped as `plugins/core-plugins/telemetry-
prompt-middleware/plugin.py`, complete with a `plugin.json` manifest — but the
class subclassed `middleware.base.Extension`, not
`autobot_shared.plugin_sdk.base.BasePlugin`, and `ON_FULL_PROMPT_READY` is an
Extension-only hook point: it is dispatched exclusively by
`middleware.manager.ExtensionManager` (via `chat_workflow.llm_handler.
_emit_full_prompt_ready`), never by the plugin system's `HookRegistry`. The
`PluginLoader` therefore discovered the manifest, failed to find a
`BasePlugin` subclass in the module, and logged "No plugin class found" on
every startup — this middleware never ran in production. Moving the class to
`middleware/builtin/`, alongside the other built-in extensions, and
registering it through `initialization.lifespan._init_builtin_extensions`
(the mechanism the Extension system actually uses — there is no manifest-
driven discovery for extensions) is the fix. `plugins/core-plugins/telemetry-
prompt-middleware/plugin.json` remains, marked `"kind": "extension"`, purely
as a capability/config-schema description; `PluginLoader.discover_plugins`
now skips any manifest whose `kind` is not `"plugin"`.

Configuration (via plugin config or environment variables):
    cpu_threshold_pct  — float, default 80.  Percent CPU above which the
                         hint fires.  Set to 0 to always inject; 100 to
                         effectively disable.
    prometheus_url     — str, overrides the PROMETHEUS_URL env var when set.

Environment variables:
    PROMETHEUS_URL     — Base URL of the Prometheus instance, e.g.
                         "http://192.168.1.10:9090".
    TELEMETRY_CPU_THRESHOLD — Override threshold without touching plugin config.

Issue #14280 (review): the Prometheus query used to open a raw
``aiohttp.ClientSession(...)`` per call. That was invisible to
``tests/test_raw_client_session_ceiling_12992.py`` while this file lived
under ``plugins/core-plugins/`` (outside the walked tree) — moving it into
``autobot-backend/`` revealed the offense, it did not create it. Converted to
the shared pooled client (``autobot_shared.http_client.get_http_client()``,
issue #12979) so it participates in the pool's sizing/utilisation accounting
instead of opening its own connector. ``prometheus_url`` is operator-supplied
stored config (env var or plugin config, #14280/Rule 8), so the request opts
into ``guard_egress=True`` — loopback/link-local/cloud-metadata/reserved
addresses are refused even when an operator has enabled
``AUTOBOT_CONNECTOR_PRIVATE_NETWORK_EGRESS`` for the RFC-1918 Prometheus
instance most self-hosted deployments actually use.
"""

import os
from typing import Dict, Optional

import aiohttp

from autobot_shared.http_client import get_http_client
from autobot_shared.logging_manager import get_logger
from middleware.base import Extension, HookContext

logger = get_logger(__name__)

_CPU_PROMQL = "100 - (avg(rate(node_cpu_seconds_total{mode='idle'}[2m])) * 100)"
_HIGH_LOAD_HINT = (
    "[System note: host CPU is currently under high load. "
    "Please keep your response concise to minimise processing time.]"
)
_QUERY_TIMEOUT = aiohttp.ClientTimeout(total=2.0)


class TelemetryPromptMiddleware(Extension):
    """Prompt middleware that injects a load-aware hint via ON_FULL_PROMPT_READY."""

    name = "telemetry_prompt_middleware"
    version = "1.0.0"
    description = "Appends a concise-response hint to the LLM prompt when CPU load is above a configurable threshold"
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
            logger.debug("[#3405] Telemetry extension: Prometheus unavailable, skipping")
            return None

        logger.debug(
            "[#3405] Telemetry extension: current CPU %.1f%% (threshold %.1f%%)",
            cpu_pct,
            self._threshold,
        )
        if cpu_pct < self._threshold:
            return None

        logger.info(
            "[#3405] Telemetry extension: CPU %.1f%% > threshold %.1f%% — injecting hint",
            cpu_pct,
            self._threshold,
        )
        return f"{prompt}\n\n{_HIGH_LOAD_HINT}"

    async def _fetch_cpu_percent(self) -> Optional[float]:
        """Query Prometheus for the current cluster-wide CPU usage percentage.

        Uses the shared pooled client (#12979/#14280) rather than a raw
        ``aiohttp.ClientSession`` — the connector is shared, sized, and
        accounted for by the pool instead of opened fresh per call.
        ``prometheus_url`` is stored config, so the request is egress-guarded
        (Rule 8, #13625): loopback/link-local/cloud-metadata/reserved
        addresses are refused even when private-network egress is enabled.
        """
        if not self._prometheus_url:
            return None
        url = f"{self._prometheus_url}/api/v1/query"
        try:
            async with get_http_client().tracked_request(
                "GET",
                url,
                params={"query": _CPU_PROMQL},
                timeout=_QUERY_TIMEOUT,
                guard_egress=True,
            ) as resp:
                if resp.status != 200:
                    return None
                payload = await resp.json()
            results = payload.get("data", {}).get("result", [])
            if not results:
                return None
            return float(results[0]["value"][1])
        except Exception as exc:
            logger.debug("[#3405] Telemetry extension: Prometheus query failed: %s", exc)
            return None
