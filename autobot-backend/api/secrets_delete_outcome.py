# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The audit outcome of a failed ``DELETE /api/secrets/{id}``, and the HTTP error it maps to (#21204).

The route records ``attempted`` before it writes. Every way the delete then fails must leave an outcome
record after it, or the trail reads as a bare intent: ``denied`` for a refusal (permission, dependents, any
other non-2xx such as the lock-timeout and vault-not-configured 503s), ``failed`` for a missing secret or an
unexpected error. :func:`outcome_for` is the one mapping; the main route and
``envelope_secrets_delete.audited_delete`` both call it (#21506). Records carry
identifiers and the exception CLASS name only, never ``exc.detail`` or a message (``secrets_audit``: those can
echo a value).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import HTTPException, Request

from autobot_shared.logging_manager import get_logger
from services.audit_logger import AuditResult
from services.envelope_secrets_service import SecretNotFoundError

logger = get_logger(__name__)

#: ``audit_secret_op``, passed in by the route so a test (or an operator) that replaces it on ``api.secrets``
#: governs every record of the request.
Audit = Callable[..., Awaitable[Any]]


def _http_outcome(exc: HTTPException) -> tuple[AuditResult, str]:
    """The (result, reason) a non-2xx response is recorded as."""
    if exc.status_code == 404:
        return "failed", "not_found"
    if exc.status_code == 409:
        return "denied", "has_dependents"
    return "denied", "http_%d" % exc.status_code


def outcome_for(exc: BaseException) -> tuple[AuditResult, str]:
    """The (result, reason) a failed delete is recorded as, on every delete route.

    A missing secret is ``failed`` / ``not_found`` whether it surfaces as an HTTP 404 or as
    ``SecretNotFoundError``, as the ACCESS and UPDATE records already do (#21506).
    """
    if isinstance(exc, HTTPException):
        return _http_outcome(exc)
    if isinstance(exc, PermissionError):
        return "denied", "permission_denied"
    if isinstance(exc, SecretNotFoundError):
        return "failed", "not_found"
    return "failed", type(exc).__name__


async def record_delete_failure(
    audit: Audit, secret_id: str, request: Request, exc: Exception, *, intent_recorded: bool
) -> HTTPException:
    """Record the outcome of the failed delete *exc* and return the HTTP error the route raises.

    ``intent_recorded`` is False while the ``attempted`` record is itself unwritten: an HTTP error then IS
    that record failing ("audit trail unavailable", 503), and a second record would only fail the same way.
    """
    if isinstance(exc, HTTPException) and not intent_recorded:
        return exc
    result, reason = outcome_for(exc)
    await audit("DELETE", secret_id, request, result, reason=reason)
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=403, detail="Internal server error")
    logger.error("Failed to delete secret: %s", type(exc).__name__)
    return HTTPException(status_code=500, detail="Failed to delete secret")
