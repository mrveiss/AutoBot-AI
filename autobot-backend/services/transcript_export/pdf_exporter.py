"""PDF format exporter.

Generates a formatted PDF document with:
- Title page with metadata
- Speaker labels and timestamps
- Page numbers
"""

import io

from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

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
        story.append(Spacer(1, 1.5 * inch))
        story.append(Paragraph(self.transcript.title, title_style))
        story.append(Spacer(1, 0.5 * inch))

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
