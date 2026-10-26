# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Exact find-and-replace for the filesystem MCP ``edit_file`` tool (#19463).

Every edit must match exactly ``expected_replacements`` times (default 1). A miss
or a count mismatch raises a 400 naming the edit, and for a miss the closest span
in the file (difflib similarity, line range, short unified diff) so the model can
retry with the exact text. A fuzzy match is never applied. Edits run against a
working copy, so a multi-edit call is all-or-nothing: the caller writes only when
every edit succeeded. A file whose every line ends CRLF is matched LF-normalised
and written back CRLF; any other file is matched as-is.

The closest-span search is bounded: an ``old_text`` longer than
``EDIT_MISS_OLD_TEXT_MAX_CHARS`` is not searched at all, and the search stops
after ``EDIT_MISS_MAX_WINDOWS`` line windows or ``EDIT_MISS_SEARCH_BUDGET_SECONDS``,
whichever comes first. A capped search still
reports the miss and says the search was capped. Async callers use
``apply_edits_off_loop``, which runs the edits via ``asyncio.to_thread``.
"""

from __future__ import annotations

import asyncio
import difflib
import os
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

from api.schemas_filesystem_edit import EditSpec
from autobot_shared.env_utils import env_float_clamped, env_int_clamped
from autobot_shared.logging_manager import get_logger
from autobot_shared.secret_redaction import redact_mapping
from autobot_shared.security.redaction import sanitize_log_value
from utils.catalog_http_exceptions import raise_invalid_input

logger = get_logger(__name__)

CRLF = "\r\n"
LF = "\n"
#: Lines of unified diff returned with a miss: enough to show the misquote, short enough for a model's context.
MISS_DIFF_MAX_LINES = 20
#: Longest file extension written to the edit-miss log event.
_EXTENSION_LOG_MAX_CHARS = 16
#: Longest ``old_text`` the closest-span search runs for; a longer miss reports no span.
EDIT_MISS_OLD_TEXT_MAX_CHARS = env_int_clamped("AUTOBOT_EDIT_MISS_OLD_TEXT_MAX_CHARS", 2000, min_v=1)
#: Most line windows the closest-span search compares before it stops and says so.
EDIT_MISS_MAX_WINDOWS = env_int_clamped("AUTOBOT_EDIT_MISS_MAX_WINDOWS", 2000, min_v=1)
#: Wall-clock budget for one closest-span search; a window shape the ratio bounds cannot prune hits this.
EDIT_MISS_SEARCH_BUDGET_SECONDS = env_float_clamped(
    "AUTOBOT_EDIT_MISS_SEARCH_BUDGET_SECONDS", 1.0, positive_finite=True
)


@dataclass(frozen=True)
class ClosestSpan:
    """The file span most similar to a missed ``old_text`` (1-based, inclusive)."""

    similarity: float
    start_line: int
    end_line: int
    text: str
    #: Why the search stopped early, or None when every window was compared.
    capped: Optional[str] = None


def detect_line_ending(content: str) -> str:
    """Return CRLF when every newline in *content* is CRLF, else LF."""
    lf_count = content.count(LF)
    if lf_count and content.count(CRLF) == lf_count:
        return CRLF
    return LF


def find_closest_span(content: str, old_text: str) -> ClosestSpan:
    """Slide an ``old_text``-sized line window over *content*; return the best match.

    Bounded by EDIT_MISS_OLD_TEXT_MAX_CHARS, EDIT_MISS_MAX_WINDOWS and
    EDIT_MISS_SEARCH_BUDGET_SECONDS; a capped search sets ``capped`` to the reason.
    """
    if len(old_text) > EDIT_MISS_OLD_TEXT_MAX_CHARS:
        reason = f"old_text is longer than {EDIT_MISS_OLD_TEXT_MAX_CHARS} characters"
        return ClosestSpan(0.0, 0, 0, "", capped=reason)
    lines = content.split(LF)
    width = max(1, min(len(lines), old_text.count(LF) + 1))
    windows = len(lines) - width + 1
    best, compared = _best_window(lines, width, old_text, min(windows, EDIT_MISS_MAX_WINDOWS))
    if compared < windows:
        reason = f"compared only the first {compared} of {windows} line windows"
        best = ClosestSpan(best.similarity, best.start_line, best.end_line, best.text, capped=reason)
    return best


def _best_window(lines: List[str], width: int, old_text: str, windows: int) -> Tuple[ClosestSpan, int]:
    """Compare up to *windows* windows within the time budget; return (best, windows compared).

    The cheap ratio upper bounds skip windows that cannot beat the best so far.
    """
    deadline = time.monotonic() + EDIT_MISS_SEARCH_BUDGET_SECONDS
    matcher = difflib.SequenceMatcher(None, autojunk=False)
    matcher.set_seq2(old_text)
    best = ClosestSpan(0.0, 1, width, LF.join(lines[:width]))
    for start in range(windows):
        if time.monotonic() > deadline:
            return best, start
        candidate = LF.join(lines[start : start + width])
        matcher.set_seq1(candidate)
        if matcher.real_quick_ratio() <= best.similarity or matcher.quick_ratio() <= best.similarity:
            continue
        ratio = matcher.ratio()
        if ratio > best.similarity:
            best = ClosestSpan(ratio, start + 1, start + width, candidate)
    return best, windows


def _short_diff(span: ClosestSpan, old_text: str) -> str:
    """Unified diff from the file span to ``old_text``, capped at MISS_DIFF_MAX_LINES."""
    diff = list(
        difflib.unified_diff(
            span.text.split(LF),
            old_text.split(LF),
            fromfile=f"file lines {span.start_line}-{span.end_line}",
            tofile="old_text",
            lineterm="",
            n=1,
        )
    )
    if len(diff) > MISS_DIFF_MAX_LINES:
        diff = diff[:MISS_DIFF_MAX_LINES] + [f"... [{len(diff) - MISS_DIFF_MAX_LINES} more diff lines]"]
    return LF.join(diff)


def _log_edit_miss(path: str, index: int, old_text: str, content: str, **fields) -> None:
    """Emit one structured edit-miss event: shapes and scores only, never content."""
    extension = os.path.splitext(path)[1].lower()
    event = {
        "event": "edit_file.edit_miss",
        "extension": sanitize_log_value(extension, max_chars=_EXTENSION_LOG_MAX_CHARS),
        "edit_index": index,
        "old_text_len": len(old_text),
        "file_len": len(content),
        **fields,
    }
    safe_event = redact_mapping(event)
    logger.warning("edit_file edit miss: %s", safe_event, extra={"edit_miss": safe_event})


def _expected_count(edit: EditSpec, index: int) -> int:
    """Validate the optional ``expected_replacements`` of one edit (default 1)."""
    expected = edit.get("expected_replacements", 1)
    if isinstance(expected, bool) or not isinstance(expected, int) or expected < 1:
        raise_invalid_input("edits", f"edit {index}: expected_replacements must be an integer >= 1")
    return expected


def _edit_texts(edit: EditSpec, index: int, line_ending: str) -> Tuple[str, str]:
    """Return one edit's (old_text, new_text), LF-normalised for a CRLF file."""
    old_text = edit.get("old_text", edit.get("oldText"))
    new_text = edit.get("new_text", edit.get("newText"))
    if not isinstance(old_text, str) or not old_text or not isinstance(new_text, str):
        raise_invalid_input("edits", f"edit {index}: old_text must be a non-empty string and new_text a string")
    if line_ending == CRLF:
        return old_text.replace(CRLF, LF), new_text.replace(CRLF, LF)
    return old_text, new_text


def _miss_message(index: int, span: ClosestSpan, old_text: str) -> str:
    """The 400 detail for a miss: closest span and diff, plus the cap when one was hit."""
    head = f"edit {index}: old_text not found"
    tail = "No edits were applied; retry with the exact text."
    if span.capped and not span.text:
        return f"{head}; closest-span search capped ({span.capped}), no span reported. {tail}"
    capped = f" Closest-span search capped ({span.capped})." if span.capped else ""
    return (
        f"{head}; closest span is lines {span.start_line}-{span.end_line} "
        f"(similarity {span.similarity:.2f}).{capped} {tail}\n{_short_diff(span, old_text)}"
    )


def _raise_miss(path: str, index: int, old_text: str, content: str) -> None:
    """Report a missed edit with its closest span; nothing is applied."""
    span = find_closest_span(content, old_text)
    _log_edit_miss(
        path,
        index,
        old_text,
        content,
        reason="not_found",
        similarity=round(span.similarity, 3),
        search_capped=span.capped is not None,
    )
    raise_invalid_input("edits", _miss_message(index, span, old_text))


def _apply_one(content: str, edit: EditSpec, index: int, path: str, line_ending: str) -> Tuple[str, dict]:
    """Apply one exact edit to *content* or raise; returns (content, change record)."""
    old_text, new_text = _edit_texts(edit, index, line_ending)
    expected = _expected_count(edit, index)
    count = content.count(old_text)
    if count == 0:
        _raise_miss(path, index, old_text, content)
    if count != expected:
        _log_edit_miss(path, index, old_text, content, reason="count_mismatch", occurrences=count, expected=expected)
        raise_invalid_input(
            "edits",
            f"edit {index}: old_text occurs {count} times but expected_replacements is {expected}. "
            "No edits were applied; add surrounding context or set expected_replacements.",
        )
    change = {"old": old_text[:50], "new": new_text[:50], "replacements": count}
    return content.replace(old_text, new_text), change


def apply_edits_to_content(content: str, edits: List[EditSpec], path: str) -> Tuple[str, List[dict]]:
    """Apply every edit exactly or raise before any is kept (all-or-nothing).

    *content* is the file as read with ``newline=''``; the result keeps its
    line-ending style, so the caller writes it back with ``newline=''``.
    """
    line_ending = detect_line_ending(content)
    working = content.replace(CRLF, LF) if line_ending == CRLF else content
    changes = []
    for index, edit in enumerate(edits):
        working, change = _apply_one(working, edit, index, path, line_ending)
        changes.append(change)
    return (working.replace(LF, CRLF) if line_ending == CRLF else working), changes


async def apply_edits_off_loop(content: str, edits: List[EditSpec], path: str) -> Tuple[str, List[dict]]:
    """``apply_edits_to_content`` in a worker thread: a miss's span search is CPU-bound."""
    return await asyncio.to_thread(apply_edits_to_content, content, edits, path)
