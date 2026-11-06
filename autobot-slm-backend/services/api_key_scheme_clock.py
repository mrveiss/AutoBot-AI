# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""When the PBKDF2 API-key hash scheme became active, and the cutoff it starts (#20611).

New keys are stored as a PBKDF2-HMAC-SHA256 digest. Keys hashed in an older format
(HMAC under the current or the legacy pepper, bare SHA-256) still verify and are re-hashed
in place on their next successful use. The moment the new scheme became active is stored once,
in the SLM ``settings`` table (main database, key ``api_key_pbkdf2_active_since``), the first
time a pepper-backed hash is needed after the scheme ships. ``LEGACY_CUTOFF_DAYS`` after it, an
old-format key that was never re-hashed is refused and its owner must reissue it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: ``Setting.key`` holding the ISO-8601 instant the PBKDF2 scheme became active.
SCHEME_ACTIVE_SETTING_KEY = "api_key_pbkdf2_active_since"

#: Days after activation that an old-format, never re-hashed key is still accepted.
LEGACY_CUTOFF_DAYS = env_int_clamped("SLM_API_KEY_LEGACY_CUTOFF_DAYS", 30, 1, 3650)

#: Shown to the key holder and written to the audit row.
EXPIRED_DETAIL = "API key expired: reissue it"


class APIKeyLegacyFormatExpiredError(Exception):
    """An old-format key was not re-hashed before the cutoff; it must be reissued."""

    def __init__(self, api_key_id) -> None:
        super().__init__(EXPIRED_DETAIL)
        self.api_key_id = api_key_id


_cached: datetime | None = None


def reset_cache() -> None:
    """Forget the per-process copy of the activation instant (tests)."""
    global _cached
    _cached = None


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


async def _read(db) -> str | None:
    from models.database import Setting

    row = (await db.execute(select(Setting).where(Setting.key == SCHEME_ACTIVE_SETTING_KEY))).scalar_one_or_none()
    return row.value if row is not None else None


async def _insert_now(db) -> bool:
    """Insert the activation instant; ``False`` when another worker's row won the race."""
    from models.database import Setting

    row = Setting(
        key=SCHEME_ACTIVE_SETTING_KEY,
        value=datetime.now(timezone.utc).isoformat(),
        value_type="string",
        description="When the PBKDF2 API-key hash scheme became active (#20611).",
    )
    try:
        async with db.begin_nested():
            db.add(row)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return False
    return True


async def scheme_active_since() -> datetime:
    """Return the activation instant, recording it on first call (set once, never moved)."""
    global _cached
    if _cached is not None:
        return _cached
    from services.database import db_service

    async with db_service.session() as db:
        stored = await _read(db)
        if stored is None:
            await _insert_now(db)  # losing the race is fine: the winner's row is read back
            stored = await _read(db)
    if stored is None:
        raise RuntimeError("API-key scheme activation instant could not be recorded")
    _cached = _parse(stored)
    return _cached


def cutoff_passed(active_since: datetime, now: datetime | None = None) -> bool:
    """True once ``LEGACY_CUTOFF_DAYS`` have elapsed since *active_since*."""
    return (now or datetime.now(timezone.utc)) >= active_since + timedelta(days=LEGACY_CUTOFF_DAYS)
