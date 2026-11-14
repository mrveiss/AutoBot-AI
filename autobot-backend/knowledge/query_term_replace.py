# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Whole-word, case-insensitive term replacement for query expansion (#21525).

Single home for "rewrite one keyword of a query as a synonym", shared by
``advanced_rag_optimizer`` and ``knowledge.search_quality``. It has no
intra-package imports, so either side can import it without a cycle.

Only whole words are rewritten: ``install`` matches ``Install`` / ``INSTALL``
but never the inside of ``installation`` or ``reinstall``. Plurals and other
inflections (``errors``, ``installing``) are different words and are not
rewritten. The rest of the query is preserved exactly.
"""

from __future__ import annotations

import re
from functools import lru_cache

_PATTERN_CACHE_SIZE = 256


@lru_cache(maxsize=_PATTERN_CACHE_SIZE)
def _word_pattern(word: str) -> re.Pattern[str]:
    """Compiled whole-word, case-insensitive pattern for *word* (cached)."""
    return re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)


def match_case(replacement: str, matched: str) -> str:
    """Give *replacement* the case shape of *matched* (lower / Capitalised / UPPER)."""
    if len(matched) > 1 and matched.isupper():
        return replacement.upper()
    if matched[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def replace_whole_word(query: str, word: str, replacement: str) -> str:
    """Replace every whole-word, case-insensitive *word* in *query* with *replacement*.

    The replacement adopts the matched occurrence's case. Returns *query*
    unchanged when the word does not occur as a whole word.
    """
    return _word_pattern(word).sub(lambda m: match_case(replacement, m.group(0)), query)
