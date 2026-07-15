# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Periodic sweep reconciling unified credential copies against canonical SQLite (#10337).

Bounds the revoke-resurrection window of the connector-store cutover (#10088 Task 3c-2): a
swallowed best-effort mirror delete/rotate (#10334) leaves the unified copy out of sync, which
read-first would serve. This Celery task runs the reconciliation sweep on a schedule.
"""

import asyncio
import logging

from celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.reconcile_credentials")
def reconcile_credentials() -> dict:
    """Reconcile mirrored unified credential copies against the canonical SQLite store."""
    return asyncio.run(_run())


async def _run() -> dict:
    from autobot_shared.secrets_envelope import load_root_key
    from services.credential_reconcile import reconcile_connector_credentials
    from services.secrets_service import get_secrets_service
    from user_management.database import get_async_session_factory

    try:
        root_key = load_root_key()
    except RuntimeError:
        logger.info("Credential reconcile skipped — unified secrets root key not configured")
        return {"skipped": "no_root_key"}

    svc = get_secrets_service()
    async with get_async_session_factory()() as session:
        report = await reconcile_connector_credentials(
            session, sqlite_path=svc.db_path, fernet=svc.cipher, root_key=root_key
        )
        await session.commit()

    result = {
        "checked": report.checked,
        "deleted": report.deleted,
        "resynced": report.resynced,
        "ok": report.ok,
        "failed": len(report.failed),
        "aborted": report.aborted,
    }
    logger.info("Credential reconcile: %s", result)
    return result
