# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Safe error response utility (#1721).

Prevents stack-trace exposure by returning generic messages to API
clients while logging the full exception server-side.

Usage:
    from autobot_shared.security.safe_response import safe_error_response

    try:
        ...
    except Exception as exc:
        return safe_error_response(exc, logger, context="loading config")
"""

from __future__ import annotations

import logging
from typing import Any


def safe_error_response(
    exc: BaseException,
    logger: logging.Logger,
    *,
    context: str = "",
    status_code: int = 500,
    include_type: bool = True,
) -> dict[str, Any]:
    """Log the full exception and return a sanitised error dict.

    Parameters
    ----------
    exc:
        The caught exception.
    logger:
        Logger instance for server-side recording.
    context:
        Optional human-readable context (e.g. "loading config").
    status_code:
        HTTP status code to include in the response dict.
    include_type:
        When *True*, include the exception class name (but not the
        message) in the client-facing response.

    Returns
    -------
    dict
        ``{"detail": "<safe message>", "status_code": <int>}``
    """
    # Full trace goes to server logs only
    log_msg = f"Error{f' ({context})' if context else ''}: %s"
    logger.exception(log_msg, exc)

    # Client-facing message — no stack trace, no internal details
    if include_type:
        safe_msg = (
            f"Internal server error ({type(exc).__name__})"
            if not context
            else f"Error {context} ({type(exc).__name__})"
        )
    else:
        safe_msg = "Internal server error" if not context else f"Error {context}"

    return {"detail": safe_msg, "status_code": status_code}
