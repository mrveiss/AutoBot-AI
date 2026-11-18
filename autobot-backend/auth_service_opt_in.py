# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one named exception to "the service key is not an admin" (#16333, owner ruling b).

``auth_middleware.check_admin_permission`` and ``get_current_user`` refuse the internal
service key unless the matched route names its caller with :func:`service_opt_in`. Every
admission is audited as ``AuditAction.SERVICE_KEY_ADMITTED``.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from fastapi import HTTPException, Request, status

from autobot_shared.auth.internal_api_key import verify_internal_api_key
from autobot_shared.logging_manager import get_logger
from autobot_shared.logging_once import log_once

logger = get_logger(__name__)

#: Set on a route handler by :func:`service_opt_in`; read from the matched endpoint (#16333).
SERVICE_OPT_IN_ATTR = "__autobot_service_opt_in__"


def service_opt_in(caller: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Let the named internal *caller* reach this route with the service key alone (#16333).

    The owner's ruling: the key is not an admin by default. A route a service genuinely calls
    names that caller here, so the exception is explicit, reviewable and audited. Every
    admission writes ``AuditAction.SERVICE_KEY_ADMITTED`` naming the caller and the route.
    """

    def mark(func: Callable[..., Any]) -> Callable[..., Any]:
        setattr(func, SERVICE_OPT_IN_ATTR, caller)
        return func

    return mark


def opted_in_caller(request: Request) -> Optional[str]:
    return getattr(request.scope.get("endpoint"), SERVICE_OPT_IN_ATTR, None)


def _key_presented(request: Request) -> bool:
    return verify_internal_api_key(request.headers.get("X-Internal-API-Key"))


async def admit_opted_in_service(request: Request) -> Optional[Dict[str, Any]]:
    """The service principal when a valid key reaches a route that names its caller; otherwise None."""
    caller = opted_in_caller(request)
    if caller is None or not _key_presented(request):
        return None
    admitted = getattr(request.state, "service_admission", None)
    if admitted is None:  # one request, one audit row, however many dependencies ask
        admitted = await admit_service(request, caller)
        request.state.service_admission = admitted
    return admitted


async def admit_service(request: Request, caller: str) -> Dict[str, Any]:
    """Admit the key as the non-admin service principal, but only once its audit row is committed.

    Fail closed, by decision: this exception to "the key is not an admin" exists because it is
    recorded, so an admission whose record cannot be committed is refused with 503 rather than
    admitted unrecorded (#16333 review). The row is the awaited, bounded ``record_committed`` write.
    """
    if not await _audit_admission(request, caller):
        logger.error(
            "service-key admission for %s on %r refused: its audit row was not committed", caller, request.url.path
        )
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=ADMISSION_NOT_AUDITED)
    return {"username": f"service:{caller}", "role": "service", "service": True}


ADMISSION_NOT_AUDITED = "Service access could not be recorded; try again"


async def _audit_admission(request: Request, caller: str) -> bool:
    try:
        from services.audit.audit import record_committed  # noqa: PLC0415  (audit imports this module's peers)
        from services.audit.taxonomy import AuditAction, AuditCategory, AuditEvent, action_name  # noqa: PLC0415

        return await record_committed(
            AuditEvent(
                category=AuditCategory.SECURITY,
                action=action_name(AuditAction.SERVICE_KEY_ADMITTED),
                actor_id=f"service:{caller}",
                resource_type="route",
                resource_id=request.url.path,
                metadata={"method": request.method, "caller": caller},
                ip_address=request.client.host if request.client else None,
            )
        )
    except Exception:  # a row that could not even be built is a row that was not written
        logger.exception("audit: could not record a service-key admission for %s", caller)
        return False


def warn_if_key_without_session(request: Request) -> None:
    """Name the likely cause once per process when a proxied call has the key but no usable session (#16333).

    The SLM proxy forwards the admin's own token beside the key. If the backend cannot verify that
    token, the SLM and backend JWT secrets probably differ: before #16333 the key hid it.
    """
    if _key_presented(request):
        log_once(
            logger,
            logging.WARNING,
            "key_without_session",
            "service key presented on %r without a session the backend can verify: the key is not an admin "
            "here (#16333); if this came through the SLM proxy, the SLM and backend JWT secrets may differ",
            request.url.path,
        )
