# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""Pure-text parser for Jina Reader response output.

Extracted from ``autobot-backend/media/link/pipeline.py`` (#7460) so that
``autobot-backend/web_fetch/extractors.py`` and other consumers can import
the parser without dragging in ``media.link.pipeline``'s heavy import
chain (``knowledge.query_sanitizer`` + further deps). The function is pure
text → tuple — zero side-effects, zero I/O — which is exactly the kind of
utility that belongs in ``autobot_shared``.

Jina Reader output format::

    Title: Actual Page Title Here
    URL Source: https://...

    Markdown body starts here...
"""

from __future__ import annotations

import re
from typing import Tuple

# Match ``Header-Name: value`` style metadata lines (Jina prepends a small
# block: ``Title:``, ``URL Source:``, optional others). Pinned letters/digits/
# space/underscore/hyphen so we don't accidentally match arbitrary text that
# happens to contain a colon (e.g. URLs in markdown body).
_METADATA_LINE_RE = re.compile(r"^([A-Za-z][A-Za-z0-9 _-]*):\s*(.+)$")

# Hard cap to avoid mis-detected metadata blocks pulling 100s of lines into
# the title scan. 10 lines covers the realistic Jina header surface.
_METADATA_SCAN_LIMIT = 10

# Bound title length to avoid pathological inputs blowing memory caches.
_TITLE_MAX_LEN = 200


def parse_jina_output(content: str) -> Tuple[str, str]:
    """Parse Jina Reader output into ``(title, body)``.

    Scans the first ~10 lines for a ``Title:`` prefix, then strips the
    metadata header (everything up to and including the first blank line
    after the metadata block) from the body. If no ``Title:`` prefix is
    found, the title falls back to the first non-empty line of the body and
    no header is stripped.

    Returns ``("", "")`` for empty input.
    """
    if not content:
        return "", ""

    lines = content.splitlines()
    title = ""
    metadata_end_idx = -1  # index of the blank line after metadata block

    scan_limit = min(len(lines), _METADATA_SCAN_LIMIT)
    for idx in range(scan_limit):
        line = lines[idx]
        stripped = line.strip()
        if not stripped and title:
            # Blank line AFTER a Title line — end of metadata header.
            metadata_end_idx = idx
            break
        match = _METADATA_LINE_RE.match(stripped)
        if match:
            key = match.group(1).strip().lower()
            if key == "title" and not title:
                title = match.group(2).strip()[:_TITLE_MAX_LEN]
            # Continue scanning — could be Title, URL Source, etc.

    if title and metadata_end_idx >= 0:
        # Strip metadata header (header lines + the blank separator).
        body = "\n".join(lines[metadata_end_idx + 1 :]).lstrip("\n")
        return title, body

    if title:
        # Title found but no blank-line separator — return title + full content.
        return title, content

    # Fallback: no Title: prefix. Use first non-empty line as title.
    first_nonempty = next((ln.strip() for ln in lines if ln.strip()), "")
    return first_nonempty[:_TITLE_MAX_LEN], content


__all__ = ["parse_jina_output"]
