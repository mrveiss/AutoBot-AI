# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""SRT (SubRip) subtitle format exporter.

SRT format specification:
- Sequence numbers starting at 1
- Timestamps in format: HH:MM:SS,mmm --> HH:MM:SS,mmm
- Speaker label and text
- Empty line between entries
"""

from services.transcript_export.base import BaseExporter


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
