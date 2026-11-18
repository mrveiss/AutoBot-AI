#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one word tokenizer: lowercase, split on non-word characters (#18093).

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
from typing import FrozenSet, List

__all__ = ["word_token_list", "word_tokens"]

_SPLIT_UNDERSCORE = re.compile(r"[\W_]+")
_KEEP_UNDERSCORE = re.compile(r"\W+")


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
    pattern = _SPLIT_UNDERSCORE if split_underscore else _KEEP_UNDERSCORE
    return [t for t in pattern.split(text.lower() if lowercase else text) if t]


def word_tokens(text: str, *, split_underscore: bool = True, lowercase: bool = True) -> FrozenSet[str]:
    """The set view of `word_token_list`, for callers that only test membership."""
    return frozenset(word_token_list(text, split_underscore=split_underscore, lowercase=lowercase))
