# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC API key service — issue, revoke, validate (GH#8218)."""

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llc.models.api_key import LLCApiKey

from .base import LLCServiceBase

logger = logging.getLogger(__name__)

_KEY_PREFIX = "llc_"


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class ApiKeyService(LLCServiceBase):
    """Issue, revoke, and validate LLC agent API keys."""

    async def issue_key(
        self,
        session: AsyncSession,
        agent_id: str,
        company_id: str,
        name: str,
    ) -> Tuple[LLCApiKey, str]:
        """Create a new API key. Returns (record, plaintext). Plaintext shown once."""
        raw = _KEY_PREFIX + secrets.token_urlsafe(48)
        record = LLCApiKey(
            id=uuid.uuid4(),
            agent_id=agent_id,
            company_id=company_id,
            name=name,
            key_hash=_hash_key(raw),
            created_at=datetime.now(timezone.utc),
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record, raw

    async def revoke_key(
        self,
        session: AsyncSession,
        agent_id: str,
        key_id: uuid.UUID,
    ) -> None:
        """Revoke a key (sets revoked_at). Raises KeyError if not found or not owned."""
        result = await session.execute(
            select(LLCApiKey).where(
                LLCApiKey.id == key_id,
                LLCApiKey.agent_id == agent_id,
                LLCApiKey.revoked_at.is_(None),
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            raise KeyError(f"API key {key_id} not found for agent {agent_id}")
        record.revoked_at = datetime.now(timezone.utc)
        await session.commit()

    async def validate_key(
        self,
        session: AsyncSession,
        raw_key: str,
    ) -> Optional[LLCApiKey]:
        """Return the key record if valid and active, else None."""
        key_hash = _hash_key(raw_key)
        result = await session.execute(
            select(LLCApiKey).where(
                LLCApiKey.key_hash == key_hash,
                LLCApiKey.revoked_at.is_(None),
            )
        )
        return result.scalar_one_or_none()


__all__ = ["ApiKeyService"]
