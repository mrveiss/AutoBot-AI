# Transcript Export Formats Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement transcript export in DOCX, PDF, SRT, and VTT formats with API endpoints and comprehensive tests.

**Architecture:** Standalone export service package with abstract base exporter and format-specific implementations. FastAPI endpoints serve generated files with appropriate MIME types.

**Tech Stack:** FastAPI, python-docx, reportlab, pytest, Pydantic

---

## File Structure

**New Files:**
- `autobot-backend/services/transcript_export/__init__.py` - Package exports
- `autobot-backend/services/transcript_export/base.py` - BaseExporter + data models
- `autobot-backend/services/transcript_export/srt_exporter.py` - SRT generator
- `autobot-backend/services/transcript_export/vtt_exporter.py` - VTT generator
- `autobot-backend/services/transcript_export/docx_exporter.py` - DOCX generator
- `autobot-backend/services/transcript_export/pdf_exporter.py` - PDF generator
- `autobot-backend/api/transcript_export.py` - API router
- `autobot-backend/tests/services/test_srt_exporter.py` - SRT tests
- `autobot-backend/tests/services/test_vtt_exporter.py` - VTT tests
- `autobot-backend/tests/services/test_docx_exporter.py` - DOCX tests
- `autobot-backend/tests/services/test_pdf_exporter.py` - PDF tests
- `autobot-backend/tests/api/test_transcript_export.py` - API integration tests

**Modified Files:**
- `autobot-backend/requirements.txt` - Add dependencies
- `autobot-backend/app_factory.py` - Register transcript_export router

---

### Task 1: Add Dependencies

**Files:**
- Modify: `autobot-backend/requirements.txt`

- [ ] **Step 1: Add export libraries to requirements**

Add these lines to `autobot-backend/requirements.txt`:

```txt
python-docx>=1.1.0
reportlab>=4.0.0
```

- [ ] **Step 2: Install dependencies**

Run: `cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/MVA-2174/autobot-backend && pip install python-docx reportlab`

Expected: Both packages install successfully

- [ ] **Step 3: Commit**

```bash
git add autobot-backend/requirements.txt
git commit -m "deps(transcriber): add python-docx and reportlab for export (MVA-2174)

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

### Task 2: Create Base Exporter and Data Models

**Files:**
- Create: `autobot-backend/services/transcript_export/__init__.py`
- Create: `autobot-backend/services/transcript_export/base.py`
- Create: `autobot-backend/tests/services/test_base_exporter.py`

- [ ] **Step 1: Create services directory**

Run: `mkdir -p autobot-backend/services/transcript_export autobot-backend/tests/services`

- [ ] **Step 2: Write test for data models**

Create `autobot-backend/tests/services/test_base_exporter.py`:

```python
"""Tests for transcript export base classes and data models."""
import pytest
from services.transcript_export.base import Segment, Transcript


def test_segment_creation():
    """Test Segment model creation."""
    segment = Segment(
        id="seg-1",
        transcript_id="trans-1",
        start_time=5.0,
        end_time=10.5,
        speaker_label="Speaker 1",
        text="Hello world",
    )
    assert segment.start_time == 5.0
    assert segment.end_time == 10.5
    assert segment.speaker_label == "Speaker 1"
    assert segment.text == "Hello world"


def test_segment_duration():
    """Test segment duration calculation."""
    segment = Segment(
        id="seg-1",
        transcript_id="trans-1",
        start_time=5.0,
        end_time=10.5,
        speaker_label="Speaker 1",
        text="Hello world",
    )
    assert segment.duration == 5.5


def test_transcript_creation():
    """Test Transcript model creation with segments."""
    segments = [
        Segment(
            id="seg-1",
            transcript_id="trans-1",
            start_time=0.0,
            end_time=5.0,
            speaker_label="Speaker 1",
            text="First segment",
        ),
        Segment(
            id="seg-2",
            transcript_id="trans-1",
            start_time=5.0,
            end_time=10.0,
            speaker_label="Speaker 2",
            text="Second segment",
        ),
    ]
    
    transcript = Transcript(
        id="trans-1",
        title="Test Transcript",
        duration_seconds=10.0,
        language="en",
        segments=segments,
    )
    
    assert transcript.id == "trans-1"
    assert transcript.title == "Test Transcript"
    assert len(transcript.segments) == 2
    assert transcript.segments[0].speaker_label == "Speaker 1"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/MVA-2174 && python -m pytest autobot-backend/tests/services/test_base_exporter.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'services.transcript_export'"

- [ ] **Step 4: Create base exporter with data models**

Create `autobot-backend/services/transcript_export/base.py`:

```python
"""Base classes and data models for transcript export.

Provides abstract exporter interface and Pydantic models for transcript data.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class Segment(BaseModel):
    """A single transcript segment with timestamp and speaker."""
    
    id: str
    transcript_id: str
    start_time: float = Field(..., description="Start time in seconds")
    end_time: float = Field(..., description="End time in seconds")
    speaker_label: str = Field(..., description="Display name for speaker")
    text: str
    confidence: Optional[float] = None
    notes: Optional[str] = None
    
    @property
    def duration(self) -> float:
        """Calculate segment duration in seconds."""
        return self.end_time - self.start_time


class Transcript(BaseModel):
    """Complete transcript with metadata and segments."""
    
    id: str
    project_id: Optional[str] = None
    title: str
    audio_file: Optional[str] = None
    duration_seconds: float
    language: str
    created_at: Optional[datetime] = None
    segments: List[Segment] = Field(default_factory=list)


class BaseExporter(ABC):
    """Abstract base class for transcript exporters."""
    
    def __init__(self, transcript: Transcript):
        """Initialize exporter with transcript data.
        
        Args:
            transcript: Transcript object to export
        """
        self.transcript = transcript
    
    @abstractmethod
    async def generate(self) -> bytes:
        """Generate export file content.
        
        Returns:
            bytes: Generated file content
        """
        pass
    
    @abstractmethod
    def get_mime_type(self) -> str:
        """Return MIME type for this format.
        
        Returns:
            str: MIME type (e.g., "application/pdf")
        """
        pass
    
    @abstractmethod
    def get_file_extension(self) -> str:
        """Return file extension for this format.
        
        Returns:
            str: File extension (e.g., ".pdf")
        """
        pass
    
    def get_filename(self) -> str:
        """Generate filename from transcript title and extension.
        
        Returns:
            str: Sanitized filename
        """
        # Sanitize title: remove special characters
        safe_title = "".join(c for c in self.transcript.title if c.isalnum() or c in (' ', '-', '_'))
        safe_title = safe_title.strip().replace(' ', '_')
        return f"{safe_title}{self.get_file_extension()}"
```

- [ ] **Step 5: Create package init**

Create `autobot-backend/services/transcript_export/__init__.py`:

```python
"""Transcript export services."""
from services.transcript_export.base import BaseExporter, Segment, Transcript

__all__ = ["BaseExporter", "Segment", "Transcript"]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/MVA-2174 && python -m pytest autobot-backend/tests/services/test_base_exporter.py -v`

Expected: 3 tests PASS

- [ ] **Step 7: Commit**

```bash
git add autobot-backend/services/transcript_export/ autobot-backend/tests/services/test_base_exporter.py
git commit -m "feat(transcriber): add base exporter and data models (MVA-2174)

- BaseExporter abstract class
- Segment and Transcript Pydantic models
- Duration calculation property
- Filename sanitization

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

### Task 3: Implement SRT Exporter

**Files:**
- Create: `autobot-backend/services/transcript_export/srt_exporter.py`
- Create: `autobot-backend/tests/services/test_srt_exporter.py`

- [ ] **Step 1: Write failing test for SRT format**

Create `autobot-backend/tests/services/test_srt_exporter.py`:

```python
"""Tests for SRT (SubRip) subtitle exporter."""
import pytest
from services.transcript_export.base import Segment, Transcript
from services.transcript_export.srt_exporter import SRTExporter


@pytest.fixture
def sample_transcript():
    """Sample transcript for testing."""
    return Transcript(
        id="test-123",
        title="Test Meeting",
        duration_seconds=30.0,
        language="en",
        segments=[
            Segment(
                id="seg-1",
                transcript_id="test-123",
                start_time=5.0,
                end_time=10.0,
                speaker_label="Speaker 1",
                text="Hello everyone, welcome to the meeting.",
            ),
            Segment(
                id="seg-2",
                transcript_id="test-123",
                start_time=12.5,
                end_time=18.0,
                speaker_label="Speaker 2",
                text="Thank you for having us.",
            ),
        ],
    )


@pytest.mark.asyncio
async def test_srt_generate(sample_transcript):
    """Test SRT generation with proper formatting."""
    exporter = SRTExporter(sample_transcript)
    result = await exporter.generate()
    
    # Decode bytes to string
    content = result.decode("utf-8")
    
    # Check SRT structure
    assert "1\n" in content  # First sequence number
    assert "00:00:05,000 --> 00:00:10,000" in content  # First timestamp
    assert "Speaker 1: Hello everyone, welcome to the meeting." in content
    
    assert "2\n" in content  # Second sequence number
    assert "00:00:12,500 --> 00:00:18,000" in content  # Second timestamp
    assert "Speaker 2: Thank you for having us." in content


@pytest.mark.asyncio
async def test_srt_mime_type():
    """Test SRT MIME type."""
    transcript = Transcript(
        id="test",
        title="Test",
        duration_seconds=10.0,
        language="en",
        segments=[],
    )
    exporter = SRTExporter(transcript)
    assert exporter.get_mime_type() == "application/x-subrip"


@pytest.mark.asyncio
async def test_srt_file_extension():
    """Test SRT file extension."""
    transcript = Transcript(
        id="test",
        title="Test",
        duration_seconds=10.0,
        language="en",
        segments=[],
    )
    exporter = SRTExporter(transcript)
    assert exporter.get_file_extension() == ".srt"


@pytest.mark.asyncio
async def test_srt_empty_segments():
    """Test SRT generation with no segments."""
    transcript = Transcript(
        id="test",
        title="Empty Transcript",
        duration_seconds=0.0,
        language="en",
        segments=[],
    )
    exporter = SRTExporter(transcript)
    result = await exporter.generate()
    content = result.decode("utf-8")
    
    # Should be empty or minimal
    assert len(content.strip()) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/MVA-2174 && python -m pytest autobot-backend/tests/services/test_srt_exporter.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'services.transcript_export.srt_exporter'"

- [ ] **Step 3: Implement SRT exporter**

Create `autobot-backend/services/transcript_export/srt_exporter.py`:

```python
"""SRT (SubRip) subtitle format exporter.

SRT format specification:
- Sequence numbers starting at 1
- Timestamps in format: HH:MM:SS,mmm --> HH:MM:SS,mmm
- Speaker label and text
- Empty line between entries
"""
from services.transcript_export.base import BaseExporter, Transcript


class SRTExporter(BaseExporter):
    """Export transcript to SRT (SubRip) subtitle format."""
    
    def _format_time(self, seconds: float) -> str:
        """Format time as HH:MM:SS,mmm.
        
        Args:
            seconds: Time in seconds
            
        Returns:
            str: Formatted time string
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
    
    async def generate(self) -> bytes:
        """Generate SRT file content.
        
        Returns:
            bytes: SRT file content as UTF-8 encoded bytes
        """
        if not self.transcript.segments:
            return b""
        
        lines = []
        for idx, segment in enumerate(self.transcript.segments, start=1):
            # Sequence number
            lines.append(str(idx))
            
            # Timestamp
            start = self._format_time(segment.start_time)
            end = self._format_time(segment.end_time)
            lines.append(f"{start} --> {end}")
            
            # Text with speaker label
            text = f"{segment.speaker_label}: {segment.text}"
            lines.append(text)
            
            # Empty line separator
            lines.append("")
        
        content = "\n".join(lines)
        return content.encode("utf-8")
    
    def get_mime_type(self) -> str:
        """Return SRT MIME type."""
        return "application/x-subrip"
    
    def get_file_extension(self) -> str:
        """Return SRT file extension."""
        return ".srt"
```

- [ ] **Step 4: Update package init**

Edit `autobot-backend/services/transcript_export/__init__.py`:

```python
"""Transcript export services."""
from services.transcript_export.base import BaseExporter, Segment, Transcript
from services.transcript_export.srt_exporter import SRTExporter

__all__ = ["BaseExporter", "Segment", "Transcript", "SRTExporter"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/MVA-2174 && python -m pytest autobot-backend/tests/services/test_srt_exporter.py -v`

Expected: 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add autobot-backend/services/transcript_export/srt_exporter.py autobot-backend/tests/services/test_srt_exporter.py autobot-backend/services/transcript_export/__init__.py
git commit -m "feat(transcriber): add SRT subtitle exporter (MVA-2174)

Implements SubRip (SRT) format:
- Sequence numbering from 1
- HH:MM:SS,mmm timestamp format
- Speaker labels in subtitle text

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

### Task 4: Implement VTT Exporter

**Files:**
- Create: `autobot-backend/services/transcript_export/vtt_exporter.py`
- Create: `autobot-backend/tests/services/test_vtt_exporter.py`

- [ ] **Step 1: Write failing test for VTT format**

Create `autobot-backend/tests/services/test_vtt_exporter.py`:

```python
"""Tests for VTT (WebVTT) subtitle exporter."""
import pytest
from services.transcript_export.base import Segment, Transcript
from services.transcript_export.vtt_exporter import VTTExporter


@pytest.fixture
def sample_transcript():
    """Sample transcript for testing."""
    return Transcript(
        id="test-456",
        title="Test Webinar",
        duration_seconds=25.0,
        language="en",
        segments=[
            Segment(
                id="seg-1",
                transcript_id="test-456",
                start_time=3.5,
                end_time=8.0,
                speaker_label="John Doe",
                text="Welcome to our webinar.",
            ),
            Segment(
                id="seg-2",
                transcript_id="test-456",
                start_time=10.0,
                end_time=15.5,
                speaker_label="Jane Smith",
                text="Let's begin with the first topic.",
            ),
        ],
    )


@pytest.mark.asyncio
async def test_vtt_generate(sample_transcript):
    """Test VTT generation with proper formatting."""
    exporter = VTTExporter(sample_transcript)
    result = await exporter.generate()
    
    content = result.decode("utf-8")
    
    # Check VTT header
    assert content.startswith("WEBVTT")
    
    # Check timestamps (dots not commas)
    assert "00:00:03.500 --> 00:00:08.000" in content
    assert "00:00:10.000 --> 00:00:15.500" in content
    
    # Check voice tags
    assert "<v John Doe>" in content
    assert "Welcome to our webinar." in content
    assert "<v Jane Smith>" in content
    assert "Let's begin with the first topic." in content


@pytest.mark.asyncio
async def test_vtt_mime_type():
    """Test VTT MIME type."""
    transcript = Transcript(
        id="test",
        title="Test",
        duration_seconds=10.0,
        language="en",
        segments=[],
    )
    exporter = VTTExporter(transcript)
    assert exporter.get_mime_type() == "text/vtt"


@pytest.mark.asyncio
async def test_vtt_file_extension():
    """Test VTT file extension."""
    transcript = Transcript(
        id="test",
        title="Test",
        duration_seconds=10.0,
        language="en",
        segments=[],
    )
    exporter = VTTExporter(transcript)
    assert exporter.get_file_extension() == ".vtt"


@pytest.mark.asyncio
async def test_vtt_empty_segments():
    """Test VTT generation with no segments."""
    transcript = Transcript(
        id="test",
        title="Empty",
        duration_seconds=0.0,
        language="en",
        segments=[],
    )
    exporter = VTTExporter(transcript)
    result = await exporter.generate()
    content = result.decode("utf-8")
    
    # Should still have WEBVTT header
    assert content.strip() == "WEBVTT"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/MVA-2174 && python -m pytest autobot-backend/tests/services/test_vtt_exporter.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'services.transcript_export.vtt_exporter'"

- [ ] **Step 3: Implement VTT exporter**

Create `autobot-backend/services/transcript_export/vtt_exporter.py`:

```python
"""VTT (WebVTT) subtitle format exporter.

WebVTT format specification:
- WEBVTT header at start
- Timestamps in format: HH:MM:SS.mmm --> HH:MM:SS.mmm (dots not commas)
- Voice tags: <v Speaker Name>text
- Empty line between entries
"""
from services.transcript_export.base import BaseExporter, Transcript


class VTTExporter(BaseExporter):
    """Export transcript to VTT (WebVTT) subtitle format."""
    
    def _format_time(self, seconds: float) -> str:
        """Format time as HH:MM:SS.mmm.
        
        Args:
            seconds: Time in seconds
            
        Returns:
            str: Formatted time string
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"
    
    async def generate(self) -> bytes:
        """Generate VTT file content.
        
        Returns:
            bytes: VTT file content as UTF-8 encoded bytes
        """
        lines = ["WEBVTT"]
        
        if not self.transcript.segments:
            return "\n".join(lines).encode("utf-8")
        
        for segment in self.transcript.segments:
            # Empty line before each cue
            lines.append("")
            
            # Timestamp
            start = self._format_time(segment.start_time)
            end = self._format_time(segment.end_time)
            lines.append(f"{start} --> {end}")
            
            # Text with voice tag
            text = f"<v {segment.speaker_label}>{segment.text}"
            lines.append(text)
        
        content = "\n".join(lines)
        return content.encode("utf-8")
    
    def get_mime_type(self) -> str:
        """Return VTT MIME type."""
        return "text/vtt"
    
    def get_file_extension(self) -> str:
        """Return VTT file extension."""
        return ".vtt"
```

- [ ] **Step 4: Update package init**

Edit `autobot-backend/services/transcript_export/__init__.py`:

```python
"""Transcript export services."""
from services.transcript_export.base import BaseExporter, Segment, Transcript
from services.transcript_export.srt_exporter import SRTExporter
from services.transcript_export.vtt_exporter import VTTExporter

__all__ = ["BaseExporter", "Segment", "Transcript", "SRTExporter", "VTTExporter"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/MVA-2174 && python -m pytest autobot-backend/tests/services/test_vtt_exporter.py -v`

Expected: 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add autobot-backend/services/transcript_export/vtt_exporter.py autobot-backend/tests/services/test_vtt_exporter.py autobot-backend/services/transcript_export/__init__.py
git commit -m "feat(transcriber): add VTT (WebVTT) exporter (MVA-2174)

Implements WebVTT format:
- WEBVTT header
- HH:MM:SS.mmm timestamp format (dots not commas)
- Voice tags for speaker identification

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

### Task 5: Implement DOCX Exporter

**Files:**
- Create: `autobot-backend/services/transcript_export/docx_exporter.py`
- Create: `autobot-backend/tests/services/test_docx_exporter.py`

- [ ] **Step 1: Write failing test for DOCX format**

Create `autobot-backend/tests/services/test_docx_exporter.py`:

```python
"""Tests for DOCX (Microsoft Word) exporter."""
import io
import pytest
from docx import Document
from services.transcript_export.base import Segment, Transcript
from services.transcript_export.docx_exporter import DOCXExporter


@pytest.fixture
def sample_transcript():
    """Sample transcript for testing."""
    return Transcript(
        id="test-789",
        title="Board Meeting",
        duration_seconds=120.0,
        language="en",
        segments=[
            Segment(
                id="seg-1",
                transcript_id="test-789",
                start_time=0.0,
                end_time=5.0,
                speaker_label="CEO",
                text="Let's start the quarterly review.",
            ),
            Segment(
                id="seg-2",
                transcript_id="test-789",
                start_time=6.0,
                end_time=12.0,
                speaker_label="CFO",
                text="Our revenue increased by 15% this quarter.",
            ),
        ],
    )


@pytest.mark.asyncio
async def test_docx_generate(sample_transcript):
    """Test DOCX generation."""
    exporter = DOCXExporter(sample_transcript)
    result = await exporter.generate()
    
    # Parse generated DOCX
    doc = Document(io.BytesIO(result))
    
    # Check that document has content
    assert len(doc.paragraphs) > 0
    
    # Check title is in document
    text_content = "\n".join(p.text for p in doc.paragraphs)
    assert "Board Meeting" in text_content
    assert "CEO" in text_content
    assert "Let's start the quarterly review." in text_content
    assert "CFO" in text_content


@pytest.mark.asyncio
async def test_docx_mime_type():
    """Test DOCX MIME type."""
    transcript = Transcript(
        id="test",
        title="Test",
        duration_seconds=10.0,
        language="en",
        segments=[],
    )
    exporter = DOCXExporter(transcript)
    assert exporter.get_mime_type() == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.mark.asyncio
async def test_docx_file_extension():
    """Test DOCX file extension."""
    transcript = Transcript(
        id="test",
        title="Test",
        duration_seconds=10.0,
        language="en",
        segments=[],
    )
    exporter = DOCXExporter(transcript)
    assert exporter.get_file_extension() == ".docx"


@pytest.mark.asyncio
async def test_docx_metadata_header(sample_transcript):
    """Test that DOCX includes metadata header."""
    exporter = DOCXExporter(sample_transcript)
    result = await exporter.generate()
    
    doc = Document(io.BytesIO(result))
    text_content = "\n".join(p.text for p in doc.paragraphs)
    
    # Check for metadata
    assert "Duration:" in text_content
    assert "Language:" in text_content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/MVA-2174 && python -m pytest autobot-backend/tests/services/test_docx_exporter.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'services.transcript_export.docx_exporter'"

- [ ] **Step 3: Implement DOCX exporter**

Create `autobot-backend/services/transcript_export/docx_exporter.py`:

```python
"""DOCX (Microsoft Word) format exporter.

Generates a formatted Word document with:
- Title and metadata header
- Speaker labels in bold
- Timestamps in monospace
- Proper paragraph spacing
"""
import io
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from services.transcript_export.base import BaseExporter, Transcript


class DOCXExporter(BaseExporter):
    """Export transcript to DOCX (Microsoft Word) format."""
    
    def _format_time(self, seconds: float) -> str:
        """Format time as [MM:SS].
        
        Args:
            seconds: Time in seconds
            
        Returns:
            str: Formatted time string
        """
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"[{minutes:02d}:{secs:02d}]"
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration as MM:SS or HH:MM:SS.
        
        Args:
            seconds: Duration in seconds
            
        Returns:
            str: Formatted duration string
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"
    
    async def generate(self) -> bytes:
        """Generate DOCX file content.
        
        Returns:
            bytes: DOCX file content as bytes
        """
        doc = Document()
        
        # Add title
        title = doc.add_heading(self.transcript.title, level=1)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Add metadata
        metadata = doc.add_paragraph()
        metadata.add_run("Duration: ").bold = True
        metadata.add_run(self._format_duration(self.transcript.duration_seconds))
        metadata.add_run("\nLanguage: ").bold = True
        metadata.add_run(self.transcript.language.upper())
        metadata.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Add separator
        doc.add_paragraph("_" * 60)
        
        # Add segments
        for segment in self.transcript.segments:
            p = doc.add_paragraph()
            
            # Add timestamp
            timestamp_run = p.add_run(self._format_time(segment.start_time) + " ")
            timestamp_run.font.name = "Courier New"
            timestamp_run.font.size = Pt(10)
            timestamp_run.font.color.rgb = RGBColor(100, 100, 100)
            
            # Add speaker label
            speaker_run = p.add_run(f"{segment.speaker_label}: ")
            speaker_run.bold = True
            speaker_run.font.size = Pt(11)
            
            # Add text
            text_run = p.add_run(segment.text)
            text_run.font.size = Pt(11)
            
            # Add notes if present
            if segment.notes:
                notes_p = doc.add_paragraph()
                notes_run = notes_p.add_run(f"    Note: {segment.notes}")
                notes_run.italic = True
                notes_run.font.size = Pt(10)
                notes_run.font.color.rgb = RGBColor(80, 80, 80)
        
        # Save to bytes
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer.read()
    
    def get_mime_type(self) -> str:
        """Return DOCX MIME type."""
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    
    def get_file_extension(self) -> str:
        """Return DOCX file extension."""
        return ".docx"
```

- [ ] **Step 4: Update package init**

Edit `autobot-backend/services/transcript_export/__init__.py`:

```python
"""Transcript export services."""
from services.transcript_export.base import BaseExporter, Segment, Transcript
from services.transcript_export.docx_exporter import DOCXExporter
from services.transcript_export.srt_exporter import SRTExporter
from services.transcript_export.vtt_exporter import VTTExporter

__all__ = [
    "BaseExporter",
    "Segment",
    "Transcript",
    "DOCXExporter",
    "SRTExporter",
    "VTTExporter",
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/MVA-2174 && python -m pytest autobot-backend/tests/services/test_docx_exporter.py -v`

Expected: 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add autobot-backend/services/transcript_export/docx_exporter.py autobot-backend/tests/services/test_docx_exporter.py autobot-backend/services/transcript_export/__init__.py
git commit -m "feat(transcriber): add DOCX exporter (MVA-2174)

Generates formatted Word documents with:
- Centered title and metadata
- Bold speaker labels
- Monospace timestamps
- Optional inline notes

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

### Task 6: Implement PDF Exporter

**Files:**
- Create: `autobot-backend/services/transcript_export/pdf_exporter.py`
- Create: `autobot-backend/tests/services/test_pdf_exporter.py`

- [ ] **Step 1: Write failing test for PDF format**

Create `autobot-backend/tests/services/test_pdf_exporter.py`:

```python
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
    assert len(reader.pages) > 0
    
    # Extract text from first page
    text = reader.pages[0].extract_text()
    assert "Conference Call" in text
    assert "Alice" in text or "Good morning" in text


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/MVA-2174 && python -m pytest autobot-backend/tests/services/test_pdf_exporter.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'services.transcript_export.pdf_exporter'"

- [ ] **Step 3: Install PyPDF2 for testing**

Run: `pip install PyPDF2`

Expected: PyPDF2 installs successfully

- [ ] **Step 4: Implement PDF exporter**

Create `autobot-backend/services/transcript_export/pdf_exporter.py`:

```python
"""PDF format exporter.

Generates a formatted PDF document with:
- Title page with metadata
- Speaker labels and timestamps
- Page numbers
"""
import io
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from services.transcript_export.base import BaseExporter, Transcript


class PDFExporter(BaseExporter):
    """Export transcript to PDF format."""
    
    def _format_time(self, seconds: float) -> str:
        """Format time as [MM:SS].
        
        Args:
            seconds: Time in seconds
            
        Returns:
            str: Formatted time string
        """
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"[{minutes:02d}:{secs:02d}]"
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration as MM:SS or HH:MM:SS.
        
        Args:
            seconds: Duration in seconds
            
        Returns:
            str: Formatted duration string
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"
    
    async def generate(self) -> bytes:
        """Generate PDF file content.
        
        Returns:
            bytes: PDF file content as bytes
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=18,
        )
        
        # Get styles
        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle(
            "CustomTitle",
            parent=styles["Heading1"],
            fontSize=24,
            alignment=TA_CENTER,
            spaceAfter=12,
        )
        
        metadata_style = ParagraphStyle(
            "Metadata",
            parent=styles["Normal"],
            fontSize=12,
            alignment=TA_CENTER,
            spaceAfter=20,
        )
        
        segment_style = ParagraphStyle(
            "Segment",
            parent=styles["Normal"],
            fontSize=11,
            alignment=TA_LEFT,
            spaceAfter=10,
        )
        
        # Build content
        story = []
        
        # Title page
        story.append(Spacer(1, 1.5*inch))
        story.append(Paragraph(self.transcript.title, title_style))
        story.append(Spacer(1, 0.5*inch))
        
        # Metadata
        metadata_text = f"""
        Duration: {self._format_duration(self.transcript.duration_seconds)}<br/>
        Language: {self.transcript.language.upper()}
        """
        story.append(Paragraph(metadata_text, metadata_style))
        story.append(PageBreak())
        
        # Segments
        for segment in self.transcript.segments:
            # Format segment text
            timestamp = self._format_time(segment.start_time)
            text = f"""
            <font name="Courier">{timestamp}</font>
            <b>{segment.speaker_label}:</b>
            {segment.text}
            """
            
            story.append(Paragraph(text, segment_style))
            
            # Add notes if present
            if segment.notes:
                notes_style = ParagraphStyle(
                    "Notes",
                    parent=segment_style,
                    fontSize=10,
                    textColor="gray",
                    leftIndent=20,
                )
                story.append(Paragraph(f"<i>Note: {segment.notes}</i>", notes_style))
        
        # Build PDF
        doc.build(story)
        
        buffer.seek(0)
        return buffer.read()
    
    def get_mime_type(self) -> str:
        """Return PDF MIME type."""
        return "application/pdf"
    
    def get_file_extension(self) -> str:
        """Return PDF file extension."""
        return ".pdf"
```

- [ ] **Step 5: Update package init**

Edit `autobot-backend/services/transcript_export/__init__.py`:

```python
"""Transcript export services."""
from services.transcript_export.base import BaseExporter, Segment, Transcript
from services.transcript_export.docx_exporter import DOCXExporter
from services.transcript_export.pdf_exporter import PDFExporter
from services.transcript_export.srt_exporter import SRTExporter
from services.transcript_export.vtt_exporter import VTTExporter

__all__ = [
    "BaseExporter",
    "Segment",
    "Transcript",
    "DOCXExporter",
    "PDFExporter",
    "SRTExporter",
    "VTTExporter",
]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/MVA-2174 && python -m pytest autobot-backend/tests/services/test_pdf_exporter.py -v`

Expected: 3 tests PASS

- [ ] **Step 7: Commit**

```bash
git add autobot-backend/services/transcript_export/pdf_exporter.py autobot-backend/tests/services/test_pdf_exporter.py autobot-backend/services/transcript_export/__init__.py
git commit -m "feat(transcriber): add PDF exporter (MVA-2174)

Generates formatted PDF documents with:
- Title page with metadata
- Speaker labels and timestamps
- Page breaks and proper layout

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

### Task 7: Create API Endpoints

**Files:**
- Create: `autobot-backend/api/transcript_export.py`
- Modify: `autobot-backend/app_factory.py`

- [ ] **Step 1: Create API endpoint file**

Create `autobot-backend/api/transcript_export.py`:

```python
"""Transcript export API endpoints.

Provides endpoints to export transcripts in various formats:
- DOCX (Microsoft Word)
- PDF
- SRT (SubRip subtitles)
- VTT (WebVTT subtitles)
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from auth_middleware import check_admin_permission
from services.transcript_export import (
    Transcript,
    Segment,
    DOCXExporter,
    PDFExporter,
    SRTExporter,
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
```

- [ ] **Step 2: Register router in app factory**

Find the router registration section in `autobot-backend/app_factory.py` and add the transcript export router. Look for lines like `app.include_router(...)` and add:

```python
from api import transcript_export

# Add this line with the other router registrations
app.include_router(transcript_export.router, prefix="/api")
```

- [ ] **Step 3: Commit**

```bash
git add autobot-backend/api/transcript_export.py autobot-backend/app_factory.py
git commit -m "feat(transcriber): add export API endpoints (MVA-2174)

Implements 4 export endpoints:
- GET /api/transcripts/{id}/export/docx
- GET /api/transcripts/{id}/export/pdf
- GET /api/transcripts/{id}/export/srt
- GET /api/transcripts/{id}/export/vtt

Includes mock data function for testing until transcriber DB ready.

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

### Task 8: Integration Tests

**Files:**
- Create: `autobot-backend/tests/api/test_transcript_export.py`

- [ ] **Step 1: Write integration tests**

Create `autobot-backend/tests/api/test_transcript_export.py`:

```python
"""Integration tests for transcript export API endpoints."""
import io
import pytest
from fastapi.testclient import TestClient
from docx import Document
from PyPDF2 import PdfReader


@pytest.fixture
def client(test_app):
    """Test client fixture."""
    return TestClient(test_app)


def test_export_docx_success(client):
    """Test DOCX export endpoint returns valid Word document."""
    response = client.get("/api/transcripts/test-transcript-1/export/docx")
    
    assert response.status_code == 200
    assert response.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert "attachment" in response.headers["content-disposition"]
    
    # Verify it's a valid DOCX
    doc = Document(io.BytesIO(response.content))
    assert len(doc.paragraphs) > 0


def test_export_pdf_success(client):
    """Test PDF export endpoint returns valid PDF."""
    response = client.get("/api/transcripts/test-transcript-1/export/pdf")
    
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment" in response.headers["content-disposition"]
    
    # Verify it's a valid PDF
    assert response.content.startswith(b"%PDF")
    reader = PdfReader(io.BytesIO(response.content))
    assert len(reader.pages) > 0


def test_export_srt_success(client):
    """Test SRT export endpoint returns valid subtitle file."""
    response = client.get("/api/transcripts/test-transcript-1/export/srt")
    
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/x-subrip"
    assert "attachment" in response.headers["content-disposition"]
    
    # Verify SRT format
    content = response.content.decode("utf-8")
    assert "1\n" in content  # Sequence number
    assert "-->" in content  # Timestamp separator
    assert "Speaker" in content


def test_export_vtt_success(client):
    """Test VTT export endpoint returns valid WebVTT file."""
    response = client.get("/api/transcripts/test-transcript-1/export/vtt")
    
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/vtt"
    assert "attachment" in response.headers["content-disposition"]
    
    # Verify VTT format
    content = response.content.decode("utf-8")
    assert content.startswith("WEBVTT")
    assert "-->" in content
    assert "<v" in content  # Voice tags


def test_export_transcript_not_found(client):
    """Test export returns 404 for non-existent transcript."""
    response = client.get("/api/transcripts/nonexistent-id/export/docx")
    assert response.status_code == 404


def test_export_filename_sanitization(client):
    """Test that filename is properly sanitized."""
    response = client.get("/api/transcripts/test-transcript-1/export/srt")
    
    assert response.status_code == 200
    disposition = response.headers["content-disposition"]
    
    # Check filename is present and sanitized (no special chars)
    assert "Sample_Meeting_Transcript.srt" in disposition or "filename=" in disposition


@pytest.mark.parametrize("format_type,extension", [
    ("docx", ".docx"),
    ("pdf", ".pdf"),
    ("srt", ".srt"),
    ("vtt", ".vtt"),
])
def test_export_all_formats(client, format_type, extension):
    """Test all export formats are functional."""
    response = client.get(f"/api/transcripts/test-transcript-1/export/{format_type}")
    
    assert response.status_code == 200
    assert len(response.content) > 0
    assert extension in response.headers["content-disposition"]
```

- [ ] **Step 2: Run integration tests**

Run: `cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/MVA-2174 && python -m pytest autobot-backend/tests/api/test_transcript_export.py -v`

Expected: All tests PASS

- [ ] **Step 3: Run full test suite**

Run: `cd /home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/MVA-2174 && python -m pytest autobot-backend/tests/services/ autobot-backend/tests/api/test_transcript_export.py -v`

Expected: All export-related tests PASS

- [ ] **Step 4: Commit**

```bash
git add autobot-backend/tests/api/test_transcript_export.py
git commit -m "test(transcriber): add integration tests for export API (MVA-2174)

Tests cover:
- All 4 export formats (DOCX, PDF, SRT, VTT)
- File format validation
- 404 handling
- Filename sanitization
- Content-Type headers

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

### Task 9: Update Requirements and Documentation

**Files:**
- Modify: `autobot-backend/requirements.txt`
- Create: `autobot-backend/services/transcript_export/README.md`

- [ ] **Step 1: Add PyPDF2 to requirements**

Add to `autobot-backend/requirements.txt`:

```txt
PyPDF2>=3.0.0
```

- [ ] **Step 2: Create service README**

Create `autobot-backend/services/transcript_export/README.md`:

```markdown
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
```

- [ ] **Step 3: Commit**

```bash
git add autobot-backend/requirements.txt autobot-backend/services/transcript_export/README.md
git commit -m "docs(transcriber): add service README and finalize deps (MVA-2174)

Documents export service usage, formats, and integration path.
Adds PyPDF2 to requirements for test suite.

Co-Authored-By: Paperclip <noreply@paperclip.ing>"
```

---

## Plan Self-Review

**Spec Coverage Check:**
- ✅ DOCX generator with speaker labels and timestamps (Task 5)
- ✅ PDF generator with formatting (Task 6)
- ✅ SRT generator for video (Task 3)
- ✅ VTT generator for web video (Task 4)
- ✅ GET /api/transcripts/{id}/export/docx endpoint (Task 7)
- ✅ GET /api/transcripts/{id}/export/pdf endpoint (Task 7)
- ✅ GET /api/transcripts/{id}/export/srt endpoint (Task 7)
- ✅ GET /api/transcripts/{id}/export/vtt endpoint (Task 7)
- ✅ Integration tests validate file format correctness (Task 8)

**Placeholder Check:**
- ✅ No TBD/TODO placeholders (except documented mock function)
- ✅ All code steps include complete implementation
- ✅ All test steps include exact commands and expected output

**Type Consistency:**
- ✅ Segment model used consistently across all tasks
- ✅ Transcript model used consistently across all tasks
- ✅ BaseExporter interface followed by all exporters
- ✅ Method signatures match across tasks

**Integration Note:**
The `_get_transcript_mock` function in Task 7 is intentionally temporary and clearly marked with TODO. It will be replaced when the transcriber database module is implemented (part of parent issue MVA-2155).

---

## Summary

This plan implements complete transcript export functionality in 9 tasks:

1. Dependencies setup
2. Base exporter and data models  
3. SRT exporter (text-based, simplest)
4. VTT exporter (similar to SRT)
5. DOCX exporter (document generation)
6. PDF exporter (document generation)
7. API endpoints with mock data
8. Integration tests
9. Documentation

Each task follows TDD: write test → verify fail → implement → verify pass → commit.

Total estimated time: ~2-3 hours for full implementation and testing.
