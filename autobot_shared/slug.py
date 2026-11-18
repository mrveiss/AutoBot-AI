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

`sanitize_token` is the general form (#18093, AC 2): the other ~13 sites that turn free
text into a safe token (Redis key, filename, collection name, tag, env-var name, MCP
prefix, ...) differ only in allowed characters, replacement, run-collapsing, case, edge
strip and length cap. Each of those is a keyword here, so a site keeps its exact output by
naming its parameters instead of owning a regex. `url_slug` and
`agent_loop.text_utils.slugify` are two parameter sets of it. Defaults are `url_slug`'s.
Stored-key sites (Redis key, Chroma collection, KB tag, temp-dir / key filename) are pinned
byte-for-byte against their previous implementation in `slug_equivalence_18093_test.py`.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

__all__ = ["url_slug", "sanitize_token"]


def sanitize_token(
    text: str,
    *,
    allowed: str | None = "a-z0-9",
    replacement: str = "-",
    collapse: bool = True,
    separator_chars: str = "",
    separator: str | None = None,
    case: Literal["lower", "upper"] | None = None,
    strip_input: bool = False,
    strip_edges: str = "",
    max_length: int | None = None,
    strip_after_truncate: bool = False,
    fold_unicode: bool = False,
) -> str:
    """Turn free text into a safe token. Every parameter is one observed site variation.

    Steps, in order: fold -> case -> strip_input -> replace disallowed -> collapse
    `separator_chars` -> strip_edges -> truncate -> (re-strip).

    Args:
        text: Source text.
        allowed: Regex character-class BODY of characters kept as-is (e.g. ``"a-z0-9"``,
            ``r"\\w-"``). Everything else becomes `replacement`. None skips the step.
        replacement: What a disallowed character (or, with `collapse`, a run of them)
            becomes. "" deletes them.
        collapse: Replace a RUN of disallowed characters with one `replacement` (True),
            or each character individually (False -- Redis keys, filenames, collection
            names keep one output character per input character).
        separator_chars: Class body of characters that are allowed but whose runs
            collapse to `separator` (``"_"`` in env names, ``r"\\s_-"`` in text_utils).
        separator: Result of that collapse; defaults to `replacement`.
        case: "lower" or "upper", applied before replacement; None leaves case alone.
        strip_input: `str.strip()` the input (whitespace) before anything else.
        strip_edges: Characters stripped from both ends of the result.
        max_length: Truncate to this many characters. None = no cap.
        strip_after_truncate: Strip `strip_edges` again after truncating, so a cut
            landing mid-run never leaves a trailing separator.
        fold_unicode: NFKD-normalise and drop non-ASCII before anything else.

    Returns:
        The sanitised token, possibly "" -- what empty means is the caller's policy.

    Examples:
        >>> sanitize_token("Hello, World!", case="lower", strip_edges="-")
        'hello-world'
        >>> sanitize_token("a b/c", allowed=r"\\w", replacement="_", collapse=False)
        'a_b_c'
    """
    if fold_unicode:
        text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    if case == "lower":
        text = text.lower()
    elif case == "upper":
        text = text.upper()
    if strip_input:
        text = text.strip()
    if allowed is not None:
        text = re.sub(f"[^{allowed}]" + ("+" if collapse else ""), lambda _m: replacement, text)
    if separator_chars:
        sep = replacement if separator is None else separator
        text = re.sub(f"[{separator_chars}]+", lambda _m: sep, text)
    if strip_edges:
        text = text.strip(strip_edges)
    if max_length is not None:
        text = text[:max_length]
        if strip_after_truncate and strip_edges:
            text = text.strip(strip_edges)
    return text


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
    return sanitize_token(
        text,
        case="lower",
        strip_edges="-",
        max_length=max_length,
        strip_after_truncate=True,
        fold_unicode=fold_unicode,
    )
