# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Turn an unhandled constraint violation into the status it deserves (#15775).

Before this, every integrity error that no route handled fell through to the
catch-all in ``app_factory`` and became a 500. That is wrong in a way that
costs more than tidiness: a 500 means "the server broke, try again", so an
agent retries a duplicate insert forever, while a 409 means "you sent this
twice" and ends the loop.

Registered as a floor. Starlette dispatches to the most specific handler for
the exception's MRO, so a route that raises its own typed error -- as
``user_service_conflict`` does to name the colliding field -- is untouched by
anything here.
"""

from __future__ import annotations

import sqlite3

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError, IntegrityError

from autobot_shared.db_errors import classify_integrity_error, detail_for, status_for
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


def _answer(request: Request, exc: BaseException) -> JSONResponse:
    """Classify, log the driver detail server-side, answer generically."""
    kind = classify_integrity_error(exc)
    status = status_for(kind)
    # The driver message names tables, columns and constraints. It belongs in
    # the log, where an operator can read it, and never in the response.
    logger.error(
        "database constraint violation on %s %s: kind=%s status=%s",
        request.method,
        request.url.path,
        kind.value,
        status,
        exc_info=exc,
    )
    return JSONResponse(status_code=status, content={"detail": detail_for(kind)})


def register_integrity_handlers(app: FastAPI) -> None:
    """Map integrity and malformed-value errors onto 409/422 for every router."""

    @app.exception_handler(IntegrityError)
    async def _sqlalchemy_integrity(request: Request, exc: IntegrityError) -> JSONResponse:
        return _answer(request, exc)

    @app.exception_handler(sqlite3.IntegrityError)
    async def _sqlite_integrity(request: Request, exc: sqlite3.IntegrityError) -> JSONResponse:
        return _answer(request, exc)

    @app.exception_handler(DataError)
    async def _data_error(request: Request, exc: DataError) -> JSONResponse:
        # Classified exactly like an integrity error, with no DataError-specific
        # default. An earlier revision forced an unclassified DataError to 422 on
        # the reasoning that the class is "bad input" -- review of #15775 was
        # right to reject it. PEP 249 puts division-by-zero in this class too,
        # and that is a fault in a query WE wrote: answering 422 would tell the
        # caller their request was wrong when the bug is ours. A malformed UUID
        # still reaches 422 through SQLSTATE 22P02, which is classification
        # rather than a guess.
        return _answer(request, exc)
