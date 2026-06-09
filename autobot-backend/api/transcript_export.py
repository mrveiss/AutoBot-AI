# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Transcript export API endpoints.

Provides endpoints to export transcripts in various formats:
- DOCX (Microsoft Word)
- PDF
- SRT (SubRip subtitles)
- VTT (WebVTT subtitles)
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from services.transcript_export import (
    DOCXExporter,
    PDFExporter,
    Segment,
    SRTExporter,
    Transcript,
    VTTExporter,
)

router = APIRouter(
    prefix="/transcripts",
    tags=["transcript_export"],
    dependencies=[Depends(check_admin_permission)],
)

logger = get_logger(__name__)


# TODO: Replace with actual database fetch when transcriber module is implemented
async def _get_transcript_mock(transcript_id: str) -> Transcript:
    """Mock function to get transcript data.

    This will be replaced with actual database query when the transcriber
    module database schema is implemented.

    Args:
        transcript_id: Transcript UUID

    Returns:
        Transcript: Transcript object

    Raises:
        HTTPException: If transcript not found
    """
    # Mock data for testing
    if transcript_id == "test-transcript-1":
        return Transcript(
            id=transcript_id,
            title="Sample Meeting Transcript",
            duration_seconds=300.0,
            language="en",
            segments=[
                Segment(
                    id="seg-1",
                    transcript_id=transcript_id,
                    start_time=5.0,
                    end_time=10.0,
                    speaker_label="Speaker 1",
                    text="Welcome everyone to today's meeting.",
                ),
                Segment(
                    id="seg-2",
                    transcript_id=transcript_id,
                    start_time=12.0,
                    end_time=18.0,
                    speaker_label="Speaker 2",
                    text="Thank you for having us here.",
                ),
            ],
        )

    raise HTTPException(status_code=404, detail=f"Transcript {transcript_id} not found")


@router.get("/{transcript_id}/export/docx")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="transcript_export_docx",
    error_code_prefix="TRANSCRIPT_EXPORT",
)
async def export_docx(transcript_id: str):
    """Export transcript as DOCX (Microsoft Word) file.

    Args:
        transcript_id: Transcript UUID

    Returns:
        Response: DOCX file download
    """
    transcript = await _get_transcript_mock(transcript_id)
    exporter = DOCXExporter(transcript)

    content = await exporter.generate()
    filename = exporter.get_filename()

    logger.info(f"Generated DOCX export for transcript {transcript_id}")

    return Response(
        content=content,
        media_type=exporter.get_mime_type(),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{transcript_id}/export/pdf")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="transcript_export_pdf",
    error_code_prefix="TRANSCRIPT_EXPORT",
)
async def export_pdf(transcript_id: str):
    """Export transcript as PDF file.

    Args:
        transcript_id: Transcript UUID

    Returns:
        Response: PDF file download
    """
    transcript = await _get_transcript_mock(transcript_id)
    exporter = PDFExporter(transcript)

    content = await exporter.generate()
    filename = exporter.get_filename()

    logger.info(f"Generated PDF export for transcript {transcript_id}")

    return Response(
        content=content,
        media_type=exporter.get_mime_type(),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{transcript_id}/export/srt")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="transcript_export_srt",
    error_code_prefix="TRANSCRIPT_EXPORT",
)
async def export_srt(transcript_id: str):
    """Export transcript as SRT (SubRip) subtitle file.

    Args:
        transcript_id: Transcript UUID

    Returns:
        Response: SRT file download
    """
    transcript = await _get_transcript_mock(transcript_id)
    exporter = SRTExporter(transcript)

    content = await exporter.generate()
    filename = exporter.get_filename()

    logger.info(f"Generated SRT export for transcript {transcript_id}")

    return Response(
        content=content,
        media_type=exporter.get_mime_type(),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{transcript_id}/export/vtt")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="transcript_export_vtt",
    error_code_prefix="TRANSCRIPT_EXPORT",
)
async def export_vtt(transcript_id: str):
    """Export transcript as VTT (WebVTT) subtitle file.

    Args:
        transcript_id: Transcript UUID

    Returns:
        Response: VTT file download
    """
    transcript = await _get_transcript_mock(transcript_id)
    exporter = VTTExporter(transcript)

    content = await exporter.generate()
    filename = exporter.get_filename()

    logger.info(f"Generated VTT export for transcript {transcript_id}")

    return Response(
        content=content,
        media_type=exporter.get_mime_type(),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
