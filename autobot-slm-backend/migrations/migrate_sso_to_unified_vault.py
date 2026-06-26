# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Migration: move SSO secrets from SystemSecret table to the unified-secrets System vault (#10153).

This is a ONE-TIME, IDEMPOTENT data migration.  Safe to run multiple times.

For each SSO provider:
1. Skip fields that already have a ``{field}_vault_id`` in the config
   (already migrated — idempotency guard).
2. Read the current SystemSecret entry (legacy encrypted store).
3. Decrypt and write to the unified-secrets vault via
   ``SSOSecretsManager.migrate_to_vault``.
4. Update the provider's config JSONB with the vault UUID.
5. Leave the SystemSecret row in place (the fallback read path still
   works during rollout), but log that it can be pruned later.

Prerequisites:
    - AUTOBOT_SECRETS_ROOT_KEY must be set (backend's root key).
    - SLM_SERVICE_KEY / SLM_SERVICE_ID must be configured (service auth).
    - SLM_AUTHORITY_BASE_URL must point to a running autobot-backend.
    - SLM_ENCRYPTION_KEY / SLM_SECRET_KEY for legacy decryption.

Run:
    python -m migrations.migrate_sso_to_unified_vault

or with an explicit DB URL:
    python -m migrations.migrate_sso_to_unified_vault postgresql+asyncpg://...
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any

logger = logging.getLogger(__name__)


def _require_env() -> None:
    """Abort with a clear message when required env vars are missing."""
    missing = []
    if not os.getenv("SLM_SERVICE_KEY") and not os.getenv("SLM_SERVICE_ID"):
        missing.append("SLM_SERVICE_KEY + SLM_SERVICE_ID (service auth to backend)")
    if not any(os.getenv(v) for v in ("SLM_ENCRYPTION_KEY", "SLM_SECRET_KEY")):
        missing.append("SLM_ENCRYPTION_KEY or SLM_SECRET_KEY (legacy decryption)")
    if missing:
        msg = "Migration aborted — missing configuration:\n" + "\n".join(f"  - {m}" for m in missing)
        raise RuntimeError(msg)


async def _run(db_url: str) -> None:
    """Async migration body."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_async_engine(db_url, echo=False)
    async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session_maker() as session:
        from user_management.models.sso import SSOProvider
        from user_management.services.sso_secrets import SSOSecretsManager

        result = await session.execute(select(SSOProvider))
        providers = list(result.scalars().all())
        logger.info("Found %d SSO providers to process", len(providers))

        migrated = 0
        skipped = 0
        failed = 0

        for provider in providers:
            config: dict[str, Any] = provider.config or {}
            mgr = SSOSecretsManager(session)
            try:
                updated_config = await mgr.migrate_to_vault(provider.id, config)
            except Exception as exc:
                logger.error(
                    "Migration failed for provider %s (%s): %s — skipping",
                    provider.id,
                    provider.name,
                    type(exc).__name__,
                )
                failed += 1
                continue

            if updated_config == config:
                logger.info("Provider %s (%s): already migrated — skipping", provider.id, provider.name)
                skipped += 1
                continue

            provider.config = updated_config
            await session.flush()
            migrated += 1
            logger.info("Provider %s (%s): migrated to vault", provider.id, provider.name)

        await session.commit()

    await engine.dispose()
    logger.info("Migration complete: migrated=%d skipped=%d failed=%d", migrated, skipped, failed)
    if failed:
        logger.warning("%d providers failed; re-run after fixing the above errors", failed)


def migrate(db_url: str) -> None:
    """Synchronous entry point (compatible with existing runner infrastructure)."""
    _require_env()
    asyncio.run(_run(db_url))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    _require_env()

    if len(sys.argv) > 1:
        _db_url = sys.argv[1]
    else:
        try:
            from migrations.runner import get_db_url

            _db_url = get_db_url()
        except ImportError:
            from config import settings

            _db_url = settings.autobot_users_database_url

    logger.info("Starting SSO → unified-vault migration (db=%s)", _db_url.split("@")[-1])
    migrate(_db_url)
