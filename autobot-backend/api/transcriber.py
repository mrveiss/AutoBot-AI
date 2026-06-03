# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Transcriber API
# Issue #9044, #9214

"""Transcriber API endpoints for audio transcription with speaker diarization."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from api.schemas_common import DataResponse
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from transcriber.database import get_transcriber_db
from transcriber.models import (
    ProcessingResponse,
    RecordingCreate,
    RecordingResponse,
    SegmentResponse,
    UploadResponse,
)
from transcriber.orchestrator import get_transcriber_orchestrator
from transcriber.upload_security import UploadSecurityError, save_uploaded_file

logger = get_logger(__name__)

router = APIRouter()


@router.post("/upload", response_model=DataResponse[UploadResponse], status_code=201)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="upload_recording",
    error_code_prefix="TRANSCRIBER",
)
async def upload_recording(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Upload an audio file for transcription.

    Security measures:
    - UUID-based server-managed filenames
    - Per-user upload directories
    - Extension whitelist (wav, mp3, mp4, m4a, ogg, flac, webm)
    - 500MB size limit
    - Path traversal protection

    Args:
        file: Audio file upload
        current_user: Authenticated user

    Returns:
        Upload response with server-managed file path

    Issue #9214: Secure file upload to prevent path injection
    """
    try:
        user_id = current_user.get("id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="User ID not found in token")

        # Read file content
        file_content = await file.read()

        # Save with security validations
        file_path = save_uploaded_file(
            file_content=file_content,
            original_filename=file.filename or "audio.wav",
            user_id=user_id,
        )

        response_data = {
            "file_path": file_path,
            "filename": file.filename or "audio.wav",
            "size_bytes": len(file_content),
        }

        logger.info(
            "File uploaded successfully: %s (user: %d, size: %d bytes)",
            file_path,
            user_id,
            len(file_content),
        )

        return JSONResponse(status_code=201, content={"data": response_data})

    except UploadSecurityError as exc:
        logger.warning("Upload security violation: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Failed to upload file: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/recordings", response_model=DataResponse[RecordingResponse], status_code=201)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_recording",
    error_code_prefix="TRANSCRIBER",
)
async def create_recording(
    recording: RecordingCreate,
    file_path: str,
    current_user: dict = Depends(get_current_user),
):
    """Create a new recording entry with server-managed file path.

    Security: file_path must be from a previous upload response.
    Client-provided paths are rejected.

    Args:
        recording: Recording creation data (filename only)
        file_path: Server-managed file path from upload endpoint
        current_user: Authenticated user

    Returns:
        Created recording with pending status

    Issue #9044: Transcriber pipeline foundation
    Issue #9214: Removed client-provided file_path to prevent path injection
    """
    try:
        user_id = current_user.get("id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="User ID not found in token")

        # Import here to avoid circular dependency
        from transcriber.upload_security import validate_upload_path

        # Validate that file_path is within user's upload directory
        try:
            validated_path = validate_upload_path(file_path, user_id)
        except UploadSecurityError as exc:
            logger.warning("Invalid file path provided: %s", exc)
            raise HTTPException(
                status_code=400,
                detail="Invalid file path. Use POST /api/transcriber/upload first.",
            )

        db = await get_transcriber_db()
        created = await db.create_recording(filename=recording.filename, file_path=str(validated_path), user_id=user_id)

        response_data = {
            "id": created.id,
            "filename": created.filename,
            "file_path": created.file_path,
            "user_id": created.user_id,
            "duration": created.duration,
            "language": created.language,
            "status": created.status.value,
            "created_at": created.created_at.isoformat(),
            "updated_at": created.updated_at.isoformat(),
            "metadata": created.metadata,
        }

        return JSONResponse(status_code=201, content={"data": response_data})

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to create recording: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/recordings/{recording_id}", response_model=DataResponse[RecordingResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_recording",
    error_code_prefix="TRANSCRIBER",
)
async def get_recording(
    recording_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Get recording by ID.

    Args:
        recording_id: Recording ID
        current_user: Authenticated user

    Returns:
        Recording details

    Issue #9044: Transcriber pipeline foundation
    """
    try:
        user_id = current_user.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="User ID not found in session")

        db = await get_transcriber_db()
        # Ownership check: returns None if user doesn't own the recording
        recording = await db.get_recording(recording_id, user_id=user_id)

        # Return 404 (not 403) to avoid ID enumeration
        if recording is None:
            raise HTTPException(status_code=404, detail="Recording not found")

        response_data = {
            "id": recording.id,
            "filename": recording.filename,
            "file_path": recording.file_path,
            "user_id": recording.user_id,
            "duration": recording.duration,
            "language": recording.language,
            "status": recording.status.value,
            "created_at": recording.created_at.isoformat(),
            "updated_at": recording.updated_at.isoformat(),
            "metadata": recording.metadata,
        }

        return JSONResponse(status_code=200, content={"data": response_data})

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to get recording %d: %s", recording_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post(
    "/recordings/{recording_id}/process",
    response_model=DataResponse[ProcessingResponse],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="process_recording",
    error_code_prefix="TRANSCRIBER",
)
async def process_recording(
    recording_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Process a recording through the transcription pipeline.

    Pipeline stages:
    1. Extract and normalize audio with FFmpeg
    2. Detect language
    3. Generate speaker segments with Pyannote diarization
    4. Transcribe audio with language-appropriate speech provider
    5. Merge transcription text with speaker timestamps
    6. Persist segments to database

    Args:
        recording_id: Recording ID to process
        current_user: Authenticated user

    Returns:
        Processing result with status and segment count

    Issue #9044: Transcriber pipeline integration
    """
    try:
        user_id = current_user.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="User ID not found in session")

        # Ownership check before processing
        db = await get_transcriber_db()
        recording = await db.get_recording(recording_id, user_id=user_id)

        # Return 404 (not 403) to avoid ID enumeration
        if recording is None:
            raise HTTPException(status_code=404, detail="Recording not found")

        orchestrator = get_transcriber_orchestrator()
        result = await orchestrator.process_recording(recording_id)

        response_data = {
            "recording_id": result["recording_id"],
            "status": result["status"],
            "segments_count": result["segments_count"],
            "message": (
                f"Processed successfully: {result['segments_count']} segments, "
                f"language: {result.get('language', 'unknown')}, "
                f"duration: {result.get('duration', 0):.2f}s"
            ),
        }

        return JSONResponse(status_code=200, content={"data": response_data})

    except ValueError as exc:
        logger.warning("Processing validation error for recording %d: %s", recording_id, exc)
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to process recording %d: %s", recording_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/recordings/{recording_id}/segments",
    response_model=DataResponse[list[SegmentResponse]],
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_segments",
    error_code_prefix="TRANSCRIBER",
)
async def get_segments(
    recording_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Get all segments for a recording.

    Args:
        recording_id: Recording ID
        current_user: Authenticated user

    Returns:
        List of transcription segments ordered by start_time

    Issue #9044: Transcriber pipeline foundation
    """
    try:
        user_id = current_user.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="User ID not found in session")

        db = await get_transcriber_db()

        # Ownership check: verify user owns this recording
        recording = await db.get_recording(recording_id, user_id=user_id)

        # Return 404 (not 403) to avoid ID enumeration
        if recording is None:
            raise HTTPException(status_code=404, detail="Recording not found")

        # Get segments
        segments = await db.get_recording_segments(recording_id)

        response_data = [
            {
                "id": seg.id,
                "recording_id": seg.recording_id,
                "speaker_label": seg.speaker_label,
                "start_time": seg.start_time,
                "end_time": seg.end_time,
                "text": seg.text,
                "confidence": seg.confidence,
                "created_at": seg.created_at.isoformat(),
            }
            for seg in segments
        ]

        return JSONResponse(status_code=200, content={"data": response_data})

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to get segments for recording %d: %s", recording_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
