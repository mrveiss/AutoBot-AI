# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""API-key requests in the SLM audit log, set apart from session requests (#16294).

Owner ruling on #16294 (2026-09-18): key-authenticated requests are audited
distinctly from session requests. Every decision about a request that presented an
``X-API-Key`` writes one row: refused off the allow-list, key rejected, scope
refused, or allowed. The row is ``resource_type="api_key"`` with
``extra_data.auth_method == "api_key"``, and carries the key's id where known and its
identification prefix (the first 12 characters, which the key table stores in
plaintext for the same purpose).

A write that fails is logged and raised as ``AuditUnavailable``. A key request that
cannot be audited does not proceed, because the ruling makes the audit part of
accepting a key. Each caller answers it with an explicit 503, never a bare 500.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

#: What a caller answers when the audit write fails.
AUDIT_UNAVAILABLE_DETAIL = "API-key requests are refused while the audit log is unavailable"


class AuditUnavailable(Exception):
    """The key request's audit row could not be written; the request must not proceed."""


#: Characters of a presented key recorded to identify it; the key table's ``key_prefix`` length.
KEY_PREFIX_LENGTH = 12


async def audit_key_request(
    request: Any,
    *,
    action: str,
    allowed: bool,
    status: int,
    presented_key: str | None = None,
    api_key_id: str | None = None,
    username: str | None = None,
    permission: str | None = None,
    reason: str | None = None,
) -> None:
    """Write one audit row for a request that presented an API key."""
    try:
        await _write(request, action, allowed, status, presented_key, api_key_id, username, permission, reason)
    except Exception as exc:
        logger.exception("API-key audit write failed for %s %s (%s)", request.method, request.url.path, action)
        raise AuditUnavailable(action) from exc


async def _write(request, action, allowed, status, presented_key, api_key_id, username, permission, reason) -> None:
    from api.security import create_audit_log
    from services.database import db_service

    async with db_service.session() as db:
        await create_audit_log(
            db,
            category="authorization",
            action=action,
            username=username,
            resource_type="api_key",
            resource_id=api_key_id,
            description=f"API-key request {'allowed' if allowed else 'refused'}: {action}",
            request_method=request.method,
            request_path=request.url.path,
            response_status=status,
            success=allowed,
            error_message=reason,
            extra_data={
                "auth_method": "api_key",
                "key_prefix": (presented_key or "")[:KEY_PREFIX_LENGTH] or None,
                "permission": permission,
            },
        )
