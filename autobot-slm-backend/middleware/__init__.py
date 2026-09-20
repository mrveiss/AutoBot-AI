# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
SLM Backend Middleware Package

Contains reusable ASGI/Starlette middleware for the SLM backend.
"""

# Issue #10778: HTTP API request counter middleware
from typing import Any, Sequence

from fastapi.middleware.cors import CORSMiddleware

from middleware.api_key_allow_list import ApiKeyAllowListMiddleware
from middleware.api_request_counter import ApiRequestCounterMiddleware
from middleware.security_headers import SecurityHeadersMiddleware

__all__ = [
    "SecurityHeadersMiddleware",
    "ApiRequestCounterMiddleware",
    "ApiKeyAllowListMiddleware",
    "install_middleware",
]


def install_middleware(app: Any, *, cors_origins: Sequence[str]) -> None:
    """Add the SLM's middleware stack, in the one order it needs (moved from ``main.py``, #16294).

    Starlette runs the middleware added **last** first, so this reads from innermost
    to outermost.
    """
    # #16294 — innermost: a user API key is refused with 403 on every route that does
    # not declare a key permission (services/api_key_routes.py; the allow-list ships
    # empty). Inside CORS and the security headers, so the refusal carries both.
    app.add_middleware(ApiKeyAllowListMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Issue #2858 — explicit CSRF mitigation + security headers.
    # Registered after CORSMiddleware so CORS headers are already present.
    app.add_middleware(SecurityHeadersMiddleware)
    # Issue #10778 — HTTP API request counter for BI dashboard monthly operations.
    # Registered last so the route is already matched when the counter reads it.
    app.add_middleware(ApiRequestCounterMiddleware)
