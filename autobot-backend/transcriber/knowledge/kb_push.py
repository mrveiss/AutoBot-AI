# autobot-backend/transcriber/knowledge/kb_push.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Manual Knowledge Base push — formats transcript segments as KB documents."""
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


def _fmt_ts(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _get_indexer():
    from knowledge.documents import DocIndexerService
    return DocIndexerService()


async def push_to_kb(
    recording_id: int,
    recording_filename: str,
    segments: list[dict],
    collection_id: str,
    pushed_by: str,
) -> dict:
    """Push all segments as documents to the AutoBot Knowledge Base.

    Each segment becomes one document: '[Speaker, HH:MM:SS] text'
    Returns dict with 'indexed' count.
    """
    documents = [
        {
            "content": f"[{seg['speaker_name']}, {_fmt_ts(seg['start'])}] {seg['text']}",
            "metadata": {
                "source": "transcriber",
                "recording_id": recording_id,
                "recording_filename": recording_filename,
                "speaker": seg["speaker_name"],
                "start_time": seg["start"],
                "end_time": seg["end"],
            },
        }
        for seg in segments
        if seg["text"].strip()
    ]
    indexer = _get_indexer()
    result = await indexer.add_documents(documents, collection_id=collection_id)
    logger.info(
        "KB push: recording=%s collection=%s docs=%s by=%s",
        recording_id, collection_id, len(documents), pushed_by,
    )
    return result
