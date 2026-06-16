# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Transcriber Celery Tasks (GH#10128)

Async Celery task that drives the transcription pipeline for each uploaded
recording.  The task body is synchronous (Celery requirement); all async
work runs inside ``asyncio.run()``, matching the pattern of
``tasks/mobile_device_tasks.py``.
"""

import asyncio

from autobot_shared.logging_manager import get_logger
from celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(
    name="tasks.transcribe_recording",
    acks_late=True,
    max_retries=3,
)
def transcribe_recording(recording_id: int) -> dict:
    """Enqueue-and-forget task: run the transcription pipeline for *recording_id*.

    Args:
        recording_id: Primary key of the recording row to process.

    Returns:
        Dict returned by ``TranscriberOrchestrator.process_recording``.
    """
    logger.info("Celery: transcribe_recording started for recording_id=%d", recording_id)
    result = asyncio.run(_run_pipeline(recording_id))
    logger.info("Celery: transcribe_recording done for recording_id=%d", recording_id)
    return result


async def _run_pipeline(recording_id: int) -> dict:
    """Async wrapper so the orchestrator can use await internally."""
    from transcriber.orchestrator import get_transcriber_orchestrator

    orchestrator = get_transcriber_orchestrator()
    return await orchestrator.process_recording(recording_id)
