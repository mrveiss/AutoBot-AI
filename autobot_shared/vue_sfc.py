# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one Vue single-file-component ``<script>`` body extractor (#21641).

The closing tag tolerates whitespace and attributes (``</script >``) as browsers do, and the
match is case-insensitive. It is a linear scan, not a regex with a lazy body: a body regex
re-scans the rest of the input from every ``<script`` it tries, which is polynomial on input
holding many unclosed tags (CodeQL py/polynomial-redos, #1733).
"""

import re

_OPEN = re.compile(r"<script", re.IGNORECASE)
_CLOSE = re.compile(r"</script", re.IGNORECASE)


def _first_tag_end(text: str, pattern: re.Pattern[str], pos: int) -> tuple[int, int] | None:
    """``(start, end)`` of the first *pattern* tag at or after *pos*, ``end`` just past its ``>``.

    The first candidate whose name ends properly decides: when no ``>`` follows it, none follows a later one
    either, so each candidate costs O(1) and the one ``find`` runs once — linear in ``len(text)``.
    """
    for tag in pattern.finditer(text, pos):
        name_end = tag.end()
        if name_end < len(text) and (text[name_end].isspace() or text[name_end] in ">/"):
            close = text.find(">", name_end)
            return None if close == -1 else (tag.start(), close + 1)
    return None


def vue_script_body(text: str) -> str | None:
    """The body of the first ``<script ...>...</script ...>`` element in *text*, or None if there is none."""
    opening = _first_tag_end(text, _OPEN, 0)
    if opening is None:
        return None
    closing = _first_tag_end(text, _CLOSE, opening[1])
    return None if closing is None else text[opening[1] : closing[0]]
