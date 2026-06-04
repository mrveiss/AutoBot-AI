# Transcript Export Services

Standalone export service package for transcripts. Supports multiple formats with clean, testable abstractions.

## Formats

### DOCX (Microsoft Word)
- Formatted document with title, metadata, and speaker labels
- Bold speakers, monospace timestamps
- Optional inline notes

### PDF
- Title page with metadata
- Professional layout with page numbers
- Speaker labels and timestamps

### SRT (SubRip Subtitles)
- Standard subtitle format for video
- Sequence numbers, HH:MM:SS,mmm timestamps
- Speaker labels in subtitle text

### VTT (WebVTT)
- Web-standard subtitle format
- WEBVTT header, HH:MM:SS.mmm timestamps
- Voice tags for speaker identification

## Usage

```python
from services.transcript_export import Transcript, Segment, DOCXExporter

# Create transcript
transcript = Transcript(
    id="trans-1",
    title="Meeting",
    duration_seconds=300.0,
    language="en",
    segments=[...]
)

# Export to DOCX
exporter = DOCXExporter(transcript)
content = await exporter.generate()
```

## API Endpoints

- `GET /api/transcripts/{id}/export/docx`
- `GET /api/transcripts/{id}/export/pdf`
- `GET /api/transcripts/{id}/export/srt`
- `GET /api/transcripts/{id}/export/vtt`

All endpoints return file downloads with appropriate MIME types.

## Testing

```bash
# Unit tests
pytest autobot-backend/tests/services/test_*_exporter.py

# Integration tests
pytest autobot-backend/tests/api/test_transcript_export.py
```

## Integration with Transcriber Module

Currently uses mock data (`_get_transcript_mock`). When the transcriber database is implemented:

1. Replace mock function in `api/transcript_export.py`
2. Add actual database query to fetch transcript and segments
3. Update tests to use test database fixtures

## Dependencies

- `python-docx` - DOCX generation
- `reportlab` - PDF generation
- `PyPDF2` - PDF testing
