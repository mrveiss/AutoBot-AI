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


async def audit_secret_op(
    operation: str,
    secret_id: str | None,
    request: Request,
    result: AuditResult = "success",
    **details: str | int,
) -> None:
    """Record one secret operation; an unreachable store never fails it.

    ``details`` must be identifiers or counts (name, scope, reason, count) --
    never a value. The miss is logged by exception class name only.
    """
    try:
        recorded = await audit_log(
            SECRET_OPERATIONS[operation],
            result,
            user_id=_actor(request),
            ip_address=get_client_ip(request) or "unknown",
            resource=secret_log_ref(secret_id) if secret_id else None,
            details=details,
        )
    except Exception as exc:  # noqa: BLE001 -- the audit store being down must not fail a secret operation
        logger.error("[Secrets Audit] audit store write failed for %s: %s", operation, type(exc).__name__)
        return
    # AuditLogger.log reports a failed write by returning False, not by raising.
    if recorded is False:
        logger.error("[Secrets Audit] audit store did not record %s", operation)
