# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Whether a docstring adds anything beyond its own symbol's name (#17165).

``def get_user_by_id(...)`` documented as ``"Get user by id."`` restates the name in
sentence form and adds nothing an embedding index didn't already have from the
identifier itself -- worse than an absent docstring, because it dilutes the
embedding with tokens already present and manufactures false neighbours (#17165's
own framing, ahead of the bulk-LLM drafting pass this guard exists to set the bar
for).

The check: tokenize the symbol name (splitting ``snake_case`` and
``camelCase``/``PascalCase``), tokenize the docstring's words, drop a small set of
grammatical connectives from the docstring side, and require at least one
docstring word that isn't already a name token. This is deliberately mechanical,
not a linguistic model (#17165 review) -- it catches literal restatement cheaply
and lets a human reviewer catch a paraphrase that uses synonyms of the name
instead of new information.

A missing docstring is not this module's concern -- :func:`is_restatement` returns
``False`` for one, since coverage (whether a docstring exists at all) is a
separate, tracked-elsewhere question (#17165's own AC2).
"""

from __future__ import annotations

import re

#: Grammatical connectives, articles and generic doc-verbs that carry no content
#: on their own. "returns"/"return" specifically: almost always a mechanical
#: prefix ("Returns the ..."), not the informative part of the sentence -- the
#: informative part is whatever follows it, which survives filtering unchanged.
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "of",
        "for",
        "to",
        "and",
        "or",
        "with",
        "from",
        "in",
        "on",
        "at",
        "by",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "as",
        "if",
        "it",
        "its",
        "this",
        "that",
        "into",
        "via",
        "when",
        "than",
        "not",
        "no",
        "given",
        "using",
        "return",
        "returns",
    }
)

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9']*")
#: An all-uppercase run followed by a capitalized word ("HTTPRequest" -> "HTTP",
#: "Request"), a capitalized-or-lowercase run, an all-uppercase run on its own
#: ("ID"), or a digit run -- the standard camelCase/acronym split.
_CAMEL_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")


def _name_tokens(symbol_name: str) -> frozenset[str]:
    """Lowercase word-tokens in *symbol_name*, splitting ``_`` and case changes."""
    tokens: set[str] = set()
    for part in symbol_name.strip("_").split("_"):
        if not part:
            continue
        # A valid identifier segment is only letters/digits, and the alternation's
        # last two branches (a bare uppercase run, a bare digit run) mean this
        # always matches something -- there is no "no case change" fallback to handle.
        tokens.update(p.lower() for p in _CAMEL_RE.findall(part))
    return frozenset(tokens)


def _content_tokens(text: str) -> frozenset[str]:
    """Lowercase word-tokens in *text*, minus stopwords and single letters."""
    words = _WORD_RE.findall(text.lower())
    return frozenset(w for w in words if w not in _STOPWORDS and len(w) > 1)


def is_restatement(symbol_name: str, docstring: str | None) -> bool:
    """True when every content word in *docstring* is already a token of *symbol_name*.

    ``False`` for a missing/blank docstring -- that is a coverage gap, not a
    restatement, and this function does not conflate the two.
    """
    if not docstring or not docstring.strip():
        return False
    novel = _content_tokens(docstring) - _name_tokens(symbol_name)
    return not novel
