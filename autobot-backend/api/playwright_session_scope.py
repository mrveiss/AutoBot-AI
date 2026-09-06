# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Make an unscoped Playwright caller discoverable (#15802).

`session_id` is optional on every Playwright request model, so a client written
before #11539 keeps working, lands in the **shared default browser context**,
and neither end can tell: the client believes it is isolated, the server sees a
well-formed request. One such caller — an MCP server built against these routes
in March 2026 — shared the default context for roughly six months and was found
during unrelated host maintenance rather than by any check.

This does not reject the request. Making the field required would break every
existing caller, which is a decision for whoever owns those integrations rather
than a fix; what is missing today is not enforcement but *visibility*. After
this, "who is still unscoped" is a log query instead of an accident.

WHY MIDDLEWARE RATHER THAN A CALL PER ROUTE
-------------------------------------------
A per-route call is a list that goes stale: the next Playwright route added is
unscoped-by-default and silent again, and nothing notices. Path-scoped
middleware covers every route the prefix has and every route it gains.

It also keeps `api/playwright.py` and `api/schemas_code.py` at their recorded
size ceilings (#14236). Four earlier shapes of this fix — a helper plus eight
call sites, an extracted helper, instrumenting the fallback, and a router
dependency — each breached one of those ceilings, the last by a single import
line. The ratchet refusing all four was the useful signal: the instrumentation
did not belong inside the module it was instrumenting.
"""

from __future__ import annotations

import json

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: Methods that carry a JSON body. `GET /status` takes `session_id` as a query
#: parameter, which is read separately below.
_BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})

#: Only these paths are inspected; everything else passes untouched.
_PREFIX = "/api/playwright/"


def _declared_session_id(body: bytes, query_param: str | None) -> str | None:
    """The `session_id` this request supplied, from body or query string.

    A body that is absent, empty, or not an object is treated as *no id*
    rather than as unparseable-so-skip: a caller that sent nothing is exactly
    the caller this exists to find, and skipping it would reproduce the silence.
    """
    if query_param:
        return query_param
    if not body:
        return None
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None
    return payload.get("session_id") if isinstance(payload, dict) else None


class PlaywrightSessionScopeMiddleware(BaseHTTPMiddleware):
    """Warn when a Playwright call omits `session_id`, and change nothing else."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith(_PREFIX):
            await warn_if_unscoped(request)
        return await call_next(request)


async def warn_if_unscoped(request: Request) -> None:
    """Log a Playwright call that omitted `session_id`, naming the caller."""
    body = await request.body() if request.method.upper() in _BODY_METHODS else b""
    if _declared_session_id(body, request.query_params.get("session_id")):
        return

    client = getattr(request.client, "host", None) if request.client else None
    logger.warning(
        "playwright %s called without session_id — this caller joins the SHARED default browser "
        "context and is NOT isolated (#15802). caller=%s user_agent=%s",
        request.url.path,
        client or "unknown",
        request.headers.get("user-agent") or "unknown",
    )
