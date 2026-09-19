# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Refuse a user API key with 403 on every route that does not accept one (#16294).

Owner ruling on #16294: the SLM accepts a key only on routes that declare the
permission they require (``services/api_key_routes.py``), and refuses it with 403
everywhere else, **even when its scopes would allow the action**. Without this, a key
on an ordinary session route would only meet that route's bearer check and get a 401,
which reads as "authenticate", not as "keys are not accepted here".

The key is not validated first: whether it is valid is irrelevant where no key is
accepted, and validating it would turn every route into a key oracle. The refusal is
audited (``services/api_key_audit.py``).
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from services.api_key_audit import AUDIT_UNAVAILABLE_DETAIL, AuditUnavailable, audit_key_request
from services.api_key_routes import accepts_api_key

API_KEY_HEADER = "X-API-Key"  # pragma: allowlist secret


class ApiKeyAllowListMiddleware(BaseHTTPMiddleware):
    """403 for any request carrying ``X-API-Key`` to a route that does not declare a key permission."""

    async def dispatch(self, request: Request, call_next) -> Response:
        presented = request.headers.get(API_KEY_HEADER)
        if presented and not accepts_api_key(request.app, request.scope):
            try:
                await audit_key_request(
                    request,
                    action="api_key_refused_off_allow_list",
                    allowed=False,
                    status=403,
                    presented_key=presented,
                    reason="API keys are not accepted on this route",
                )
            except AuditUnavailable:  # outside the exception middleware: answer it here, not as a bare 500
                return JSONResponse(status_code=503, content={"detail": AUDIT_UNAVAILABLE_DETAIL})
            return JSONResponse(status_code=403, content={"detail": "API keys are not accepted on this route"})
        return await call_next(request)
