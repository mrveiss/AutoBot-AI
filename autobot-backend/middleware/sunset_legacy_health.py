# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Issue #6902: telegraph deprecation of legacy /api/<module>/health routes.

After PR #6870 (#3333) consolidated 45 scattered ``/health`` endpoints behind
a single canonical aggregator at ``/api/system/health``, the 38 per-module
routes are kept for one release as a deprecation grace period. This
middleware adds RFC-7234 / IETF ``Sunset`` and ``Deprecation`` response
headers to those legacy paths so any external scraper (Prometheus exporter,
k8s liveness probe, oncall dashboard) sees the deprecation signal at runtime
without a behavioral change.

The canonical aggregator and the legacy ``/api/health`` alias are
**explicitly exempted** so the headers do not appear on the path that
external monitors should be migrating *to*.

After the sunset date elapses, the route-deletion PR can run with the
audit playbook in ``docs/api/health.md`` knowing every consumer was given
prior notice.

Issue #6919: Logging and Prometheus metering added so external audits can
identify which scrapers are still calling deprecated endpoints.  Each hit
is logged at INFO level and increments
``autobot_legacy_health_hits_total{path, user_agent}`` so operators can
query ``sum by (path, user_agent) (autobot_legacy_health_hits_total)``
to identify the caller and the targeted endpoint.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from autobot_shared.logging_manager import get_logger
from autobot_shared.proxy_utils import get_client_ip

logger = get_logger(__name__)

# RFC 8594 ``Sunset`` header value — HTTP-date format (RFC 7231 §7.1.1.1).
# Picked ~4 months out from the consolidation merge (#6870 on 2026-05-04)
# to give external scrapers an explicit migration window.
SUNSET_DATE_HTTP = "Wed, 02 Sep 2026 00:00:00 GMT"

# Path of the canonical aggregator + its alias — these MUST NOT receive
# the deprecation headers since they are the migration *target*.
_CANONICAL_PATHS = frozenset(
    {
        "/api/system/health",
        "/api/health",  # legacy alias on api/system.py
    }
)


class _NoopCounter:
    """Fallback counter used when prometheus_client is unavailable."""

    def labels(self, **_kwargs: object) -> "_NoopCounter":
        return self

    def inc(self, _amount: int = 1) -> None:
        return None


try:  # pragma: no cover - exercised in environments with the dep
    from prometheus_client import Counter as _PromCounter

    autobot_legacy_health_hits_total: _NoopCounter | _PromCounter = _PromCounter(
        "autobot_legacy_health_hits_total",
        (
            "Count of requests to deprecated /api/<module>/health endpoints "
            "during grace period (#6919). Query over 14 days before deletion."
        ),
        ("path", "user_agent"),
    )
except Exception:  # pragma: no cover - defensive fallback
    autobot_legacy_health_hits_total = _NoopCounter()


def _is_legacy_module_health(path: str) -> bool:
    """Match ``/api/<module>/health`` but not the canonical aggregator paths."""
    if path in _CANONICAL_PATHS:
        return False
    if not path.startswith("/api/"):
        return False
    if not path.endswith("/health"):
        return False
    # Path shape: /api/<module>/health (segment count == 4 after split)
    parts = path.split("/")
    return len(parts) == 4 and bool(parts[2])


class SunsetLegacyHealthMiddleware(BaseHTTPMiddleware):
    """Add ``Sunset`` / ``Deprecation`` / ``Link`` headers to legacy /health responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        path = request.url.path
        if _is_legacy_module_health(path):
            response.headers["Sunset"] = SUNSET_DATE_HTTP
            response.headers["Deprecation"] = "true"
            response.headers["Link"] = '</api/system/health>; rel="successor-version"'
            client_ip = get_client_ip(request) or "unknown"
            ua = request.headers.get("user-agent", "unknown")[:120]
            logger.info("Legacy health hit: %s from %s (%s)", path, client_ip, ua)
            autobot_legacy_health_hits_total.labels(path=path, user_agent=ua).inc()
        return response
