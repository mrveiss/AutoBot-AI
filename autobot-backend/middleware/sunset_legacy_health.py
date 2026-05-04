# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
"""

from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

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
            response.headers["Link"] = (
                '</api/system/health>; rel="successor-version"'
            )
        return response
