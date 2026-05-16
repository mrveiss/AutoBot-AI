# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Config Revision Service (#1404)

Manages configuration audit trail: recording changes with before/after
snapshots, computing diffs, redacting secrets, and rolling back to any
prior revision.
"""

import uuid
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from models.config_revision import ConfigRevision

logger = get_logger(__name__)

# Keys whose values must be redacted in stored snapshots.
_SECRET_SUBSTRINGS = frozenset(["password", "secret", "key", "token", "api_key"])
_REDACTED = "***REDACTED***"


def _is_secret_key(key: str) -> bool:
    """Return True if key name suggests a sensitive value (#1404)."""
    lower = key.lower()
    return any(sub in lower for sub in _SECRET_SUBSTRINGS)


def redact_secrets(config_dict: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """Return a copy of config_dict with secret values replaced (#1404).

    Only top-level keys are inspected. Nested structures are not
    recursively redacted to keep the implementation focused.
    """
    if config_dict is None:
        return None
    return {k: (_REDACTED if _is_secret_key(k) else v) for k, v in config_dict.items()}


def compute_diff(
    before: Dict[str, Any] | None,
    after: Dict[str, Any],
) -> List[str]:
    """Return sorted list of top-level keys that differ between snapshots (#1404)."""
    before = before or {}
    all_keys = set(before) | set(after)
    return sorted(k for k in all_keys if before.get(k) != after.get(k))


class ConfigRevisionService:
    """Service for config revision CRUD and rollback (#1404)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # -- Write ---------------------------------------------------------

    async def create_revision(
        self,
        entity_type: str,
        entity_id: str,
        before_config: Dict[str, Any] | None,
        after_config: Dict[str, Any],
        source: str,
        created_by: str,
    ) -> ConfigRevision:
        """Persist a new config revision with redacted snapshots (#1404)."""
        safe_before = redact_secrets(before_config)
        safe_after = redact_secrets(after_config)
        changed = compute_diff(safe_before, safe_after)

        revision = ConfigRevision(
            entity_type=entity_type,
            entity_id=entity_id,
            before_config=safe_before,
            after_config=safe_after,
            changed_keys=changed,
            source=source,
            created_by=created_by,
        )
        self.session.add(revision)
        await self.session.commit()
        await self.session.refresh(revision)

        logger.info(
            "Config revision %s created: %s/%s by %s (%s keys changed)",
            revision.id,
            entity_type,
            entity_id,
            created_by,
            len(changed),
        )
        return revision

    async def rollback_to_revision(
        self,
        revision_id: uuid.UUID,
        created_by: str,
    ) -> ConfigRevision:
        """Restore config to a prior snapshot and record the rollback (#1404).

        Returns the new revision that captures the rollback action.
        """
        target = await self._get_or_raise(revision_id)
        current = await self._get_latest(target.entity_type, target.entity_id)

        new_revision = await self.create_revision(
            entity_type=target.entity_type,
            entity_id=target.entity_id,
            before_config=current.after_config if current else None,
            after_config=target.after_config or {},
            source="rollback",
            created_by=created_by,
        )
        logger.info(
            "Rolled back %s/%s to revision %s (new revision %s)",
            target.entity_type,
            target.entity_id,
            revision_id,
            new_revision.id,
        )
        return new_revision

    # -- Read ----------------------------------------------------------

    async def get_revisions(
        self,
        entity_type: str,
        entity_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ConfigRevision]:
        """List revisions for an entity, newest first (#1404)."""
        stmt = (
            select(ConfigRevision)
            .where(
                ConfigRevision.entity_type == entity_type,
                ConfigRevision.entity_id == entity_id,
            )
            .order_by(ConfigRevision.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_revision(self, revision_id: uuid.UUID) -> ConfigRevision | None:
        """Fetch a single revision by primary key (#1404)."""
        stmt = select(ConfigRevision).where(ConfigRevision.id == revision_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    # -- Internal helpers ----------------------------------------------

    async def _get_or_raise(self, revision_id: uuid.UUID) -> ConfigRevision:
        """Load revision or raise ValueError if not found (#1404)."""
        revision = await self.get_revision(revision_id)
        if revision is None:
            raise ValueError(f"ConfigRevision {revision_id} not found")
        return revision

    async def _get_latest(
        self,
        entity_type: str,
        entity_id: str,
    ) -> ConfigRevision | None:
        """Return the most recent revision for an entity (#1404)."""
        stmt = (
            select(ConfigRevision)
            .where(
                ConfigRevision.entity_type == entity_type,
                ConfigRevision.entity_id == entity_id,
            )
            .order_by(ConfigRevision.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
