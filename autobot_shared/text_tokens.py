#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one word tokenizer: lowercase, split on non-word characters, marks kept in the word (#18093, #21891).

Three copies existed and are now parameter sets of this module:

* `prepared_facts._tok` and `skills/builtin/skill_router._tokenize` split on `[\\W_]+`
  (underscore is a separator) and wanted a set;
* `agent_loop/fingerprint.tokenize`, `knowledge/search_quality`,
  `llm_shared/tiered_routing/complexity_scorer`, `services/skill_management/skill_extractor`
  and `markdown_reference_system` used `re.findall(r"\\b\\w+\\b")` (underscore stays
  inside a token); the first wants the ordered list with duplicates.

`\\b\\w+\\b` finds exactly the maximal runs of `\\w`, which is what splitting on `\\W+`
leaves, so the two differ only in the underscore. The module lives in `autobot_shared`
because `prepared_facts` cannot import anything under `skills` (`skills.registry`
imports it).

Not this concept: `training/data_loader.Tokenizer.tokenize` keeps case and emits
punctuation tokens (`\\b\\w+\\b|[^\\w\\s]`) to build a code-completion vocabulary. It
is a lossless code tokenizer, not word extraction.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from functools import lru_cache
from typing import FrozenSet, List, Pattern

__all__ = ["word_token_list", "word_tokens"]

_MARK_CATEGORIES = frozenset({"Mn", "Mc", "Me"})


def _mark_class_body() -> str:
    """Regex class body listing every Unicode mark (Mn, Mc, Me) as `\\U` ranges.

    `re` has no `\\p{M}` and the `regex` package is not a dependency, so the ranges
    are read from `unicodedata`, the tables `str.isalnum` (and so `\\w`) already use.
    """
    ranges, start = [], None
    for cp in range(sys.maxunicode + 2):
        is_mark = cp <= sys.maxunicode and unicodedata.category(chr(cp)) in _MARK_CATEGORIES
        if is_mark and start is None:
            start = cp
        elif not is_mark and start is not None:
            ranges.append((start, cp - 1))
            start = None
    return "".join(f"\\U{a:08x}" if a == b else f"\\U{a:08x}-\\U{b:08x}" for a, b in ranges)


@lru_cache(maxsize=None)
def _pattern(split_underscore: bool) -> Pattern[str]:
    """Separator pattern: a run of non-word characters, with marks kept inside the word (#21891).

    Marks (Devanagari vowel signs, Tamil pulli, Arabic harakat, NFD diacritics) are not
    `\\w`, so `\\W+` cut such words apart. Built on first use, not at import.
    """
    separator = f"[^\\w{_mark_class_body()}]"
    return re.compile(f"(?:_|{separator})+" if split_underscore else f"{separator}+")


def word_token_list(text: str, *, split_underscore: bool = True, lowercase: bool = True) -> List[str]:
    """Lowercase *text* and return its word tokens in order, duplicates kept.

    Args:
        text: Source text.
        split_underscore: True (default) treats `_` as a separator, so `snake_case`
            is two tokens; False keeps it inside a token, as `\\w` does.
        lowercase: False when the caller has already lowercased (or deliberately
            counts case-preserved runs), so the text is not lowered a second time.

    >>> word_token_list("Analyze_this PDF-document!")
    ['analyze', 'this', 'pdf', 'document']
    >>> word_token_list("Analyze_this PDF-document!", split_underscore=False)
    ['analyze_this', 'pdf', 'document']
    """
    pattern = _pattern(split_underscore)
    return [t for t in pattern.split(text.lower() if lowercase else text) if t]


def word_tokens(text: str, *, split_underscore: bool = True, lowercase: bool = True) -> FrozenSet[str]:
    """The set view of `word_token_list`, for callers that only test membership."""
    return frozenset(word_token_list(text, split_underscore=split_underscore, lowercase=lowercase))
