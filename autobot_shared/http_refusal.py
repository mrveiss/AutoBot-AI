# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ONE refusal rule for HTTP routes (#21579, #21559): what a caller is told when an exception may not speak.

Company OS and the secret routes answer a refusal from this one table, so no route words a 403 or a 400 its own
way or lets exception text through. An exception is public by construction only when it carries a
``public_detail`` string.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from autobot_shared.logging_manager import get_logger
from autobot_shared.security.redaction import safe_log_text, sanitize_log_value

logger = get_logger(__name__)

#: What a caller is told when an exception does not say what it may show, by status code (#21579). One table, so
#: no handler word a refusal differently or let exception text through.
REFUSAL_TEXT: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "Invalid request",
    status.HTTP_403_FORBIDDEN: "Forbidden",
    status.HTTP_404_NOT_FOUND: "Not found",
    status.HTTP_409_CONFLICT: "Conflict",
    status.HTTP_422_UNPROCESSABLE_ENTITY: "Unprocessable request",
    status.HTTP_503_SERVICE_UNAVAILABLE: "Service unavailable",
}
_REFUSAL_DEFAULT = "Request refused"


def http_refusal(status_code: int, exc: BaseException, *, scope: str) -> HTTPException:
    """The refusal for *exc*: its ``public_detail`` when it has one, else a fixed text by status (#21579).

    An exception is public by construction only when it carries a ``public_detail`` string. Its own
    message (``str(exc)``) is never the response: it can hold a driver message, a path, a company's
    data. The cause is logged once, redacted, with *scope* and the exception class.
    """
    public = getattr(exc, "public_detail", None)
    if isinstance(public, str):
        if public != str(exc):  # a redacted class: the dropped detail (ids, remedy) still reaches the log
            logger.info(
                "Refused %s with %s: %s: %s",
                status_code,
                sanitize_log_value(scope),
                type(exc).__name__,
                safe_log_text(exc),
            )
        return HTTPException(status_code=status_code, detail=public)
    logger.warning(
        "Refused %s with %s: %s: %s",
        status_code,
        sanitize_log_value(scope),
        type(exc).__name__,
        safe_log_text(exc),
    )
    return HTTPException(status_code=status_code, detail=REFUSAL_TEXT.get(status_code, _REFUSAL_DEFAULT))


def fixed_refusal(status_code: int) -> HTTPException:
    """The refusal for *status_code* with its fixed text and nothing from any exception (#21559)."""
    return HTTPException(status_code=status_code, detail=REFUSAL_TEXT.get(status_code, _REFUSAL_DEFAULT))
