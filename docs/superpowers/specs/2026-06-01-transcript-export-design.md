# Transcript Export Formats Design

**Date**: 2026-06-01  
**Issue**: MVA-2174  
**Author**: BackendEngineer  
**Status**: Proposed

## Summary

Implement export functionality for audio transcripts in four formats: DOCX, PDF, SRT (subtitles), and VTT (WebVTT). This is part of the larger Transcriber module feature (#9044).

## Context

The Transcriber module will provide general-purpose audio transcription with:
- Projects to organize recordings
- Processing pipeline with diarization (speaker identification)
- Transcript workspace with editing capabilities
- **Export functionality** (this spec)
- AI analysis and knowledge base integration

This spec focuses solely on the export endpoints and generators.

## Data Model Assumption

Since the full transcriber module is being built in parallel, we assume transcripts will be stored in a dedicated SQLite database (`data/transcriber/transcriber.db`) as mentioned in GitHub issue #9044.

**Data structure**:

```python
Transcript:
  - id: str                    # UUID
  - project_id: str            # Foreign key to projects table
  - title: str                 # Recording title
  - audio_file: str            # Path to audio file
  - duration_seconds: float    # Total duration
  - language: str              # Language code (e.g., "en", "lv")
  - created_at: datetime       # Creation timestamp
  - segments: List[Segment]    # Ordered list of transcript segments

Segment:
  - id: str                    # UUID
  - transcript_id: str         # Foreign key
  - start_time: float          # Start time in seconds
  - end_time: float            # End time in seconds
  - speaker_label: str         # Display name (can be renamed via speaker management)
  - text: str                  # Transcribed text
  - confidence: float          # optional, STT confidence score
  - notes: str                 # optional, user-added notes from inline editing
```

**Speaker handling**: The `speaker_label` field contains the **display name** (e.g., "John Doe", "Speaker 1"). If users rename speakers via the transcript workspace, exports will use the renamed labels automatically.

## Approach Comparison

### Option A: Standalone API Router (Recommended)

**Structure**:
```
autobot-backend/api/transcript_export.py  # Export endpoints
autobot-backend/services/transcript_export/
  ├── __init__.py
  ├── base.py           # BaseExporter abstract class
  ├── docx_exporter.py  # DOCX generator
  ├── pdf_exporter.py   # PDF generator
  ├── srt_exporter.py   # SRT generator
  └── vtt_exporter.py   # VTT generator
```

**Pros**:
- Clean separation of concerns
- Easy to test each exporter independently
- Can be integrated into the transcriber module later
- Follows existing service pattern in the codebase

**Cons**:
- May need to mock transcript data for testing until full module exists

### Option B: Build Inside Transcriber Module

**Structure**:
```
autobot-backend/transcriber/
  ├── api.py            # All transcriber endpoints including export
  ├── models.py         # Database models
  ├── export/
  │   ├── docx.py
  │   ├── pdf.py
  │   ├── srt.py
  │   └── vtt.py
```

**Pros**:
- Everything in one place
- Matches the planned architecture from GitHub issue

**Cons**:
- Requires building the full transcriber foundation first
- Longer time to first deliverable

### Option C: Extend Voice API

Add export to existing `/api/voice.py` since transcription is voice-related.

**Pros**:
- Minimal new files

**Cons**:
- voice.py already has 419 lines, would grow significantly
- Conceptually different from live transcription
- Hard to separate later

## Recommended Approach: Option A

Build standalone export services that can be integrated into the transcriber module when ready. This allows:
1. Immediate progress on export functionality
2. Clean, testable code
3. Easy integration later

## Architecture

### API Endpoints

```python
GET /api/transcripts/{id}/export/docx
GET /api/transcripts/{id}/export/pdf
GET /api/transcripts/{id}/export/srt
GET /api/transcripts/{id}/export/vtt
```

Each endpoint:
- Fetches transcript data from database
- Instantiates appropriate exporter
- Generates file content
- Returns file download response with correct MIME type

### Exporter Classes

**Base Exporter**:
```python
class BaseExporter(ABC):
    def __init__(self, transcript: Transcript):
        self.transcript = transcript
    
    @abstractmethod
    async def generate(self) -> bytes:
        """Generate export file content."""
        pass
    
    @abstractmethod
    def get_mime_type(self) -> str:
        """Return MIME type for this format."""
        pass
    
    @abstractmethod
    def get_file_extension(self) -> str:
        """Return file extension."""
        pass
```

### Format Specifications

#### DOCX Format

**Layout**:
- Header: Title, Date, Duration, Language
- Segments: Speaker label + timestamp + text
- Formatting: Bold for speakers, monospace for timestamps

**Example**:
```
Meeting Transcript
Date: June 1, 2026
Duration: 15:42
Language: English

[00:00:05] Speaker 1: Hello everyone, welcome to the meeting.
[00:00:12] Speaker 2: Thank you for having us.
```

#### PDF Format

Similar to DOCX but with PDF-specific formatting:
- Title page with metadata
- Table of contents (optional, for long transcripts)
- Segments with speaker labels and timestamps
- Page numbers and footer

#### SRT Format (SubRip Subtitles)

**Specification**:
```
1
00:00:05,000 --> 00:00:10,000
Speaker 1: Hello everyone, welcome to the meeting.

2
00:00:12,000 --> 00:00:18,000
Speaker 2: Thank you for having us.
```

- 1-indexed sequence numbers
- Time format: HH:MM:SS,mmm
- Speaker labels included in text

#### VTT Format (WebVTT)

**Specification**:
```
WEBVTT

00:00:05.000 --> 00:00:10.000
<v Speaker 1>Hello everyone, welcome to the meeting.

00:00:12.000 --> 00:00:18.000
<v Speaker 2>Thank you for having us.
```

- Header: "WEBVTT"
- Time format: HH:MM:SS.mmm
- Voice tags: `<v Speaker>`

## Dependencies

Add to `autobot-backend/requirements.txt`:
```
python-docx>=1.1.0    # DOCX generation
reportlab>=4.0.0      # PDF generation
```

SRT and VTT are text-based and need no external libraries.

## Testing Strategy

### Unit Tests

Each exporter class:
- `test_generate_empty_transcript()` - Handle edge case
- `test_generate_single_segment()` - Basic functionality
- `test_generate_multiple_speakers()` - Speaker identification
- `test_format_timestamps()` - Time formatting
- `test_special_characters()` - Escape handling

### Integration Tests

For each endpoint:
- `test_export_{format}_success()` - Happy path
- `test_export_transcript_not_found()` - 404 handling
- `test_export_unauthorized()` - Permission check
- `test_export_mime_type()` - Correct Content-Type header
- `test_export_filename()` - Content-Disposition header

### Mock Data

Since transcriber database doesn't exist yet, tests will use:
```python
@pytest.fixture
def mock_transcript():
    return Transcript(
        id="test-123",
        title="Test Meeting",
        duration_seconds=300.0,
        language="en",
        segments=[
            Segment(
                start_time=5.0,
                end_time=10.0,
                speaker_label="Speaker 1",
                text="Hello everyone."
            ),
            # ... more segments
        ]
    )
```

## Error Handling

- **Transcript not found**: 404 with JSON error
- **Invalid transcript ID**: 400 with validation message
- **Export generation failure**: 500 with error details
- **Permission denied**: 403 with message

## Future Considerations

1. **Customization**: Allow users to configure export format (e.g., include/exclude timestamps)
2. **Batch Export**: Export multiple transcripts at once
3. **Template System**: Custom DOCX/PDF templates
4. **Async Generation**: Queue large export jobs
5. **Caching**: Cache generated exports for repeated downloads

## Security

- Validate transcript ID format
- Check user permissions before export
- Sanitize text content to prevent injection in PDF/DOCX
- Rate limiting on export endpoints

## Success Criteria

- [ ] All four export endpoints functional
- [ ] Correct MIME types and file extensions
- [ ] Format specifications followed (SRT, VTT standards)
- [ ] Unit tests pass with >80% coverage
- [ ] Integration tests validate file format correctness
- [ ] Error handling for all edge cases
- [ ] Documentation updated

## Implementation Plan

Will transition to detailed implementation plan after approval.
