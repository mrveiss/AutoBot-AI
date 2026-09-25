# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Where a streamed answer changes between response, thought and planning.

The model marks its reasoning with `[THOUGHT]...[/THOUGHT]` and
`[PLANNING]...[/PLANNING]`, and the streaming path splits an answer into
separate messages at those boundaries, typing each segment so the UI can badge
reasoning differently from the answer.

THE DEFECT THIS MODULE EXISTS TO FIX (#17513). The markers were matched with a
plain regex over the whole accumulated text, so a marker the model merely
QUOTED was indistinguishable from one it emitted. A reply containing::

    - Thinking tags (`[THOUGHT]`, `[PLANNING]`) requirements

was cut into three segments at those two quoted markers. The user saw one answer
arrive as two messages -- the first ending mid-clause at ``- Thinking tags (``,
the second badged **Thought** and opening with the orphaned ``` `, ` ``` that had
sat between the markers, followed by a broken ``` `) requirements ```. The reply
was not escaped or corrupted in storage; the persisted text is intact. It was
*parsed* wrongly on the way to the screen.

It is self-triggering on its own subject: any answer that documents the markers,
shows them in a code block, or reads the system prompt back to the user breaks
the same way. That is how it was found.

WHY MASKING AND NOT A SMARTER REGEX. A regex that tries to exclude backticked
spans in one pass has to reason about nesting and about the unterminated span
that streaming always produces mid-emission. Blanking code regions to
equal-length runs of spaces keeps the two concerns apart: one function decides
what is code, the scanners stay trivial, and because the mask preserves length
every position found in the masked copy still indexes the original -- which
matters, because the segment boundary is used to slice the real text.

THE STREAMING CASE, which a naive mask gets wrong. Detection runs on text that
is still arriving, so when the model has emitted ``` `[THOUGHT] ``` the opening
backtick is present and the closing one is not. A mask that only handles CLOSED
spans would still see a bare marker and still split, one chunk before the span
completes -- and by then the message is already broken. So a trailing unclosed
backtick masks to the end of the text: a real marker arriving after a stray
backtick is missed for one chunk, which costs a late badge, where the opposite
error costs the user a severed reply.
"""

from __future__ import annotations

import re
from typing import Dict, FrozenSet

#: Segment types whose content is reasoning rather than answer.
BLOCK_CONTENT_TYPES: FrozenSet[str] = frozenset({"thought", "planning"})

THOUGHT_TAG_PATTERN = re.compile(r"\[THOUGHT\]", re.IGNORECASE)
THOUGHT_END_PATTERN = re.compile(r"\[/THOUGHT\]", re.IGNORECASE)
PLANNING_TAG_PATTERN = re.compile(r"\[PLANNING\]", re.IGNORECASE)
PLANNING_END_PATTERN = re.compile(r"\[/PLANNING\]", re.IGNORECASE)

#: Closed markdown code regions, longest delimiter first so a fence is consumed
#: whole rather than as three inline spans.
_CLOSED_CODE_REGION_RE = re.compile(r"```.*?```|~~~.*?~~~|``[^`]*``|`[^`\n]*`", re.DOTALL)

#: A backtick run with no partner, which streaming produces constantly.
_TRAILING_BACKTICK_RE = re.compile(r"`+[^`]*\Z", re.DOTALL)


def _blank(match: re.Match) -> str:
    """Spaces of the same width, so positions survive masking."""
    return " " * (match.end() - match.start())


def mask_code_regions(text: str) -> str:
    """*text* with markdown code regions blanked, same length.

    Closed spans and fences go first; whatever unclosed backtick run remains is
    then masked to the end of the string, because during streaming the closing
    delimiter has not arrived yet (see the module docstring).
    """
    masked = _CLOSED_CODE_REGION_RE.sub(_blank, text)
    if masked.count("`") % 2:
        masked = _TRAILING_BACKTICK_RE.sub(_blank, masked)
    return masked


def find_last_tag_positions(content: str) -> Dict[str, int]:
    """Last position of each marker, ignoring markers inside code regions.

    Positions index *content*, not the masked copy -- the mask is
    length-preserving for exactly this reason.
    """
    positions = {
        "thought_start": -1,
        "thought_end": -1,
        "planning_start": -1,
        "planning_end": -1,
    }
    scannable = mask_code_regions(content)

    for key, pattern in (
        ("thought_start", THOUGHT_TAG_PATTERN),
        ("thought_end", THOUGHT_END_PATTERN),
        ("planning_start", PLANNING_TAG_PATTERN),
        ("planning_end", PLANNING_END_PATTERN),
    ):
        for match in pattern.finditer(scannable):
            positions[key] = match.start()

    return positions


def detect_content_type(content: str, current_type: str = "response") -> str:
    """The segment type *content* currently reads as (Issue #351, #17513)."""
    positions = find_last_tag_positions(content)
    thought_start = positions["thought_start"]
    thought_end = positions["thought_end"]
    planning_start = positions["planning_start"]
    planning_end = positions["planning_end"]

    if thought_start >= 0:
        if thought_end > thought_start:
            # Block is closed - check for planning after
            if planning_start > thought_end and planning_end < planning_start:
                return "planning"
            return "response"
        return "thought"

    if planning_start >= 0:
        if planning_end > planning_start:
            return "response"
        return "planning"

    # No tags - maintain current type if in block
    if current_type in BLOCK_CONTENT_TYPES:
        return current_type

    return "response"


def find_new_segment_start(llm_response: str, new_type: str, previous_type: str = "response") -> str:
    """Content after the marker that opens *new_type* (Issue #680, #17513).

    For an opening type the boundary is after ``[TYPE]``; for a return to
    ``response`` it is after the previous type's ``[/TYPE]``. The search runs on
    the masked copy so a quoted marker cannot become the boundary, and the slice
    is taken from the original text.
    """
    opening_tag_map = {
        "thought": THOUGHT_TAG_PATTERN,
        "planning": PLANNING_TAG_PATTERN,
    }
    closing_tag_map = {
        "thought": THOUGHT_END_PATTERN,
        "planning": PLANNING_END_PATTERN,
    }

    if new_type in opening_tag_map:
        pattern = opening_tag_map[new_type]
    elif new_type == "response" and previous_type in closing_tag_map:
        pattern = closing_tag_map[previous_type]
    else:
        return ""

    match = None
    for candidate in pattern.finditer(mask_code_regions(llm_response)):
        match = candidate

    return llm_response[match.end() :] if match else ""
