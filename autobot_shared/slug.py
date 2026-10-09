#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One hyphen-slug rule (#18093).

Three sites independently implemented the same thing -- lowercase, collapse runs of
non-alphanumeric characters to a single hyphen, strip the edges, truncate:

    autobot-backend/knowledge/adapters/okf_adapter.py:152   cap 80, NFKD fold first
    autobot-backend/llc/models/company.py:61                cap 100, strips TWICE
    autobot_shared/user_management/organization_service.py:573  cap 100

They were not merely duplicated, they disagreed on two details, and in both cases the
minority was right:

* `company.py` alone does `.strip("-")[:100].strip("-")`. The second strip matters:
  truncation can land mid-run and leave a trailing hyphen, so the other two could emit
  `my-long-name-` where `company.py` emits `my-long-name`.
* `okf_adapter` alone NFKD-folds to ASCII first. Without it, "Zürich" slugs to
  `z-rich` -- the non-ASCII character is not alphanumeric in the class, so it becomes a
  separator rather than being transliterated.

This takes both. Folding is the default because a slug that silently splits a word is
worse than one that transliterates it, and the behaviour only differs for non-ASCII
input.

What it deliberately does NOT decide is what an empty result means. `okf_adapter` falls
back to "concept", `company.py` raises, `organization_service` returns it as-is. That is
per-caller policy, so this returns "" and lets each keep its own -- the same division as
`autobot_shared.frontmatter`, which parses but does not decide what malformed YAML means.

NOT in scope: `agent_loop/text_utils.py:16` `slugify`, which collapses to UNDERSCORE
(a whitespace/underscore/hyphen run -> `_`) and keeps word characters rather than ASCII-folding. Same word,
different output contract; flattening it would change identifiers it has already
produced.
"""

from __future__ import annotations

import re
import unicodedata

__all__ = ["url_slug"]

#: A run of anything that is not a lowercase ASCII alphanumeric becomes one hyphen.
_NON_SLUG_RUN = re.compile(r"[^a-z0-9]+")


def url_slug(text: str, *, max_length: int = 100, fold_unicode: bool = True) -> str:
    """Return a URL-safe hyphen slug, or "" when nothing survives.

    Args:
        text: Source text.
        max_length: Maximum length of the result. Truncation happens before the final
            strip, so the result never ends in a hyphen.
        fold_unicode: NFKD-normalise and transliterate to ASCII first, so "Zürich"
            becomes "zurich" rather than "z-rich". Set False only to preserve an
            existing non-folding contract.

    Returns:
        A string matching ``[a-z0-9]([a-z0-9-]*[a-z0-9])?``, or "".

    Examples:
        >>> url_slug("Hello, World!")
        'hello-world'
        >>> url_slug("Zürich")
        'zurich'
        >>> url_slug("Zürich", fold_unicode=False)
        'z-rich'
        >>> url_slug("a very long name indeed", max_length=12)
        'a-very-long'
        >>> url_slug("!!!")
        ''
    """
    if fold_unicode:
        text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = _NON_SLUG_RUN.sub("-", text.lower()).strip("-")
    # Strip again AFTER truncating: cutting mid-run would otherwise leave a trailing
    # hyphen, which is what two of the three original implementations emitted.
    return slug[:max_length].strip("-")
