# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Celery-beat sweep: finish attachment file work the request path could not (#19756).

Two passes, in this order:

1. **Retry owed removals.** Every row in the attachment deletion outbox is a file whose
   attachment row a caller already deleted. The file is unlinked and the entry removed; a
   failure keeps the entry, with its error, for the next tick. This decides nothing new about
   what is deleted (#17038) -- it completes a delete somebody asked for.
2. **Settle stale staging files.** A staged file whose row was committed is published to its
   final path; one with no row is the remains of an upload that never committed and is
   unlinked. Only the staging directory is read, and only files older than
   ``AUTOBOT_LLC_ATTACHMENT_STAGING_MAX_AGE_SECONDS``.
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
        removed = await service.drain_removals(session)
        staging = await service.sweep_staging(session)
    # Every number is reported, zeros included: a sweep that found nothing and one that did
    # not run must not look the same in the logs.
    logger.info("#19756: attachment file sweep removed %d file(s); staging %s", removed, staging)
    return {"removed": removed, **staging}


__all__ = ["run_attachment_file_sweep"]
