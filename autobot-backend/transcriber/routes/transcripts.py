# autobot-backend/transcriber/routes/transcripts.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Transcript routes: segments, speakers, notes."""
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from transcriber.database import Database
from transcriber.deps import get_db
from transcriber.models import (
    NoteCreate, NoteOut, NoteUpdate, SegmentOut, SegmentUpdate,
    SpeakerOut, SpeakerUpdate, TranscriptOut, RecordingOut,
)

router = APIRouter(tags=["transcriber-transcripts"])


def _user_id(request: Request) -> str:
    user = getattr(request.state, "user", None)
    return user.id if user else "default"


@router.get("/recordings/{recording_id}/transcript", response_model=TranscriptOut)
async def get_transcript(recording_id: int, request: Request, db: Database = Depends(get_db)):
    rec = await db.get_recording(recording_id)
    if not rec or rec["user_id"] != _user_id(request):
        raise HTTPException(404, "Recording not found")
    speakers = await db.list_speakers(recording_id)
    segments = await db.list_segments(recording_id)
    return TranscriptOut(
        recording=RecordingOut(**rec),
        speakers=[SpeakerOut(**s) for s in speakers],
        segments=[SegmentOut(**s) for s in segments],
    )


@router.patch("/segments/{segment_id}", response_model=SegmentOut)
async def update_segment(segment_id: int, body: SegmentUpdate, request: Request, db: Database = Depends(get_db)):
    cur = await db._db().execute("SELECT recording_id FROM segments WHERE id=?", (segment_id,))
    row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Segment not found")
    recording_id = row[0]
    rec = await db.get_recording(recording_id)
    if not rec or rec["user_id"] != _user_id(request):
        raise HTTPException(404, "Segment not found")
    await db.update_segment_text(segment_id, body.text)
    cur2 = await db._db().execute("SELECT * FROM segments WHERE id=?", (segment_id,))
    updated = await cur2.fetchone()
    return SegmentOut(**dict(updated))


@router.patch("/speakers/{speaker_id}", response_model=SpeakerOut)
async def update_speaker(speaker_id: int, body: SpeakerUpdate, request: Request, db: Database = Depends(get_db)):
    cur = await db._db().execute("SELECT recording_id FROM speakers WHERE id=?", (speaker_id,))
    row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Speaker not found")
    recording_id = row[0]
    rec = await db.get_recording(recording_id)
    if not rec or rec["user_id"] != _user_id(request):
        raise HTTPException(404, "Speaker not found")
    await db.update_speaker(speaker_id, body.display_name)
    cur2 = await db._db().execute("SELECT * FROM speakers WHERE id=?", (speaker_id,))
    updated = await cur2.fetchone()
    return SpeakerOut(**dict(updated))


@router.post("/segments/{segment_id}/notes", response_model=NoteOut, status_code=201)
async def create_note(segment_id: int, body: NoteCreate, request: Request, db: Database = Depends(get_db)):
    seg_cur = await db._db().execute("SELECT recording_id FROM segments WHERE id=?", (segment_id,))
    seg_row = await seg_cur.fetchone()
    if not seg_row:
        raise HTTPException(404, "Segment not found")
    recording_id = seg_row[0]
    rec = await db.get_recording(recording_id)
    if not rec or rec["user_id"] != _user_id(request):
        raise HTTPException(404, "Segment not found")
    nid = await db.create_note(segment_id, recording_id, body.content)
    note = await db.get_note(nid)
    return NoteOut(**note)


@router.patch("/notes/{note_id}", response_model=NoteOut)
async def update_note(note_id: int, body: NoteUpdate, request: Request, db: Database = Depends(get_db)):
    note = await db.get_note(note_id)
    if not note:
        raise HTTPException(404, "Note not found")
    recording_id = note["recording_id"]
    rec = await db.get_recording(recording_id)
    if not rec or rec["user_id"] != _user_id(request):
        raise HTTPException(404, "Note not found")
    await db.update_note(note_id, body.content)
    return NoteOut(**await db.get_note(note_id))


@router.delete("/notes/{note_id}", status_code=204)
async def delete_note(note_id: int, request: Request, db: Database = Depends(get_db)):
    note = await db.get_note(note_id)
    if not note:
        raise HTTPException(404, "Note not found")
    recording_id = note["recording_id"]
    rec = await db.get_recording(recording_id)
    if not rec or rec["user_id"] != _user_id(request):
        raise HTTPException(404, "Note not found")
    await db.delete_note(note_id)
    return Response(status_code=204)
