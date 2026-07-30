# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Migration: import ``system_secrets`` rows into the unified-secrets System vault (#10088 Task 6a).

This is a ONE-TIME, IDEMPOTENT data import. Safe to run multiple times — a
second run finds every eligible key already present in the vault (by name)
and reports it skipped.

Not part of the schema ``migrations.runner`` list (same as the SSO vault
migration, ``migrate_sso_to_unified_vault.py``) — it does not change any
table, it only copies plaintext values into the (separate-service) vault.

Skips two categories of key (see ``services.system_secrets_vault.is_migratable``):
  - ``autobot_internal_api_key`` — the auth-bootstrap credential that gates
    access to the vault itself; migrating it is a confused-deputy cycle.
  - ``sso:provider:*`` — already migrated by the dedicated #10153 path.

The legacy ``system_secrets`` row is NEVER deleted or modified by this
script — ``api/secrets.py`` (today's SLM Secrets UI) stays the live write
path until the owner decides how the two Secrets UIs unify (#10088 Task 6c).

Prerequisites:
    - AUTOBOT_INTERNAL_API_KEY (or SLM_SERVICE_KEY/SLM_SERVICE_ID) — vault auth.
    - SLM_AUTHORITY_BASE_URL must point to a running autobot-backend.
    - SLM_ENCRYPTION_KEY / SLM_SECRET_KEY for legacy decryption.

Run:
    python -m migrations.migrate_system_secrets_to_vault

or with an explicit DB URL:
    python -m migrations.migrate_system_secrets_to_vault postgresql+asyncpg://...
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

logger = logging.getLogger(__name__)


def _require_env() -> None:
    """Abort with a clear message when required env vars are missing."""
    missing = []
    if not os.getenv("AUTOBOT_INTERNAL_API_KEY") and not (os.getenv("SLM_SERVICE_KEY") and os.getenv("SLM_SERVICE_ID")):
        missing.append("AUTOBOT_INTERNAL_API_KEY (or SLM_SERVICE_KEY + SLM_SERVICE_ID) — vault auth")
    if not any(os.getenv(v) for v in ("SLM_ENCRYPTION_KEY", "SLM_SECRET_KEY")):
        missing.append("SLM_ENCRYPTION_KEY or SLM_SECRET_KEY (legacy decryption)")
    if missing:
        msg = "Migration aborted — missing configuration:\n" + "\n".join(f"  - {m}" for m in missing)
        raise RuntimeError(msg)


def _asyncpg_url(db_url: str) -> str:
    """Normalize a sync ``postgresql://`` URL to the asyncpg driver for the async engine."""
    if db_url.startswith("postgresql://"):
        return db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return db_url


async def _run(db_url: str) -> None:
    """Async migration body."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_async_engine(_asyncpg_url(db_url), echo=False)
    async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session_maker() as session:
        from models.database import SystemSecret
        from services.system_secrets_vault import is_migratable, migrate_key_to_vault

        result = await session.execute(select(SystemSecret.key))
        keys = [row[0] for row in result.all()]
        logger.info("Found %d system_secrets rows to consider", len(keys))

        migrated = 0
        skipped = 0
        ineligible = 0
        failed = 0

        for key in keys:
            if not is_migratable(key):
                ineligible += 1
                logger.info("key=%s: ineligible (irreducible or SSO-managed) — skipping", key)
                continue
            try:
                did_migrate = await migrate_key_to_vault(session, key)
            except Exception as exc:
                logger.error("key=%s: migration failed: %s", key, type(exc).__name__)
                failed += 1
                continue
            if did_migrate:
                migrated += 1
            else:
                skipped += 1

    await engine.dispose()
    logger.info(
        "Migration complete: migrated=%d skipped=%d ineligible=%d failed=%d",
        migrated,
        skipped,
        ineligible,
        failed,
    )
    if failed:
        logger.warning("%d keys failed; re-run after fixing the above errors", failed)


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

            _db_url = settings.database_url

    logger.info("Starting system_secrets -> unified-vault import (db=%s)", _db_url.split("@")[-1])
    migrate(_db_url)
