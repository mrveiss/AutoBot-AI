# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
API Request Counter Middleware — Issue #10778

Lightweight ASGI middleware that increments ``autobot_api_requests_total``
after each HTTP request completes.

Design decisions:
- Uses the FastAPI **matched route template** (``request.scope["route"].path``)
  rather than the raw URL path so that parameterised routes such as
  ``/api/nodes/{node_id}`` do not produce one series per node ID.
- Falls back to ``"unmatched"`` when the route is not yet resolved (e.g. 404s),
  keeping cardinality bounded.
- Counter increment is the *last* action after ``call_next`` returns, so any
  exception inside the handler still propagates normally; the middleware never
  swallows errors.
- ``get_metrics_manager`` is imported at module level so it is patchable in
  tests; ``monitoring.prometheus_metrics`` is always importable in the SLM
  backend environment.
"""

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class ApiRequestCounterMiddleware(BaseHTTPMiddleware):
    """Middleware that counts every HTTP request by method, route, and status class."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        """Pass request through, then record it against the counter."""
        response = await call_next(request)
        try:
            _record_request(request, response.status_code)
        except Exception:  # never break a request due to metric failure
            logger.debug("api_request_counter: failed to record metric", exc_info=True)
        return response


def _record_request(request: Request, status_code: int) -> None:
    """Increment the counter; resolve the route template if available."""
    # Lazy import: importing monitoring.prometheus_metrics at module load pulls the
    # whole `monitoring` package (→ constants.path_constants), which isn't on the
    # container sys.path when middleware is registered at startup. Defer to runtime.
    from monitoring.prometheus_metrics import get_metrics_manager

    manager = get_metrics_manager()
    recorder = manager._api_requests  # type: ignore[attr-defined]
    route = request.scope.get("route")
    endpoint = route.path if route is not None else "unmatched"
    recorder.record_request(
        method=request.method,
        endpoint=endpoint,
        status_code=status_code,
    )


__all__ = ["ApiRequestCounterMiddleware"]
