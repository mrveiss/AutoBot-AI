# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Sweep a pinned file with only its pinned sites masked -- one helper for every one-home guard (#19498)."""

from __future__ import annotations

import re


def masked(text: str, pattern: str, mask: str = "_") -> str:
    """*text* with each capture of *pattern* overwritten by *mask*: the pinned sites, and only them.

    The capture, not the whole match, so a definition inside a multi-line pin's context is still
    swept, and every line keeps its length and number, so the sites left over are reported where
    they stand. The default ``_`` keeps a masked Python literal parseable (it becomes a name); pass
    ``" "`` where a scanner reads ``_`` as part of an identifier.
    """

    def _blank(m: re.Match[str]) -> str:
        out, last = [], m.start()
        for group in range(1, (m.re.groups or 0) + 1):
            if m.start(group) >= 0:
                out += [text[last : m.start(group)], mask * (m.end(group) - m.start(group))]
                last = m.end(group)
        return "".join(out) + text[last : m.end()]

    return re.sub(pattern, _blank, text, flags=re.MULTILINE)
