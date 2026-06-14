# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/transcriber/export/segments.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Segment-list assembly shared by export, KB, and AI analysis routes (#9863)."""

from transcriber.database import Database


async def build_segment_list(recording_id: int, db: Database) -> list[dict]:
    """Join segments with speaker display names and per-segment notes."""
    speakers = {s["id"]: s for s in await db.list_speakers(recording_id)}
    segments = await db.list_segments(recording_id)
    notes = await db.list_notes(recording_id)
    notes_by_seg: dict[int, list] = {}
    for n in notes:
        notes_by_seg.setdefault(n["segment_id"], []).append(n)
    result = []
    for seg in segments:
        spk = speakers.get(seg["speaker_id"], {})
        result.append(
            {
                **seg,
                "speaker_name": spk.get("display_name", "Unknown"),
                "notes": notes_by_seg.get(seg["id"], []),
            }
        )
    return result
