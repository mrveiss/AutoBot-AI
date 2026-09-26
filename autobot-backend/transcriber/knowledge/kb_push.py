# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/transcriber/knowledge/kb_push.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Manual Knowledge Base push — lands transcript segments in the Knowledge Base.

The Knowledge Base write API is ``KnowledgeBase.add_document`` plus, for
collection membership, ``KnowledgeBase.add_facts_to_collection`` — both methods
of the one composed singleton (``knowledge/_composed.py``). This module used to
call ``DocIndexerService.add_documents(documents, collection_id=...)``, which is
neither: ``DocIndexerService`` indexes *files* off disk and has never had an
``add_documents`` method or a ``collection_id`` parameter (#17022).
"""

from autobot_shared.logging_manager import get_logger
from transcriber.util import format_timestamp as _fmt_ts

logger = get_logger(__name__)


def build_segment_documents(
    recording_id: int,
    recording_filename: str,
    segments: list[dict],
    pushed_by: str,
) -> list[dict]:
    """One document per non-empty segment, each attributable to its recording.

    ``source_type``/``source`` follow the single-segment push in
    ``api/transcripts.py``, so a segment pushed from either entry point is
    recognisable as transcript material and traceable back to the recording it
    was spoken in (#17527).
    """
    return [
        {
            "content": f"[{seg['speaker_name']}, {_fmt_ts(seg['start'])}] {seg['text']}",
            "metadata": {
                "source_type": "transcript",
                "source": f"recording:{recording_id}",
                "recording_id": recording_id,
                "recording_filename": recording_filename,
                "speaker": seg["speaker_name"],
                "start_time": seg["start"],
                "end_time": seg["end"],
                "pushed_by": pushed_by,
            },
        }
        for seg in segments
        if seg["text"].strip()
    ]


async def _store_documents(kb, documents: list[dict]) -> tuple[list[str], dict]:
    """Store each document, returning the resulting fact ids and a status tally."""
    fact_ids: list[str] = []
    tally = {"indexed": 0, "duplicate": 0, "failed": 0}

    for document in documents:
        result = await kb.add_document(content=document["content"], metadata=document["metadata"])
        status = result.get("status")

        if status not in ("success", "duplicate"):
            tally["failed"] += 1
            logger.warning("KB push: segment rejected (%s): %s", status, result.get("message"))
            continue

        tally["indexed" if status == "success" else "duplicate"] += 1
        # A duplicate already exists in the Knowledge Base under the returned id and
        # still belongs in the collection: dropping it would mean a second push of
        # the same recording silently routed fewer segments than the first.
        fact_id = result.get("fact_id")
        if fact_id:
            fact_ids.append(fact_id)

    return fact_ids, tally


async def _route_to_collection(kb, collection_id: str, fact_ids: list[str]) -> dict:
    """Join the stored facts to the requested collection.

    ``add_document`` takes no collection parameter, so the collection this push
    was asked for is honoured by a second call. A collection is a real store with
    its own membership and a not-found path, not a metadata tag.
    """
    if not collection_id or not fact_ids:
        return {"added": 0, "already_present": 0, "missing": 0}

    result = await kb.add_facts_to_collection(collection_id, fact_ids)
    if not result.get("success"):
        logger.warning(
            "KB push: collection routing failed for %d facts: %s",
            len(fact_ids),
            result.get("message"),
        )
        return {"added": 0, "already_present": 0, "missing": len(fact_ids)}

    return {
        "added": result.get("added_count", 0),
        "already_present": result.get("already_in_collection", 0),
        "missing": len(result.get("not_found") or ()),
    }


async def push_to_kb(
    recording_id: int,
    recording_filename: str,
    segments: list[dict],
    collection_id: str,
    pushed_by: str,
) -> dict:
    """Push every non-empty segment of a recording into the Knowledge Base.

    Each segment becomes one document: '[Speaker, HH:MM:SS] text'.

    Returns the real outcome of the write — ``indexed``, ``duplicate`` and
    ``failed`` sum to ``segments`` — so a caller cannot mistake a rejected push
    for a stored one.
    """
    from knowledge import get_knowledge_base

    documents = build_segment_documents(recording_id, recording_filename, segments, pushed_by)

    # get_knowledge_base is a coroutine function. Calling it without await yields a
    # coroutine, and every attribute access on that coroutine raises AttributeError
    # -- which is how the watch folder ingested nothing for months while only
    # incrementing an error counter (#13551). Pinned by a test that drops the await.
    kb = await get_knowledge_base()

    fact_ids, tally = await _store_documents(kb, documents)
    collection = await _route_to_collection(kb, collection_id, fact_ids)

    logger.info(
        "KB push: recording=%s collection=%s segments=%d indexed=%d duplicate=%d failed=%d "
        "collection_added=%d by=%s",
        recording_id,
        collection_id,
        len(documents),
        tally["indexed"],
        tally["duplicate"],
        tally["failed"],
        collection["added"],
        pushed_by,
    )

    return {**tally, "segments": len(documents), "fact_ids": fact_ids, "collection": collection}
