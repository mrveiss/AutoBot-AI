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

WHAT THIS DELIBERATELY DOES NOT READ
------------------------------------
The body is inspected only when `Content-Length` says it is small. Downstream,
`ValidationMiddleware` buffers an unbounded body into memory *before* checking
`MAX_BODY_BYTES` (#15857), so an unbounded read here would add a second full
copy of a payload nothing has bounded yet. An oversized or unmeasurable body is
therefore reported as *unconfirmed* rather than parsed — a weaker claim, and
the only one that was actually established.
"""

from __future__ import annotations

import json

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: Methods that carry a JSON body. `GET /status` takes `session_id` as a query
#: parameter, which is read separately below.
_BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})

#: Only these paths are inspected; everything else passes untouched.
_PREFIX = "/api/playwright/"

#: Largest body this will read looking for `session_id`. A scoped Playwright
#: body is a URL and an id — well under a kilobyte — so anything past this is
#: not a body worth parsing, and reading it would add a second full copy of a
#: buffer that is already unbounded downstream (#15857).
_INSPECT_MAX_BYTES = env_int_clamped("PLAYWRIGHT_SCOPE_INSPECT_MAX_BYTES", 64 * 1024, min_v=0)


def _inspection_refusal(request: Request) -> str | None:
    """Why this body must not be read, or None when reading it is bounded.

    A missing or unparseable `Content-Length` counts as a refusal: the size is
    then unknown, and an unknown quantity is exactly what must not be pulled
    into memory.
    """
    declared = request.headers.get("content-length")
    if declared is None:
        return "no content-length header"
    try:
        size = int(declared)
    except ValueError:
        return f"unparseable content-length {declared!r}"
    if size > _INSPECT_MAX_BYTES:
        return f"{size} bytes over the {_INSPECT_MAX_BYTES} byte inspection bound"
    return None


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


def _message(path: str, caller: str, refusal: str | None) -> str:
    """The warning text, which states only what was actually established."""
    if refusal is None:
        return (
            f"playwright {path} called without session_id from caller={caller} — this caller "
            f"joins the SHARED default browser context and is NOT isolated (#15802)."
        )
    return (
        f"playwright {path} could not be confirmed as scoped from caller={caller} — body not "
        f"inspected ({refusal}) and no session_id query parameter, so this caller MAY be "
        f"joining the SHARED default browser context (#15802)."
    )


class PlaywrightSessionScopeMiddleware(BaseHTTPMiddleware):
    """Warn when a Playwright call omits `session_id`, and change nothing else."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith(_PREFIX):
            await warn_if_unscoped(request)
        return await call_next(request)


async def warn_if_unscoped(request: Request) -> None:
    """Log a Playwright call that did not establish a `session_id`."""
    refusal: str | None = None
    body = b""
    if request.method.upper() in _BODY_METHODS:
        refusal = _inspection_refusal(request)
        if refusal is None:
            body = await request.body()

    if _declared_session_id(body, request.query_params.get("session_id")):
        return

    client = getattr(request.client, "host", None) if request.client else None
    # Caller and path are embedded in the message, not passed as %s arguments:
    # the flood filter keys on the UNINTERPOLATED template plus call site
    # (#15774), so arguments would hand every caller one shared 5-per-minute
    # budget and let a chatty client silence a second unscoped one — the log
    # could no longer answer "who". user_agent stays an argument: it is
    # attacker-controlled and unbounded, so it must not enter the key space.
    logger.warning(
        _message(request.url.path, client or "unknown", refusal) + " user_agent=%s",
        request.headers.get("user-agent") or "unknown",
    )
