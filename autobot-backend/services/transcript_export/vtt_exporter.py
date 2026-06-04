"""VTT (WebVTT) subtitle format exporter.

WebVTT format specification:
- WEBVTT header at start
- Timestamps in format: HH:MM:SS.mmm --> HH:MM:SS.mmm (dots not commas)
- Voice tags: <v Speaker Name>text
- Empty line between entries
"""

from services.transcript_export.base import BaseExporter


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
