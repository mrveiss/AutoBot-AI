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


def _refusal_reason(request: Request) -> tuple[str, str]:
    """(the credential form presented, why it was refused) for a 401 log -- never a value (#20750).

    The forms are the internal key, the HMAC X-Service-* headers, or none. Naming which one came,
    and why it failed, is what lets an operator tell a key mismatch from a missing key or an
    unsigned call without reading a credential.
    """
    if request.headers.get("X-Internal-API-Key"):
        if not internal_api_key():
            return "X-Internal-API-Key", "the backend has no AUTOBOT_INTERNAL_API_KEY configured"
        return "X-Internal-API-Key", "it does not match the backend's AUTOBOT_INTERNAL_API_KEY"
    if request.headers.get("X-Service-ID") or request.headers.get("X-Service-Signature"):
        return "X-Service-* (HMAC)", "the service signature did not validate"
    return "none", "no service credential was presented"


async def validated_service(request: Request) -> Dict:
    """``validate_service_auth``, logging a refusal with the credential form presented; re-raises it."""
    try:
        return await validate_service_auth(request)
    except HTTPException:
        form, reason = _refusal_reason(request)
        logger.warning(
            "service principal refused: presented %s; %s",
            form,
            reason,
            extra={"credential_form": form, "path": request.url.path, "method": request.method},
        )
        raise
