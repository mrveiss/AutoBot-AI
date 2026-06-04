"""Tests for PDF exporter."""

import io
import pytest
from PyPDF2 import PdfReader
from services.transcript_export.base import Segment, Transcript
from services.transcript_export.pdf_exporter import PDFExporter


@pytest.fixture
def sample_transcript():
    """Sample transcript for testing."""
    return Transcript(
        id="test-pdf",
        title="Conference Call",
        duration_seconds=180.0,
        language="en",
        segments=[
            Segment(
                id="seg-1",
                transcript_id="test-pdf",
                start_time=0.0,
                end_time=8.0,
                speaker_label="Alice",
                text="Good morning everyone.",
            ),
            Segment(
                id="seg-2",
                transcript_id="test-pdf",
                start_time=10.0,
                end_time=20.0,
                speaker_label="Bob",
                text="Thanks for joining the call.",
            ),
        ],
    )


@pytest.mark.asyncio
async def test_pdf_generate(sample_transcript):
    """Test PDF generation."""
    exporter = PDFExporter(sample_transcript)
    result = await exporter.generate()

    # Verify it's valid PDF
    assert result.startswith(b"%PDF")

    # Parse PDF and check content
    reader = PdfReader(io.BytesIO(result))
    assert len(reader.pages) >= 2  # Title page + content page

    # Extract text from all pages
    full_text = "\n".join(page.extract_text() for page in reader.pages)
    assert "Conference Call" in full_text
    assert "Alice" in full_text or "Good morning" in full_text


@pytest.mark.asyncio
async def test_pdf_mime_type():
    """Test PDF MIME type."""
    transcript = Transcript(
        id="test",
        title="Test",
        duration_seconds=10.0,
        language="en",
        segments=[],
    )
    exporter = PDFExporter(transcript)
    assert exporter.get_mime_type() == "application/pdf"


@pytest.mark.asyncio
async def test_pdf_file_extension():
    """Test PDF file extension."""
    transcript = Transcript(
        id="test",
        title="Test",
        duration_seconds=10.0,
        language="en",
        segments=[],
    )
    exporter = PDFExporter(transcript)
    assert exporter.get_file_extension() == ".pdf"
