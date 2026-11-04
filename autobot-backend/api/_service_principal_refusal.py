# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The System vault's HMAC service check, with its refusal logged by the credential FORM presented (#20750).

``api.envelope_secrets.service_principal`` admits the internal key, then falls back to the HMAC
``X-Service-*`` check. A refused caller left no log naming what it sent, so an operator couldn't tell a
key mismatch from a missing key or an unsigned call without reading a credential. The log names the
form (the internal key, the HMAC headers, or none) and why it failed -- never a value or a fingerprint.
"""

from __future__ import annotations

from typing import Dict

from fastapi import HTTPException, Request

from autobot_shared.logging_manager import get_logger
from autobot_shared.node_proxy import internal_api_key
from security.service_auth import validate_service_auth

logger = get_logger(__name__)


#: validate_service_auth's fixed server-side contexts -> the reason logged. Mapped, never echoed: one of
#: them interpolates the caller's service id, which is client input.
_HMAC_REASONS = (
    ("Missing required headers", "the X-Service-* headers are incomplete"),
    ("Invalid timestamp format", "the request timestamp is malformed"),
    ("Timestamp outside", "the request timestamp is outside the allowed window"),
    ("Unknown service", "the service is not registered"),
    ("Invalid signature", "the service signature did not validate"),
)


def _form(request: Request) -> str:
    """The credential form a request presented: the internal key, the HMAC headers, or none."""
    if request.headers.get("X-Internal-API-Key"):
        return "X-Internal-API-Key"
    if request.headers.get("X-Service-ID") or request.headers.get("X-Service-Signature"):
        return "X-Service-* (HMAC)"
    return "none"


def _refusal_reason(form: str, refusal: HTTPException) -> str:
    """Why a 401/403 refused *form*: from the backend's own key state or the check's fixed detail."""
    if form == "X-Internal-API-Key":
        if not internal_api_key():
            return "the backend has no AUTOBOT_INTERNAL_API_KEY configured"
        return "it does not match the backend's AUTOBOT_INTERNAL_API_KEY"
    if form == "none":
        return "no service credential was presented"
    detail = str(refusal.detail)
    return next(
        (reason for marker, reason in _HMAC_REASONS if marker in detail), f"refused (HTTP {refusal.status_code})"
    )


async def validated_service(request: Request) -> Dict:
    """``validate_service_auth``; a 401/403 is logged as a refusal with its form and reason, a 5xx as an
    auth-service error. Each re-raises unchanged."""
    try:
        return await validate_service_auth(request)
    except HTTPException as failure:
        form = _form(request)
        where = {"credential_form": form, "path": request.url.path, "method": request.method}
        if failure.status_code >= 500:
            logger.error(
                "service principal check failed: the authentication service errored (HTTP %s); presented %s",
                failure.status_code,
                form,
                extra=where,
            )
        elif failure.status_code in (401, 403):
            reason = _refusal_reason(form, failure)
            logger.warning("service principal refused: presented %s; %s", form, reason, extra=where)
        raise
