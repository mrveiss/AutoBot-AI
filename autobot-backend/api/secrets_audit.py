# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Secret-operation audit records, written to the canonical audit store (#18648).

``api/secrets.py`` used to carry its own ``audit_log`` that only wrote a log
line, so no secret operation reached the audit trail. This adapter maps a
secret operation onto ``services.audit_logger.audit_log``.

Only identifiers are recorded: a hashed secret reference, the actor, the client
address, the operation and its result. Never a secret value, key material, a
token, a request body, or an exception message (those can echo a value) -- a
failure carries its exception class name only.
"""

from fastapi import Request

from auth_middleware import get_auth_middleware
from autobot_shared.logging_manager import get_logger
from middleware.proxy_utils import get_client_ip
from security.secrets_store_reader import secret_log_ref
from services.audit.outcome import (
    ATTEMPTED,
    OUTCOME_MISSING_MARKER,
    attempt_unrecorded,
    record_audit_attempt,
    record_audit_outcome,
)
from services.audit.taxonomy import AuditEvent
from services.audit_logger import AuditResult, audit_log, get_audit_logger

logger = get_logger(__name__)

#: Audit operation names, ``<domain>.<verb>`` like the store's other operations.
SECRET_OPERATIONS = {
    "CREATE": "secret.create",
    "LIST": "secret.list",
    "ACCESS": "secret.access",
    "UPDATE": "secret.update",
    "DELETE": "secret.delete",
    "TRANSFER": "secret.transfer",
    "BULK_DELETE": "secret.bulk_delete",
}


def _actor(request: Request) -> str | None:
    """The authenticated user id, or ``None`` when it cannot be resolved."""
    try:
        user = get_auth_middleware().get_user_from_request(request)
    except Exception as exc:  # noqa: BLE001 -- an actor lookup must not fail the operation
        logger.warning("[Secrets Audit] actor lookup failed: %s", type(exc).__name__)
        return None
    return str((user or {}).get("user_id", "")) or None


def remember_actor(request: Request, user: dict | None) -> str:
    """The user id of the session *user* ("unknown" when none), kept for every record of this request.

    A second session lookup that comes back empty would file the required DELETE/UPDATE record as
    ``system`` while the operation proceeds; ``"unknown"`` (no session resolved) is not remembered.
    """
    user_id = str((user or {}).get("user_id", "unknown"))
    if user_id != "unknown":
        request.state.audit_actor = user_id
    return user_id


#: ``request.state`` attribute holding the attempt event of each operation awaiting its outcome row.
_PENDING_ATTEMPTS = "audit_attempts"


def _pending(request: Request) -> dict[str, AuditEvent]:
    """The attempts of this request that have no outcome row yet, by operation."""
    pending = getattr(request.state, _PENDING_ATTEMPTS, None)
    if pending is None:
        pending = {}
        setattr(request.state, _PENDING_ATTEMPTS, pending)
    return pending


def _user_id(request: Request, actor: str | None) -> str | None:
    """The caller's resolved id, else the one remembered for this request, else a session lookup."""
    return actor or getattr(request.state, "audit_actor", None) or _actor(request)


async def _secret_event(
    operation: str,
    secret_id: str | None,
    request: Request,
    actor: str | None,
    details: dict,
    result: AuditResult = "success",
) -> AuditEvent:
    """The canonical event of one secret operation, built exactly as ``audit_log`` builds it.

    An attempt's event takes the default: ``record_audit_attempt`` stamps the ``attempted`` result when it writes.
    """
    return (await get_audit_logger()).event(
        SECRET_OPERATIONS[operation],
        result,
        user_id=_user_id(request, actor),
        ip_address=get_client_ip(request) or "unknown",
        resource=secret_log_ref(secret_id) if secret_id else None,
        details=details,
    )


async def _record_attempt(
    operation: str, secret_id: str | None, request: Request, actor: str | None, details: dict
) -> None:
    """The ``attempted`` row through the shared helper: a 503 when it is not written, so nothing is changed (#20557)."""
    try:
        event = await _secret_event(operation, secret_id, request, actor, details)
    except Exception as exc:  # noqa: BLE001 -- an unbuildable record is an unwritten one
        logger.error("[Secrets Audit] could not build the %s attempt: %s", operation, type(exc).__name__)
        raise attempt_unrecorded() from None
    _pending(request)[operation] = await record_audit_attempt(event)


async def _record_outcome(
    operation: str, secret_id: str | None, request: Request, result: AuditResult, actor: str | None, details: dict
) -> None:
    """The outcome row of a pending attempt, linked to it by ``attempt_id``; an unwritable one is logged, not raised."""
    attempt = _pending(request).pop(operation)
    try:
        event = await _secret_event(operation, secret_id, request, actor, details, result)
    except Exception as exc:  # noqa: BLE001 -- the change has happened or failed already; the miss is logged
        logger.error(
            "%s attempt_id=%s [Secrets Audit] could not build the %s outcome: %s",
            OUTCOME_MISSING_MARKER,
            attempt.id,
            operation,
            type(exc).__name__,
        )
        return
    await record_audit_outcome(event, result, attempt_id=attempt.id)


async def _record_plain(
    operation: str, secret_id: str | None, request: Request, result: AuditResult, actor: str | None, details: dict
) -> None:
    """A best-effort record with no attempt before it: an unreachable store never fails the operation."""
    try:
        recorded = await audit_log(
            SECRET_OPERATIONS[operation],
            result,
            user_id=_user_id(request, actor),
            ip_address=get_client_ip(request) or "unknown",
            resource=secret_log_ref(secret_id) if secret_id else None,
            details=details,
        )
    except Exception as exc:  # noqa: BLE001 -- a best-effort record must not fail a secret operation
        logger.error("[Secrets Audit] audit store write failed for %s: %s", operation, type(exc).__name__)
        return
    # AuditLogger.log reports a failed write by returning False, not by raising.
    if recorded is False:
        logger.error("[Secrets Audit] audit store did not record %s", operation)


async def audit_secret_op(
    operation: str,
    secret_id: str | None,
    request: Request,
    result: AuditResult = "success",
    *,
    required: bool = False,
    actor: str | None = None,
    **details: str | int,
) -> None:
    """Record one secret operation.

    ``result="attempted"`` is the record written BEFORE an irreversible credential delete or rotate (#20557):
    it goes through ``services.audit.outcome`` and an unrecorded write raises a 503, so the credential is never
    destroyed or replaced without the durable paper trail #17038 requires. The next record of that operation on
    the request (``success``, ``denied`` or ``failed``) is its outcome, written by the same helper and linked by
    ``attempt_id``. Any other record is best-effort: an unreachable store never fails the operation (the miss is
    logged by exception class name only). ``details`` must be identifiers or counts (name, scope, reason, count)
    -- never a value. ``actor`` is the caller's already-resolved user id: pass it when the route has one, so the
    record never depends on a second session lookup that can come back empty (and be filed as ``system``).
    ``required`` is kept for the callers that pass it; an attempt is always required.
    """
    if result == ATTEMPTED:
        await _record_attempt(operation, secret_id, request, actor, details)
    elif operation in _pending(request):
        await _record_outcome(operation, secret_id, request, result, actor, details)
    else:
        await _record_plain(operation, secret_id, request, result, actor, details)
