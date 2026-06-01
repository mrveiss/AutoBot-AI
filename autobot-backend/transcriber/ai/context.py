# autobot-backend/transcriber/ai/context.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Build transcript context string for LLM analysis."""


def _fmt_ts(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def build_context(segments: list[dict], *, max_chars: int = 30_000) -> str:
    lines = []
    total = 0
    for seg in segments:
        line = f"[{seg['speaker_name']}, {_fmt_ts(seg['start'])}] {seg['text']}"
        if total + len(line) > max_chars:
            lines.append(f"\n... (transcript truncated at {max_chars} characters)")
            break
        lines.append(line)
        total += len(line)
    return "\n".join(lines)
