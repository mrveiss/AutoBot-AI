# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Security Headers Middleware (Issue #2858)

Adds HTTP security response headers to every response and enforces
CSRF mitigation for state-changing requests.

CSRF Mitigation Strategy
------------------------
This application uses header-based Bearer token authentication exclusively
(HTTPBearer dependency in services/auth.py — no auth cookies are ever set).
Browsers do NOT automatically attach custom Authorization headers to
cross-origin requests, so a malicious third-party page cannot perform
authenticated state-changing requests on behalf of a logged-in user.

This means the app already has CSRF protection by design.  This middleware
makes that protection **explicit and auditable** by:

  1. Rejecting state-changing requests (POST/PUT/PATCH/DELETE) that lack an
     Authorization header entirely — belt-and-suspenders on top of the
     HTTPBearer dependency.
  2. Adding standard security response headers to every response so that
     browsers receive explicit framing, MIME-sniffing, and XSS instructions.

Reference: OWASP CSRF Prevention Cheat Sheet — "Use of Custom Request Headers"
https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
"""

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# HTTP methods that can change server state
_STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Paths exempt from the Authorization header check.
# These are unauthenticated endpoints where no token exists yet.
_AUTH_EXEMPT_PREFIXES = (
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/sso/",
    "/api/health",
    "/api/docs",
    "/api/redoc",
    "/api/openapi.json",
    "/api/api-keys/scopes",  # public endpoint — no auth required
    "/api/nodes/",  # agent heartbeats — no browser auth, endpoints have own guards
    "/api/events/sync",  # agent event sync — node_id validated in endpoint (#3193)
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that adds security headers and enforces CSRF mitigation.

    Must be registered AFTER CORSMiddleware so CORS headers are already
    present when this middleware inspects the request.

    Issue #2858 — explicit CSRF protection enforcement.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request: enforce CSRF check, then add security headers."""
        if self._is_state_changing(request) and not self._is_exempt(request):
            if not self._has_authorization_header(request):
                logger.warning(
                    "CSRF guard: rejected %s %s — missing Authorization header",
                    request.method,
                    request.url.path,
                )
                rejection = JSONResponse(
                    status_code=401,
                    content={"detail": "Authorization header required"},
                )
                _add_security_headers(rejection)
                return rejection

        response = await call_next(request)
        _add_security_headers(response)
        return response

    @staticmethod
    def _is_state_changing(request: Request) -> bool:
        return request.method in _STATE_CHANGING_METHODS

    @staticmethod
    def _is_exempt(request: Request) -> bool:
        path = request.url.path
        return any(path.startswith(prefix) for prefix in _AUTH_EXEMPT_PREFIXES)

    @staticmethod
    def _has_authorization_header(request: Request) -> bool:
        return "authorization" in request.headers


def _add_security_headers(response: Response) -> None:
    """Attach standard HTTP security headers to an outgoing response.

    Args:
        response: Starlette/FastAPI response object to mutate in-place.
    """
    # Prevent page from being embedded in frames (clickjacking defence)
    response.headers.setdefault("X-Frame-Options", "DENY")

    # Prevent MIME-type sniffing
    response.headers.setdefault("X-Content-Type-Options", "nosniff")

    # Force HTTPS for 1 year (only meaningful when served over TLS)
    response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

    # Disable legacy XSS filter (modern browsers — use CSP instead)
    response.headers.setdefault("X-XSS-Protection", "0")

    # Restrict Referrer information leaked to third parties
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")

    # Minimal Content-Security-Policy: API-only backend, no HTML served
    response.headers.setdefault("Content-Security-Policy", "default-src 'none'")

    # Disable interest-cohort FLoC / Privacy Sandbox APIs
    response.headers.setdefault("Permissions-Policy", "interest-cohort=()")
