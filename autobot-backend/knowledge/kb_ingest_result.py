# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What ``kb.add_document`` actually did, reported honestly to the caller (#17530)."""

from autobot_shared.logging_manager import get_logger
from knowledge.ingestion_visibility import stamp_if_document
from knowledge.upload_rejections import UploadRejection, UploadRejectionCode

logger = get_logger(__name__)


async def ingest_in_kb(kb, content: str, metadata: dict) -> dict:
    """Store *content* under *metadata* through the one ingest path (#18407) and return its result.

    An admin file upload, the only caller writing ``type: file``, is a document: SYSTEM unless something
    already claims it (#16693). ``success``, ``duplicate`` and ``partial`` come back; an ``error``, a
    ``timeout`` or any other status with nothing stored is rejected rather than reported as stored.
    """
    if metadata.get("type") == "file":
        stamp_if_document(metadata)
    result = await kb.add_document(content, metadata)
    status = result.get("status")
    if status == "timeout":
        raise UploadRejection(
            UploadRejectionCode.INGEST_TIMEOUT, "Storing the document timed out; nothing was saved.", status_code=504
        )
    if status not in ("success", "duplicate", "partial") or not result.get("fact_id"):
        logger.warning("Document ingest failed: status=%r message=%r", status, result.get("message"))
        raise UploadRejection(
            UploadRejectionCode.INGEST_FAILED, "The document could not be stored; nothing was saved.", status_code=500
        )
    if status == "partial":
        logger.warning(
            "Partial ingest: %s of %s chunks stored", result.get("chunks_stored"), result.get("chunks_total")
        )
    return result


def partial_note(result: dict) -> dict:
    """Response fields saying how much of a ``partial`` ingest was stored; empty for a complete one."""
    if result.get("status") != "partial":
        return {}
    stored, total = result.get("chunks_stored"), result.get("chunks_total")
    return {
        "status": "partial",
        "chunks_stored": stored,
        "chunks_total": total,
        "message": f"Only {stored} of {total} chunks were stored before the ingest budget ran out; upload to resume.",
    }
