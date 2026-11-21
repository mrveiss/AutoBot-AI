# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Exact, disjoint spellings of ``\\s`` / ``\\S`` for regexes a static ReDoS analyser must prove linear (#21987).

``\\S+\\s+`` inside a repeated group is unambiguous at runtime, but CodeQL's model of the two
shorthand classes overlaps, so it reports exponential backtracking (``py/redos``). Spelling the
classes out lets the analyser see the real, disjoint sets. :data:`WS_CHARS` is exactly the set
``re`` matches with ``\\s`` for ``str`` patterns (``str.isspace()``), so swapping it in changes
no match; ``autobot_shared/regex_whitespace_test.py`` proves that for every code point.

``WS_CHARS`` / ``HSPACE_CHARS`` are class *bodies* (no brackets) so a caller can compose them,
e.g. ``rf"[^{WS_CHARS}{{]"`` for "not whitespace and not ``{``".
"""

_TAIL = r"\x1c-\x20\x85\xa0  -     　"

#: Body of a character class equal to ``\s``.
WS_CHARS = r"\t-\r" + _TAIL
#: Body of a character class equal to ``\s`` minus ``\n`` (what ``^`` + MULTILINE line starts allow).
HSPACE_CHARS = r"\t\x0b-\r" + _TAIL

#: ``[...]`` equal to ``\s``.
WS = f"[{WS_CHARS}]"
#: ``[^...]`` equal to ``\S``.
NOT_WS = f"[^{WS_CHARS}]"
#: ``[...]`` equal to ``\s`` without the newline.
HSPACE = f"[{HSPACE_CHARS}]"
