# autobot-backend/transcriber/export/vtt_export.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Export transcript segments to WebVTT (.vtt) format."""


def _fmt_vtt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def segments_to_vtt(segments: list[dict], *, include_speaker: bool = True) -> str:
    lines = ["WEBVTT", ""]
    for seg in segments:
        start = _fmt_vtt_time(seg["start"])
        end = _fmt_vtt_time(seg["end"])
        text = f"{seg['speaker']}: {seg['text']}" if include_speaker else seg["text"]
        lines.append(f"{start} --> {end}\n{text}\n")
    return "\n".join(lines)
