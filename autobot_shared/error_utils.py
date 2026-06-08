# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Safe HTTP detail helpers — prevent str(exc) leaking in API responses (#5680)."""

from __future__ import annotations

import logging

_log = logging.getLogger(__name__)


def safe_http_detail(exc: BaseException, fallback: str = "Internal server error") -> str:
    """Return a client-safe error string that never leaks internal exception messages.

    Always returns *fallback*. Logs the full exception at DEBUG level so the
    information is available in server logs without being sent to clients.
    """
    _log.debug("safe_http_detail suppressed: %s: %s", type(exc).__name__, exc)
    return fallback


def user_facing_detail(exc: BaseException) -> str:
    """Return str(exc) for user-input validation errors only.

    Call this ONLY when the exception originates from explicit input validation
    (Pydantic, ValueError raised by business logic with a user-readable message).
    Never call for system/internal exceptions.
    """
    return str(exc)
