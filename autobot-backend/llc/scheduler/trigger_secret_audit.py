# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Celery-beat audit: propose a human review of plaintext webhook secrets (#19759, #17038).

Finds triggers whose stored HMAC secret is plaintext and files one pending approval
naming their ids. It never rewrites, re-encrypts or deletes a secret: a person decides,
and acting on an approved proposal is a separate piece of work.
"""

import asyncio

from celery import shared_task

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from services.trigger_secrets import propose_plaintext_secret_rewrite
from user_management.database import get_async_session_factory
from utils.celery_reliability import (
    CELERY_MAX_RETRIES,
    CELERY_RETRY_BACKOFF_MAX,
    CELERY_TRANSIENT_ERRORS,
    DeadLetterTask,
)

logger = get_logger(__name__)


@shared_task(
    name="llc.scheduler.trigger_secret_audit.run_trigger_secret_audit",
    bind=True,
    base=DeadLetterTask,
    autoretry_for=CELERY_TRANSIENT_ERRORS,
    retry_backoff=True,
    retry_jitter=True,
    retry_backoff_max=CELERY_RETRY_BACKOFF_MAX,
    max_retries=CELERY_MAX_RETRIES,
)
def run_trigger_secret_audit(self: object) -> dict:  # type: ignore[type-arg]
    """Celery entry point. Returns whether a proposal was raised."""
    return asyncio.run(_async_audit())


async def _async_audit() -> dict:
    """Propose once for the current plaintext set, publishing only after the commit."""
    redis = get_redis_client(database="workflows")
    factory = get_async_session_factory()
    async with factory() as session:
        approval = await propose_plaintext_secret_rewrite(session, redis)
        await session.commit()
        if approval is not None:
            await _publish(approval)
    return {"proposed": approval is not None}


async def _publish(approval) -> None:
    """Announce a committed proposal; a failure is logged with its id, not swallowed."""
    from llc.services.approval import ApprovalService

    try:
        await ApprovalService().publish_requested(approval)
    except Exception as exc:
        logger.warning("Publishing trigger-secret proposal %s failed: %s", approval.id, type(exc).__name__)


__all__ = ["run_trigger_secret_audit"]
