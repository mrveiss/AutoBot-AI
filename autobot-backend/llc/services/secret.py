# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC company-scoped secret service (GH#8217).

Provides set/get/revoke/list with Fernet encryption. The plaintext value
is never stored; only the Fernet-encrypted ciphertext persists in the DB.

Key derivation:
  1. Read LLC_SECRET_MASTER_KEY from env (required, no default).
  2. Derive a 32-byte company-specific key via HKDF-SHA256 with company_id as info.
  3. URL-safe-base64-encode → 44-char Fernet key.

Access control: SecretService methods accept company_id as a first-class
argument. API routes must verify that the calling agent's company_id matches
the requested company_id before invoking service methods.
"""

import base64
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.time_utils import now_utc
from llc.models.secret import LLCSecret

from .base import LLCServiceBase

logger = logging.getLogger(__name__)

_ENV_MASTER_KEY = "LLC_SECRET_MASTER_KEY"


class SecretNotFound(Exception):
    """Raised when the named secret does not exist or is revoked."""

    def __init__(self, company_id: str, name: str) -> None:
        self.company_id = company_id
        self.name = name
        super().__init__(f"Secret '{name}' not found for company {company_id}")


class SecretAccessDenied(Exception):
    """Raised when an agent attempts to access a secret outside its company."""

    def __init__(self, agent_company_id: str, secret_company_id: str) -> None:
        super().__init__(f"Agent company {agent_company_id} cannot access secrets of {secret_company_id}")


def _derive_fernet_key(master_key_bytes: bytes, company_id: str) -> Fernet:
    """Derive a Fernet instance whose key is company-specific.

    Uses HKDF-SHA256 to stretch master_key_bytes into 32 bytes, keyed to
    company_id so that each company has a distinct encryption key.
    The 32 output bytes are URL-safe-base64-encoded to satisfy Fernet's
    requirement of a 44-character key string.
    """
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=company_id.encode("utf-8"),
    )
    derived = hkdf.derive(master_key_bytes)
    fernet_key = base64.urlsafe_b64encode(derived)
    return Fernet(fernet_key)


class SecretService(LLCServiceBase):
    """Company-scoped secret management: encrypt, store, retrieve, revoke."""

    def _get_master_key(self) -> bytes:
        raw = os.environ.get(_ENV_MASTER_KEY)
        if not raw:
            raise RuntimeError(
                f"Environment variable {_ENV_MASTER_KEY} is not set. " "Secret operations require a master key."
            )
        return raw.encode("utf-8")

    def _fernet(self, company_id: str) -> Fernet:
        return _derive_fernet_key(self._get_master_key(), company_id)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def set(
        self,
        session: AsyncSession,
        company_id: str,
        name: str,
        value: str,
        actor: str,
    ) -> LLCSecret:
        """Encrypt and store a secret; auto-increment version on update.

        If a secret with this (company_id, name) already exists and is not
        revoked, its value and version are updated in-place. If it is
        revoked, it is reactivated with version=1 and the new value.

        Returns the persisted (and refreshed) LLCSecret row.
        """
        ciphertext = self._fernet(company_id).encrypt(value.encode("utf-8"))

        result = await session.execute(
            select(LLCSecret).where(
                LLCSecret.company_id == company_id,
                LLCSecret.name == name,
            )
        )
        existing = result.scalar_one_or_none()

        if existing is None:
            secret = LLCSecret(
                id=uuid.uuid4(),
                company_id=company_id,
                name=name,
                value=ciphertext,
                version=1,
                created_by_agent_id=actor,
            )
            session.add(secret)
        else:
            # Reactivate if previously revoked; always bump version
            existing.value = ciphertext
            existing.version = (existing.version if not existing.is_revoked else 0) + 1
            existing.revoked_at = None
            existing.updated_at = now_utc()
            secret = existing

        await session.flush()
        await session.refresh(secret)

        if self.activity_log:
            await self.activity_log.record(
                session=session,
                company_id=company_id,
                actor_id=actor,
                event_type="secret.set",
                entity_type="llc_secret",
                entity_id=str(secret.id),
                after={"name": name, "version": secret.version},
            )

        logger.info(
            "Secret '%s' set for company %s (version=%d, actor=%s)",
            name,
            company_id,
            secret.version,
            actor,
        )
        return secret

    async def get(
        self,
        session: AsyncSession,
        company_id: str,
        name: str,
    ) -> str:
        """Return the decrypted plaintext for the named secret.

        Raises SecretNotFound if the secret does not exist or is revoked.
        """
        secret = await self._fetch_active(session, company_id, name)
        return self._fernet(company_id).decrypt(secret.value).decode("utf-8")

    async def revoke(
        self,
        session: AsyncSession,
        company_id: str,
        name: str,
        actor: str,
    ) -> None:
        """Soft-delete the secret; get() will raise SecretNotFound after this."""
        secret = await self._fetch_active(session, company_id, name)
        secret.revoked_at = now_utc()
        secret.updated_at = now_utc()
        await session.flush()

        if self.activity_log:
            await self.activity_log.record(
                session=session,
                company_id=company_id,
                actor_id=actor,
                event_type="secret.revoked",
                entity_type="llc_secret",
                entity_id=str(secret.id),
                after={"name": name, "revoked_at": secret.revoked_at.isoformat()},
            )

        logger.info(
            "Secret '%s' revoked for company %s (actor=%s)",
            name,
            company_id,
            actor,
        )

    async def list(
        self,
        session: AsyncSession,
        company_id: str,
        include_revoked: bool = False,
    ) -> List[dict]:
        """Return names and versions only — never plaintext values.

        By default only active (non-revoked) secrets are returned.
        Pass include_revoked=True to include revoked secrets in the listing.
        """
        stmt = select(LLCSecret).where(LLCSecret.company_id == company_id)
        if not include_revoked:
            stmt = stmt.where(LLCSecret.revoked_at.is_(None))

        result = await session.execute(stmt.order_by(LLCSecret.name))
        rows = result.scalars().all()

        return [
            {
                "name": r.name,
                "version": r.version,
                "created_by_agent_id": r.created_by_agent_id,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
                "revoked_at": r.revoked_at,
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_active(
        self,
        session: AsyncSession,
        company_id: str,
        name: str,
    ) -> LLCSecret:
        """Return the active (non-revoked) secret or raise SecretNotFound."""
        result = await session.execute(
            select(LLCSecret).where(
                LLCSecret.company_id == company_id,
                LLCSecret.name == name,
                LLCSecret.revoked_at.is_(None),
            )
        )
        secret = result.scalar_one_or_none()
        if secret is None:
            raise SecretNotFound(company_id=company_id, name=name)
        return secret
