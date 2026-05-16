# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Background scheduler for LLM API key expiry rotation (#6590).

Runs hourly (configurable via AUTOBOT_LLM_KEY_ROTATION_INTERVAL_MINUTES)
and auto-revokes keys whose expires_at has passed.
"""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from services.llm_api_key_service import get_llm_api_key_service

logger = get_logger(__name__)

_ROTATION_INTERVAL_MINUTES = int(config.llm_key_rotation_interval_minutes)


class LLMKeyRotationScheduler:
    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()

    async def start(self) -> None:
        self._scheduler.add_job(
            self._run_rotation,
            "interval",
            minutes=_ROTATION_INTERVAL_MINUTES,
            id="llm_key_rotation",
            replace_existing=True,
        )
        self._scheduler.start()
        logger.info("LLM key rotation scheduler started (interval=%dm)", _ROTATION_INTERVAL_MINUTES)

    async def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("LLM key rotation scheduler stopped")

    async def _run_rotation(self) -> None:
        try:
            svc = get_llm_api_key_service()
            count = await svc.rotate_expired_keys()
            if count:
                logger.info("LLM key rotation: revoked %d expired key(s)", count)
        except Exception as exc:
            logger.error("LLM key rotation job failed: %s", exc)


_scheduler_instance: LLMKeyRotationScheduler | None = None


def get_llm_key_rotation_scheduler() -> LLMKeyRotationScheduler:
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = LLMKeyRotationScheduler()
    return _scheduler_instance
