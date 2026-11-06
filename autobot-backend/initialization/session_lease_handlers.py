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
from autobot_shared.security.redaction import sanitize_log_value
from chat_history.session_lease import ChatFileUnreadable, SessionLeaseError

logger = get_logger(__name__)


CHAT_SESSION_UNREADABLE = {
    "code": "chat_session_unreadable",
    "message": "The stored chat session could not be read, so it was not changed.",
}


def _loggable(request: Request, exc: Exception) -> tuple[str, str, str]:
    """Method, path and error text with control characters escaped: a request path or a session id in the
    error can carry terminal escapes or line breaks that would rewrite the log."""
    return sanitize_log_value(request.method), sanitize_log_value(request.url.path), sanitize_log_value(str(exc))


def register_session_lease_handlers(app: FastAPI) -> None:
    """Lease contention (timeout, lost lease or file lock, stale generation) is a 409; an unreadable file a 500.

    ``ChatFileUnreadable`` is a ``SessionLeaseError`` but permanent, so retrying cannot help: it gets its
    own handler (Starlette picks the most specific class) with a typed code and no decode cause in the body.
    """

    @app.exception_handler(ChatFileUnreadable)
    async def _chat_unreadable(request: Request, exc: ChatFileUnreadable) -> JSONResponse:
        logger.error("chat session file unreadable on %s %s: %s", *_loggable(request, exc))
        return JSONResponse(status_code=500, content={"detail": CHAT_SESSION_UNREADABLE})

    @app.exception_handler(SessionLeaseError)
    async def _session_conflict(request: Request, exc: SessionLeaseError) -> JSONResponse:
        logger.warning("chat session write conflict on %s %s: %s", *_loggable(request, exc))
        return JSONResponse(status_code=409, content={"detail": str(exc)})
