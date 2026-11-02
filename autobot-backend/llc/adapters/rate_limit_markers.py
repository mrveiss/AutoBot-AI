# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Provider rate-limit / quota detection for subprocess-adapter output (GH#9773, #20267).

The scanned tail of a stream-json transcript also carries model text and tool output,
so a word like "quota" there says nothing about the run. JSONL events are therefore
read by structure: only an error-bearing field of an error-shaped event counts.
Lines that are not JSON (stderr, exception strings, a line cut by the tail boundary)
are matched with error-shaped patterns only.
"""

from __future__ import annotations

import json
import re
from typing import Any

# Phrases that identify a provider rate-limit or quota error.  ``rate_limit_event`` is
# deliberately absent: the CLI emits it on successful runs too (#20267).
_RL_KEYWORDS: frozenset[str] = frozenset(
    {"rate_limit_error", "rate limit", "too many requests", "quota", "overloaded", "overloaded_error", "capacity_error"}
)
_RL_PHRASE_RE = re.compile(r"\b(?:" + "|".join(re.escape(k) for k in sorted(_RL_KEYWORDS)) + r")\b", re.IGNORECASE)

# 429 / 529 only as a standalone number after an error-context word ("HTTP 529",
# "status: 429", ``"api_error_status":429``); never inside a uuid, cost or count.
_RL_CODE_RE = re.compile(
    r"(?:http|status|status_code|error|code)[\"']?\s*[:=]?\s*[\"']?(?:429|529)(?![\w.\-])",
    re.IGNORECASE,
)

# Free text: the unambiguous phrases, plus "quota"/"overloaded" only when worded as an error.
_RL_PLAIN_RE = re.compile(
    r"\b(?:rate_limit_error|capacity_error|overloaded_error|too many requests|rate limit)\b"
    r"|\bquota (?:exceeded|exhausted|reached)\b"
    r"|\b(?:exceeded|exhausted) (?:your |the |its )?(?:\w+ )?quota\b"
    r"|\b(?:api|server|service|model|error)\b[^\n]{0,40}\boverloaded\b"
    r"|\boverloaded\b[^\n]{0,20}(?:error|please retry)",
    re.IGNORECASE,
)
_RL_STATUSES = (429, 529)


def _api_error_text(event: dict[str, Any]) -> list[str]:
    """Text of the CLI's synthetic API-error assistant message (it carries no model text)."""
    blocks = (event.get("message") or {}).get("content") or []
    return [b["text"] for b in blocks if isinstance(b, dict) and isinstance(b.get("text"), str)]


def _error_fields(event: dict[str, Any]) -> list[str]:
    """The error-bearing strings of one JSONL event; ``[]`` for ordinary events."""
    kind, out = event.get("type"), []
    if kind == "result" and event.get("is_error"):
        out.append(str(event.get("result") or ""))
    err = event.get("error")
    if isinstance(err, dict):
        out += [str(err.get("type") or ""), str(err.get("message") or "")]
    elif isinstance(err, str):
        out.append(err.replace("_", " "))
    if kind == "error":
        out.append(str(event.get("message") or ""))
    if kind == "assistant" and event.get("is_api_error_message"):
        out += _api_error_text(event)
    return out


def _event_status(event: dict[str, Any]) -> Any:
    err = event.get("error")
    return event.get("api_error_status") or (err.get("status") if isinstance(err, dict) else None)


def _event_matches(event: dict[str, Any]) -> bool:
    if _event_status(event) in _RL_STATUSES:
        return True
    return any(_RL_PHRASE_RE.search(t) or _RL_CODE_RE.search(t) for t in _error_fields(event))


def _line_matches(line: str) -> bool:
    try:
        event = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return bool(_RL_PLAIN_RE.search(line) or _RL_CODE_RE.search(line))
    return _event_matches(event) if isinstance(event, dict) else False


def is_rate_limit_output(text: str | None) -> bool:
    """Return True if *text* contains a provider rate-limit signal.

    Apply only to error text or a failure tail (see ``claude_code_adapter._status``).
    JSONL events count only through their error fields; other lines through
    error-shaped patterns. Numeric codes need an error context, never a bare substring.
    """
    if not text:
        return False
    return any(_line_matches(line) for line in text.splitlines() if line.strip())
