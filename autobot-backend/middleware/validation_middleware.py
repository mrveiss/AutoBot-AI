# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Centralised Input Validation Middleware (Issue #3274).

Validates and sanitizes all inbound API requests before they reach route
handlers.  Two complementary checks are applied:

1. **Injection pattern detection** — query-string values and JSON body string
   fields are scanned for SQL injection, command injection, and path-traversal
   patterns.  Any match causes an immediate 400 response.

2. **Size guard** — request bodies larger than ``MAX_BODY_BYTES`` (default 1 MB)
   are rejected with a 413 response, preventing memory exhaustion from crafted
   payloads.

The middleware is intentionally lightweight:

* It only buffers the body once; the buffered bytes are re-injected so that
  downstream handlers see an unmodified ``Request``.
* JSON decode errors are silently ignored — Pydantic / FastAPI provides
  schema-level validation for malformed bodies.
* Validation failures always return ``{"error": ..., "details": ...}`` to
  match the project-wide error format expected by the frontend.

Usage (wired automatically via ``configure_validation`` in
``initialization/middleware.py``):

    from middleware.validation_middleware import ValidationMiddleware
    app.add_middleware(ValidationMiddleware)
"""

from __future__ import annotations

import json
import re
from typing import Final, Sequence

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Maximum body size in bytes that the middleware will buffer (1 MiB).
MAX_BODY_BYTES: Final[int] = 1 * 1024 * 1024

# HTTP methods whose bodies we inspect.
_BODY_METHODS: Final[frozenset[str]] = frozenset({"POST", "PUT", "PATCH"})

# Paths that bypass validation entirely (health probes, OpenAPI docs, static).
_EXEMPT_PREFIXES: Final[tuple[str, ...]] = (
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/static/",
)

# Storage-only paths whose bodies contain already-processed content (AI responses,
# web search results) that legitimately includes shell command patterns.  These paths
# store data — they never execute it — so injection scanning produces false positives
# and blocks saves.  The user-input entry point (/chats/{id}/message) is NOT matched.
_BODY_SCAN_EXEMPT_RE: Final[re.Pattern[str]] = re.compile(r"^/api/chats/[^/]+/save$")

# ---------------------------------------------------------------------------
# Injection-pattern catalog
# ---------------------------------------------------------------------------

# Each tuple is (human-readable label, compiled pattern).
# Patterns are deliberately conservative: they require common attack-specific
# tokens rather than bare keywords so that benign content is not rejected.
_INJECTION_PATTERNS: Final[Sequence[tuple[str, re.Pattern[str]]]] = (
    # SQL injection — keyword + quote boundary
    (
        "sql_injection",
        re.compile(
            r"(?i)(\b(union\s+select|select\s+\*|drop\s+table|insert\s+into"
            r"|delete\s+from|update\s+\w+\s+set|exec\s*\(|execute\s*\(|xp_cmdshell)\b"
            r"|('|\")\s*(or|and)\s+('|\")?\s*\d+\s*=\s*\d+"
            r"|--\s*$|;\s*--)",
            re.MULTILINE,
        ),
    ),
    # Command injection — shell metacharacters in suspicious combos
    (
        "command_injection",
        re.compile(
            r"(?:;|\||&&|\$\(|`)" r"\s*(?:rm|cat|ls|wget|curl|bash|sh|python|perl|nc|ncat|netcat|chmod|chown)" r"\b",
        ),
    ),
    # Path traversal — encoded or literal directory-traversal sequences
    (
        "path_traversal",
        re.compile(
            r"(?:\.\./|\.\.\\|%2e%2e%2f|%2e%2e/|\.\.%2f|%252e%252e%252f" r"|(?:\.\./){2,})",
            re.IGNORECASE,
        ),
    ),
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_fully_exempt(path: str) -> bool:
    """Return True when *path* should bypass ALL validation (health probes, docs, static)."""
    return any(path.startswith(prefix) for prefix in _EXEMPT_PREFIXES)


def _is_scan_exempt(path: str) -> bool:
    """Return True when *path* should skip injection scanning but NOT the size guard."""
    return bool(_BODY_SCAN_EXEMPT_RE.match(path))


def _scan_value(value: str) -> str | None:
    """Return the label of the first injection pattern matched, or None."""
    for label, pattern in _INJECTION_PATTERNS:
        if pattern.search(value):
            return label
    return None


def _scan_query_params(request: Request) -> str | None:
    """Scan all query-parameter values; return first matched label or None."""
    for param_value in request.query_params.values():
        label = _scan_value(param_value)
        if label:
            return label
    return None


def _scan_body_strings(data: object) -> str | None:
    """
    Recursively scan string leaf-nodes in *data* (dict / list / str).

    Returns the label of the first injection pattern matched, or None.
    """
    if isinstance(data, str):
        return _scan_value(data)
    if isinstance(data, dict):
        for v in data.values():
            result = _scan_body_strings(v)
            if result:
                return result
    if isinstance(data, list):
        for item in data:
            result = _scan_body_strings(item)
            if result:
                return result
    return None


def _rejection_response(error_type: str, detail: str) -> JSONResponse:
    """Build the standardised 400 rejection JSONResponse."""
    return JSONResponse(
        status_code=400,
        content={"error": error_type, "details": detail},
    )


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class ValidationMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that validates and sanitises inbound API requests.

    Registered via ``app.add_middleware(ValidationMiddleware)`` or through
    ``configure_validation(app)`` in ``initialization/middleware.py``.
    """

    def __init__(self, app: ASGIApp, max_body_bytes: int = MAX_BODY_BYTES) -> None:
        super().__init__(app)
        self._max_body_bytes = max_body_bytes

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Health probes, docs, and static assets bypass all checks.
        if _is_fully_exempt(path):
            return await call_next(request)

        # Storage-only paths skip injection scanning but still enforce the size
        # guard — a crafted oversized payload must be rejected regardless of path.
        scan_exempt = _is_scan_exempt(path)

        if not scan_exempt:
            # ── Query-parameter scan ─────────────────────────────────────
            label = _scan_query_params(request)
            if label:
                logger.warning(
                    "validation_middleware: %s detected in query params path=%s ip=%s",
                    label,
                    path,
                    request.client.host if request.client else "unknown",
                )
                return _rejection_response(
                    "VALIDATION_ERROR",
                    f"Request rejected: {label} pattern detected in query parameters.",
                )

        # ── Body size guard + optional injection scan (POST / PUT / PATCH) ──
        if request.method in _BODY_METHODS:
            body_bytes = await request.body()

            if len(body_bytes) > self._max_body_bytes:
                logger.warning(
                    "validation_middleware: body too large (%d bytes) path=%s",
                    len(body_bytes),
                    path,
                )
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": "PAYLOAD_TOO_LARGE",
                        "details": (f"Request body exceeds the {self._max_body_bytes} byte limit."),
                    },
                )

            if not scan_exempt:
                content_type = request.headers.get("content-type", "")
                if "application/json" in content_type and body_bytes:
                    try:
                        payload = json.loads(body_bytes.decode("utf-8"))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        # Malformed JSON — let FastAPI/Pydantic handle it.
                        pass
                    else:
                        label = _scan_body_strings(payload)
                        if label:
                            logger.warning(
                                "validation_middleware: %s detected in body path=%s ip=%s",
                                label,
                                path,
                                request.client.host if request.client else "unknown",
                            )
                            return _rejection_response(
                                "VALIDATION_ERROR",
                                f"Request rejected: {label} pattern detected in request body.",
                            )

        return await call_next(request)
