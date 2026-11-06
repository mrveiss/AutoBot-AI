# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One 409 for a chat session another writer holds (#20862).

A write to a chat session raises ``SessionLeaseTimeout`` (the lease stayed held for the whole bounded
wait, holder named) or ``StaleGenerationError`` (a newer write landed first). Both are retryable
conflicts, not server faults, so every route answers them here with the same status and a detail that
names the holder, instead of each route mapping them itself or leaving a 500.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from autobot_shared.logging_manager import get_logger
from chat_history.session_lease import SessionLeaseError

logger = get_logger(__name__)


def register_session_lease_handlers(app: FastAPI) -> None:
    """Map every ``SessionLeaseError`` (timeout, lost lease or file lock, stale generation) onto a 409."""

    @app.exception_handler(SessionLeaseError)
    async def _session_conflict(request: Request, exc: SessionLeaseError) -> JSONResponse:
        logger.warning("chat session write conflict on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(status_code=409, content={"detail": str(exc)})
