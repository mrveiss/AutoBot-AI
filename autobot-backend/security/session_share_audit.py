# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The audit bracket around a session share/unshare (#18890 AC3).

``attempted`` is written durably BEFORE the table changes (the audit store is not the share table, so one
transaction cannot cover both) and a record that is not committed refuses the change. The final outcome is
written after it, also when the change raises or is cancelled (the write is bounded by
``AUDIT_DURABLE_TIMEOUT_SECONDS``, so it cannot hold a cancellation open). The table has already changed, so a
failure there cannot refuse anything and is logged by
exception class only, as ``api.secrets_audit.audit_secret_op`` does for a non-required record. Both go through
``services.audit_logger.audit_log(durable=True)``, the primitive the secrets audit uses.
"""

import asyncio
from collections.abc import Awaitable, Callable

from autobot_shared.logging_manager import get_logger
from security import session_shares
from services.audit_logger import AuditResult, audit_log

logger = get_logger(__name__)

_OPERATIONS = {"share": "session.share", "unshare": "session.unshare"}


class ShareAuditError(Exception):
    """The ``attempted`` audit record could not be written, so the share change was not made (#18890)."""


async def _write(action: str, result: AuditResult, actor: dict, session_id: str, details: dict) -> bool:
    """One durable audit row; False when it was not committed. Never raises, never logs a message."""
    try:
        return bool(
            await audit_log(
                _OPERATIONS[action],
                result,
                user_id=actor["user_id"],
                ip_address=actor["ip"],
                session_id=session_id,
                resource=session_id,
                details={**details, "username": actor["username"]},
                durable=True,
            )
        )
    except Exception as exc:  # noqa: BLE001 -- reported as a failed write, class name only
        logger.error(
            "Share audit write failed for %s (%s): %s",
            action,
            result,
            type(exc).__name__,
        )
        return False


async def _record_outcome(action: str, result: AuditResult, actor: dict, session_id: str, details: dict) -> None:
    """The final record. The change is already made, so a failed write is logged, not refused."""
    if not await _write(action, result, actor, session_id, details):
        logger.error("Share audit outcome %s for %s was not recorded", result, action)


async def audited_change(
    action: str,
    actor: dict,
    session_id: str,
    participants: list[str],
    change: Callable[[], Awaitable[bool]],
) -> bool:
    """Run ``change`` between an ``attempted`` row and its outcome row; ``ShareAuditError`` if the first fails."""
    details: dict = {"participants": participants}
    if not await _write(action, "attempted", actor, session_id, details):
        raise ShareAuditError(action)
    try:
        changed = await change()
    except (
        Exception,
        asyncio.CancelledError,
    ):  # a cancelled change is an error outcome too, then re-raised
        await _record_outcome(action, "error", actor, session_id, details)
        raise
    if changed:
        await _record_outcome(action, "success", actor, session_id, details)
    else:
        reason = "not_a_participant" if action == "unshare" else "not_recorded"
        await _record_outcome(action, "failed", actor, session_id, {**details, "reason": reason})
    return changed


async def _add_share(redis, session_id: str, shared_with_ids: list[str], shared_by: str) -> bool:
    """The table write of a share. False = not recorded."""
    try:
        await session_shares.ensure_adopted(redis)
        await session_shares.durable_add(session_id, shared_with_ids, shared_by)
        logger.info(
            "Session %s... shared by %s with %d users",
            session_id[:8],
            shared_by,
            len(shared_with_ids),
        )
        return True
    except Exception as e:
        logger.error("Failed to share session: %s", e)
        return False


async def share_audited(
    redis,
    session_id: str,
    shared_with_ids: list[str],
    shared_by: str,
    actor: dict | None,
) -> bool:
    """Share a session between its ``attempted`` and outcome audit rows."""
    actor = actor or {"user_id": shared_by, "username": shared_by, "ip": "unknown"}
    return await audited_change(
        "share",
        actor,
        session_id,
        shared_with_ids,
        lambda: _add_share(redis, session_id, shared_with_ids, shared_by),
    )


async def unshare_audited(redis, session_id: str, user_id: str, actor: dict) -> bool:
    """Remove one participant between its ``attempted`` and outcome audit rows; a failure raises."""
    return await audited_change(
        "unshare",
        actor,
        session_id,
        [user_id],
        lambda: session_shares.remove_share(redis, session_id, user_id),
    )
