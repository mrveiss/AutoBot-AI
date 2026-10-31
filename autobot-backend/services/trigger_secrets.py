# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Webhook trigger secrets at rest: fail-closed encryption, legacy reads, audit (#19759).

A webhook HMAC secret is only ever written encrypted. When ``EncryptionService`` cannot be
built the write is refused with :class:`EncryptionUnavailableError` -- storing the secret
in plaintext instead would silently downgrade a credential, and the downgrade would be
invisible to the caller.

Rows written before that rule are still plaintext (64 hex characters, the shape of
``secrets.token_hex(32)``) and are **not** migrated here. They stay readable so existing
webhooks keep verifying. :func:`find_plaintext_secret_trigger_ids` lists them and
:func:`propose_plaintext_secret_rewrite` raises one approval for a human to decide
(#17038: no code path rewrites a stored credential on its own). Both report trigger ids
only, never a value.
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from autobot_shared.env_utils import env_float_clamped, env_str
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Redis key prefix for webhook secrets, not a hardcoded secret
SECRET_PREFIX = "workflows:trigger_secret:"  # nosec B105  # pragma: allowlist secret

#: Cron for the plaintext-secret audit beat entry (registered in env_registry_llc).
TRIGGER_SECRET_AUDIT_SCHEDULE = env_str("AUTOBOT_TRIGGER_SECRET_AUDIT_SCHEDULE", "25 3 * * *")

#: Days a rejected proposal keeps suppressing a new one for the same plaintext set.
REJECTION_SUPPRESS_DAYS = env_float_clamped("AUTOBOT_TRIGGER_SECRET_AUDIT_REJECTION_DAYS", 30.0, min_v=1.0)

#: Marks the proposal this module raises, to tell it apart from other destructive gates.
PROPOSAL_KIND = "trigger_secret_plaintext_rewrite"

#: The requester recorded on the proposal; there is no agent, so no UUID is invented.
AUDIT_REQUESTER = "trigger-secret-audit"

# What ``secrets.token_hex(32)`` produces. Ciphertext is base64 of >=76 bytes (>=104
# characters), so a stored value of this shape cannot be an encrypted one.
_LEGACY_PLAINTEXT = re.compile(r"[0-9a-f]{64}")

_encryption_service = None


class EncryptionUnavailableError(RuntimeError):
    """Raised instead of storing a trigger secret unencrypted."""


class SecretStorageError(RuntimeError):
    """Raised when a trigger secret could not be written; the trigger is not registered."""


def store_secret(redis: Any, trigger_id: str, stored: str, ttl: int) -> None:
    """Write the already-encrypted secret; raise :class:`SecretStorageError` on failure."""
    try:
        redis.setex(f"{SECRET_PREFIX}{trigger_id}", ttl, stored)
    except Exception as exc:
        logger.error("Storing the webhook secret for trigger %s failed: %s", trigger_id, type(exc).__name__)
        raise SecretStorageError("Webhook secret could not be stored") from exc


def _get_encryption_service():
    """Return a singleton EncryptionService, or None if unavailable."""
    global _encryption_service  # noqa: PLW0603
    if _encryption_service is None:
        try:
            from encryption_service import EncryptionService

            _encryption_service = EncryptionService()
        except Exception as exc:
            logger.error("EncryptionService unavailable: %s", exc)
    return _encryption_service


def encrypt_secret(secret: str) -> str:
    """Encrypt *secret* for storage; raise rather than return it unencrypted."""
    enc = _get_encryption_service()
    if enc is None:
        raise EncryptionUnavailableError("Webhook secret encryption is unavailable; refusing to store the secret")
    try:
        return enc.encrypt(secret)
    except ValueError as exc:
        # The service wraps its failure text in a ValueError; the route would turn it into a 422.
        logger.error("Webhook secret encryption failed: %s", type(exc).__name__)
        raise EncryptionUnavailableError("Webhook secret encryption failed; refusing to store the secret") from exc


def is_legacy_plaintext(stored: str) -> bool:
    """True if *stored* has the shape of a pre-#19759 plaintext secret."""
    return bool(_LEGACY_PLAINTEXT.fullmatch(stored))


def decode_stored_secret(stored: str) -> str | None:
    """Return the HMAC secret for a stored value, or None if it cannot be recovered.

    Legacy plaintext rows are returned as stored so existing webhooks keep verifying.
    """
    if is_legacy_plaintext(stored):
        return stored
    enc = _get_encryption_service()
    if enc is None:
        logger.warning("Cannot decrypt a stored webhook secret: encryption unavailable")
        return None
    return enc.decrypt(stored)


def find_plaintext_secret_trigger_ids(redis: Any) -> list[str]:
    """Ids of triggers whose stored secret is plaintext. Never returns a value.

    Synchronous Redis scan: for workers (the Celery audit) only, never an event-loop handler.
    """
    ids = []
    for key in redis.scan_iter(match=f"{SECRET_PREFIX}*"):
        key = key.decode() if isinstance(key, bytes) else key
        raw = redis.get(key)
        stored = raw.decode() if isinstance(raw, bytes) else raw
        if stored and is_legacy_plaintext(stored):
            ids.append(key[len(SECRET_PREFIX) :])
    return sorted(ids)


def _covers(approval: Any, ids: list[str], rejected_since: datetime) -> bool:
    """True if *approval* already answers for *ids*: pending, or recently rejected, on a superset."""
    from llc.models.enums import ApprovalStatus

    ctx = approval.context or {}
    if ctx.get("kind") != PROPOSAL_KIND or not set(ids) <= set(ctx.get("trigger_ids", [])):
        return False
    if approval.status == ApprovalStatus.PENDING.value:
        return True
    decided = approval.decided_at
    return decided is None or decided.replace(tzinfo=decided.tzinfo or timezone.utc) >= rejected_since


async def _already_covered(session: Any, ids: list[str]) -> bool:
    """True if a pending proposal, or one rejected within the window, covers *ids*.

    A superset counts, so a changed set never leaves two pending proposals and a
    human's rejection is not overridden hourly. Nothing is closed or edited here.
    """
    from sqlalchemy import select

    from llc.models.enums import ApprovalStatus
    from models.approval import Approval

    result = await session.execute(
        select(Approval).where(
            Approval.requested_by_agent == AUDIT_REQUESTER,
            Approval.status.in_([ApprovalStatus.PENDING.value, ApprovalStatus.REJECTED.value]),
        )
    )
    since = datetime.now(timezone.utc) - timedelta(days=REJECTION_SUPPRESS_DAYS)
    return any(_covers(a, ids, since) for a in result.scalars().all())


async def propose_plaintext_secret_rewrite(session: Any, redis: Any) -> Any:
    """Raise one approval listing plaintext-secret triggers; rewrite nothing.

    Returns the pending ``Approval`` (caller commits, then calls ``publish_requested``),
    or None when no plaintext secret exists or a proposal already covers the set (see
    :func:`_already_covered`: pending, or rejected within the suppression window).
    """
    from llc.models.enums import ApprovalType
    from llc.services.approval import ApprovalService

    ids = find_plaintext_secret_trigger_ids(redis)
    logger.info("#19759: %d trigger(s) hold a plaintext webhook secret", len(ids))
    if not ids or await _already_covered(session, ids):
        return None
    return await ApprovalService().request_approval(
        session,
        company_id=None,
        gate_type=ApprovalType.DESTRUCTIVE_ACTION,
        payload={
            "kind": PROPOSAL_KIND,
            "summary": f"Re-encrypt the webhook secret of {len(ids)} trigger(s) stored in plaintext",
            "trigger_ids": ids,
        },
        requested_by=AUDIT_REQUESTER,
    )
