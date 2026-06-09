# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/transcriber/export/srt_export.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Export transcript segments to SubRip (.srt) format."""


def _fmt_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def segments_to_srt(segments: list[dict], *, include_speaker: bool = True) -> str:
    if not segments:
        return ""
    lines = []
    for i, seg in enumerate(segments, start=1):
        start = _fmt_srt_time(seg["start"])
        end = _fmt_srt_time(seg["end"])
        text = f"{seg['speaker']}: {seg['text']}" if include_speaker else seg["text"]
        lines.append(f"{i}\n{start} --> {end}\n{text}\n")
    return "\n".join(lines)
