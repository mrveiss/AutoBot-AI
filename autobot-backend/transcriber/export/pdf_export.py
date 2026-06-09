# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/transcriber/export/pdf_export.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Export transcript to PDF via HTML→WeasyPrint."""

import html as html_lib

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_SPEAKER_COLORS = ["#1a73e8", "#d93425", "#188a38", "#fbbc04", "#8a2be2"]


def _fmt_ts(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def build_pdf(
    title: str,
    segments: list[dict],
    *,
    include_timestamps: bool,
    include_notes: bool,
    include_speaker_names: bool,
) -> bytes:
    from weasyprint import HTML

    speaker_index: dict[str, int] = {}
    rows = []
    for seg in segments:
        speaker = seg.get("speaker_name", "Unknown")
        if speaker not in speaker_index:
            speaker_index[speaker] = len(speaker_index)
        color = _SPEAKER_COLORS[speaker_index[speaker] % len(_SPEAKER_COLORS)]
        ts = f'<span class="ts">[{_fmt_ts(seg["start"])} → {_fmt_ts(seg["end"])}]</span> ' if include_timestamps else ""
        spk = (
            f'<span class="speaker" style="color:{color}">{html_lib.escape(speaker)}</span> '
            if include_speaker_names
            else ""
        )
        notes_html = ""
        if include_notes and seg.get("notes"):
            items = "".join(f'<li>{html_lib.escape(n["content"])}</li>' for n in seg["notes"])
            notes_html = f'<ul class="notes">{items}</ul>'
        rows.append(f'<p>{spk}{ts}{html_lib.escape(seg["text"])}{notes_html}</p>')

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body {{font-family: sans-serif; font-size: 11pt; margin: 2cm;}}
  h1 {{font-size: 16pt;}}
  .speaker {{font-weight: bold;}}
  .ts {{font-style: italic; color: #666; font-size: 9pt;}}
  .notes {{color: #555; font-size: 9pt; margin: 2px 0 6px 1em;}}
</style></head>
<body><h1>{html_lib.escape(title)}</h1>
{"".join(rows)}
</body></html>"""
    return HTML(string=html).write_pdf()
