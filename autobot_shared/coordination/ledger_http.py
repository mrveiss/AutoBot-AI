# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one HTTP mapping of 'the ledger could not be read' (#18391).

Both ledger routers (user backend, SLM backend) answer an unreachable store the
same way -- HTTP 503 with a :class:`LedgerUnavailable` body -- so a screen can
say "couldn't read the ledger" rather than "no claims". Done once here so the
two surfaces cannot drift into different failure shapes.
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from autobot_shared.coordination.ledger_read import LedgerUnreadable
from autobot_shared.coordination.ledger_schemas import LedgerUnavailable
from autobot_shared.coordination.work_claims import VALID_KINDS
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: Merge into a route's ``responses=`` so the 503 body is in the OpenAPI schema.
UNAVAILABLE_RESPONSES: dict[int | str, dict[str, Any]] = {
    503: {"model": LedgerUnavailable, "description": "The ledger could not be read (not the same as empty)"}
}


def unavailable(exc: LedgerUnreadable) -> JSONResponse:
    logger.warning("agent ledger: %s could not be read: %s", exc.source, exc.detail)
    body = LedgerUnavailable(source=exc.source, detail=exc.detail)
    return JSONResponse(status_code=503, content=body.model_dump())


def valid_kind(kind: str | None) -> str | None:
    """Pass *kind* through when it is a real claim scope kind; otherwise answer 422 (not a 500)."""
    if kind is not None and kind not in VALID_KINDS:
        raise HTTPException(status_code=422, detail=f"unknown scope kind; expected one of {sorted(VALID_KINDS)}")
    return kind


def serve_ledger(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """Wrap a route so an unreadable store becomes the typed 503 instead of a 500 or an empty list."""

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await fn(*args, **kwargs)
        except LedgerUnreadable as exc:
            return unavailable(exc)

    return wrapper
