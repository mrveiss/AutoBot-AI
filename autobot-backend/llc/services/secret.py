# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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

import logging
import os
import uuid
from typing import List, Optional

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.legacy_secret_keys import derive_llc_company_fernet
from autobot_shared.time_utils import now_utc
from llc.models.secret import LLCSecret
from services.llc_secrets_read import llc_unified_read_enabled, read_imported_llc_secret_in_session

from .base import LLCServiceBase

logger = logging.getLogger(__name__)

_ENV_MASTER_KEY = "LLC_SECRET_MASTER_KEY"

# Backward-compatible alias: the per-company HKDF+Fernet derivation now lives in
# autobot_shared.legacy_secret_keys (#10088 / Task 1.3 + Task 4) so migration
# importers can reuse it without pulling in llc/services/__init__.py's eager
# import of every concrete LLC service. Existing tests import this name
# directly from this module, so it stays a re-export rather than moving away.
_derive_fernet_key = derive_llc_company_fernet


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

        # Logs secret *name* (metadata key) and audit fields only — the encrypted value is never logged.
        logger.info(  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure  # noqa: E501
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

        Dual-read (#10088 / Task 4): when ``AUTOBOT_SECRETS_LLC_UNIFIED_READ`` is
        enabled, tries the unified envelope store first (see
        ``services.llc_secrets_read``) — only for the row ``_fetch_active`` just
        proved exists and is not revoked, so a revoked/absent secret can never
        stale-resurrect through the unified copy. Falls back to the legacy
        per-company Fernet decrypt on any miss, disabled flag, or unusable root key.
        """
        secret = await self._fetch_active(session, company_id, name)
        if llc_unified_read_enabled():
            unified = await self._unified_get(session, secret, company_id)
            if unified is not None:
                return unified
        return self._fernet(company_id).decrypt(secret.value).decode("utf-8")

    async def _unified_get(self, session: AsyncSession, secret: LLCSecret, company_id: str) -> Optional[str]:
        """Best-effort unified-store read for an already-resolved active secret row."""
        from autobot_shared.secrets_envelope import load_root_key

        try:
            root_key = load_root_key()
        except RuntimeError:
            return None
        return await read_imported_llc_secret_in_session(
            session, source_id=str(secret.id), company_id=company_id, root_key=root_key
        )

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

        # Logs secret *name* (metadata key) and audit fields only — the encrypted value is never logged.
        logger.info(  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure  # noqa: E501
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
