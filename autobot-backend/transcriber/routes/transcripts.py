# autobot-backend/transcriber/routes/transcripts.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Transcript routes: segments, speakers, notes."""

from fastapi import APIRouter, Depends, HTTPException, Response, Request
from transcriber.database import Database
from transcriber.deps import get_db
from transcriber.models import (
    NoteCreate,
    NoteOut,
    NoteUpdate,
    SegmentOut,
    SegmentUpdate,
    SpeakerOut,
    SpeakerUpdate,
    SpeakerMerge,
    TranscriptOut,
    RecordingOut,
)

router = APIRouter(tags=["transcriber-transcripts"])

_DEFAULT_USER = "default"


def _user_id(request: Request) -> str:
    user = getattr(request.state, "user", None)
    return user.id if user else _DEFAULT_USER


async def _require_recording_owner(recording_id: int, user_id: str, db: Database) -> None:
    """Raise 403 if user does not own the project that contains this recording."""
    recording = await db.get_recording(recording_id)
    if not recording:
        raise HTTPException(404, "Recording not found")
    project = await db.get_project(recording["project_id"])
    if not project or project["user_id"] != user_id:
        raise HTTPException(403, "Not authorized")


@router.get("/recordings/{recording_id}/transcript", response_model=TranscriptOut)
async def get_transcript(recording_id: int, request: Request, db: Database = Depends(get_db)):
    await _require_recording_owner(recording_id, _user_id(request), db)
    rec = await db.get_recording(recording_id)
    speakers = await db.list_speakers(recording_id)
    segments = await db.list_segments(recording_id)
    return TranscriptOut(
        recording=RecordingOut(**rec),
        speakers=[SpeakerOut(**s) for s in speakers],
        segments=[SegmentOut(**s) for s in segments],
    )


@router.patch("/segments/{segment_id}", response_model=SegmentOut)
async def update_segment(segment_id: int, body: SegmentUpdate, request: Request, db: Database = Depends(get_db)):
    segment = await db.get_segment(segment_id)
    if not segment:
        raise HTTPException(404, "Segment not found")
    await _require_recording_owner(segment["recording_id"], _user_id(request), db)
    await db.update_segment_text(segment_id, body.text)
    updated = await db.get_segment(segment_id)
    return SegmentOut(**updated)


@router.patch("/speakers/{speaker_id}", response_model=SpeakerOut)
async def update_speaker(speaker_id: int, body: SpeakerUpdate, request: Request, db: Database = Depends(get_db)):
    speaker = await db.get_speaker(speaker_id)
    if not speaker:
        raise HTTPException(404, "Speaker not found")
    await _require_recording_owner(speaker["recording_id"], _user_id(request), db)
    await db.update_speaker(speaker_id, body.display_name)
    updated = await db.get_speaker(speaker_id)
    return SpeakerOut(**updated)


@router.post("/speakers/merge", status_code=200)
async def merge_speakers(body: SpeakerMerge, request: Request, db: Database = Depends(get_db)):
    """Merge source speaker into target speaker. All segments from source will be reassigned to target, then source is deleted."""
    source = await db.get_speaker(body.source_speaker_id)
    if not source:
        raise HTTPException(404, f"no speaker with id={body.source_speaker_id}")
    await _require_recording_owner(source["recording_id"], _user_id(request), db)
    try:
        await db.merge_speakers(body.source_speaker_id, body.target_speaker_id)
        return {"success": True, "message": f"Speaker {body.source_speaker_id} merged into {body.target_speaker_id}"}
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/segments/{segment_id}/notes", response_model=NoteOut, status_code=201)
async def create_note(segment_id: int, body: NoteCreate, request: Request, db: Database = Depends(get_db)):
    segment = await db.get_segment(segment_id)
    if not segment:
        raise HTTPException(404, "Segment not found")
    recording_id = segment["recording_id"]
    await _require_recording_owner(recording_id, _user_id(request), db)
    nid = await db.create_note(segment_id, recording_id, body.content)
    note = await db.get_note(nid)
    return NoteOut(**note)


@router.patch("/notes/{note_id}", response_model=NoteOut)
async def update_note(note_id: int, body: NoteUpdate, request: Request, db: Database = Depends(get_db)):
    note = await db.get_note(note_id)
    if not note:
        raise HTTPException(404, "Note not found")
    await _require_recording_owner(note["recording_id"], _user_id(request), db)
    await db.update_note(note_id, body.content)
    return NoteOut(**await db.get_note(note_id))


@router.delete("/notes/{note_id}", status_code=204)
async def delete_note(note_id: int, request: Request, db: Database = Depends(get_db)):
    note = await db.get_note(note_id)
    if not note:
        raise HTTPException(404, "Note not found")
    await _require_recording_owner(note["recording_id"], _user_id(request), db)
    await db.delete_note(note_id)
    return Response(status_code=204)
