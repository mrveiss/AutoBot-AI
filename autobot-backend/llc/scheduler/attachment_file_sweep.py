# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Celery-beat sweep: finish attachment file work the request path could not (#19756).

Two passes, in this order:

1. **Retry owed removals.** Every row in the attachment deletion outbox is a file whose
   attachment row a caller already deleted. The file is unlinked and the entry removed; a
   failure keeps the entry, with its error, for a later tick, and after repeated failures the
   entry is marked stuck, skipped and counted in the result. This decides nothing new about
   what is deleted (#17038) -- it completes a delete somebody asked for.
2. **Settle stale staging files.** A staged file whose row was committed is published to its
   final path; one with no row, older than ``AUTOBOT_LLC_ATTACHMENT_STAGING_MAX_AGE_SECONDS``,
   is moved to ``.staging/quarantine``. Nothing is deleted. Only the staging directory is read.
"""

import asyncio

from celery import shared_task

from autobot_shared.logging_manager import get_logger
from llc.services.attachment_service import AttachmentService
from user_management.database import get_async_session_factory
from utils.celery_reliability import (
    CELERY_MAX_RETRIES,
    CELERY_RETRY_BACKOFF_MAX,
    CELERY_TRANSIENT_ERRORS,
    DeadLetterTask,
)

logger = get_logger(__name__)


@shared_task(
    name="llc.scheduler.attachment_file_sweep.run_attachment_file_sweep",
    bind=True,
    base=DeadLetterTask,
    autoretry_for=CELERY_TRANSIENT_ERRORS,
    retry_backoff=True,
    retry_jitter=True,
    retry_backoff_max=CELERY_RETRY_BACKOFF_MAX,
    max_retries=CELERY_MAX_RETRIES,
)
def run_attachment_file_sweep(self: object) -> dict:  # type: ignore[type-arg]
    """Celery entry point. Returns the counts so a run is legible from the result."""
    return asyncio.run(_async_sweep())


async def _async_sweep() -> dict:
    service = AttachmentService()
    factory = get_async_session_factory()
    async with factory() as session:
        outbox = await service.drain_removals(session)
        staging = await service.sweep_staging(session)
    # Every number is reported, zeros included: a sweep that found nothing and one that did
    # not run must not look the same in the logs.
    logger.info("#19756: attachment file sweep outbox %s; staging %s", outbox, staging)
    if outbox["other_root"]:
        logger.warning(
            "#19756: %d attachment file removal(s) belong to another node's storage and were not drained here",
            outbox["other_root"],
        )
    if outbox["stuck"]:
        logger.error("#19756: %d attachment file removal(s) are stuck and need a person", outbox["stuck"])
    return {**outbox, **staging}


__all__ = ["run_attachment_file_sweep"]
