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

from fastapi import HTTPException, Request

from auth_middleware import get_auth_middleware
from autobot_shared.logging_manager import get_logger
from middleware.proxy_utils import get_client_ip
from security.secrets_store_reader import secret_log_ref
from services.audit_logger import AuditResult, audit_log

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

    By default an unreachable store never fails the operation (the miss is
    logged by exception class name only). ``required=True`` is for the record
    written BEFORE an irreversible credential delete or rotate (#20557): an
    unrecorded write raises a 503, so the credential is never destroyed or
    replaced without the durable paper trail #17038 requires. ``details`` must
    be identifiers or counts (name, scope, reason, count) -- never a value. ``actor`` is the
    caller's already-resolved user id: pass it when the route has one, so the record never
    depends on a second session lookup that can come back empty (and be filed as ``system``).
    """
    try:
        recorded = await audit_log(
            SECRET_OPERATIONS[operation],
            result,
            user_id=actor or getattr(request.state, "audit_actor", None) or _actor(request),
            ip_address=get_client_ip(request) or "unknown",
            resource=secret_log_ref(secret_id) if secret_id else None,
            details=details,
            durable=required,  # a required record is awaited until committed, not just scheduled
        )
    except Exception as exc:  # noqa: BLE001 -- a best-effort record must not fail a secret operation
        logger.error("[Secrets Audit] audit store write failed for %s: %s", operation, type(exc).__name__)
        recorded = False
    # AuditLogger.log reports a failed write by returning False, not by raising.
    if recorded is False:
        logger.error("[Secrets Audit] audit store did not record %s", operation)
        if required:
            raise HTTPException(status_code=503, detail="Audit trail unavailable; nothing was changed")
