#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One parser for ``---``-delimited YAML front matter (#18093).

Seven call sites each had their own regex, in four incompatible variants. Measured
against the same four inputs:

    variant                        LF      CRLF      '--- ' + ws   no trailing NL
    markdown_reference_system:25   ok      ok \\r!    ok            ok
    specialized_agent_service:95   ok      ok \\r!    ok            ok
    skills/generator:98            ok      REJECT    REJECT        ok
    skills/sync/base_sync:24       ok      REJECT    REJECT        ok
    skills/validator:86            ok      REJECT    REJECT        ok
    skills/manifest_parser:42      ok      ok \\r!    REJECT        ok
    claude_memory_importer:61      ok      REJECT    REJECT        REJECT

Three consequences, all of them live before this module existed:

* A CRLF ``SKILL.md`` parsed by ``manifest_parser`` and was then rejected by
  ``validator`` and ``generator`` — accepted and invalid at once, depending on which
  code path reached it.
* Every variant that *did* accept CRLF leaked the ``\\r`` into the captured YAML, so the
  last key's value carried a trailing carriage return into ``yaml.safe_load``.
* ``claude_memory_importer`` alone rejected a document that is nothing but front matter,
  because its pattern required a newline after the closing fence.

This module accepts all four shapes, returns YAML with line endings normalised so no
parser sees a stray ``\\r``, and returns the body as a verbatim slice of the input so no
caller's content is rewritten.

It deliberately does **no** YAML parsing. The seven sites disagree about what a malformed
block means — ``{}``, ``ValueError``, ``MemoryParseError``, or an entry appended to an
error list — and that is a per-caller policy, not something a shared helper should decide.
"""

from __future__ import annotations

import re

__all__ = ["split_frontmatter", "strip_frontmatter"]

# A fence is exactly three dashes on its own line, optionally followed by horizontal
# whitespace and a carriage return. Leading whitespace is NOT accepted: every call site
# this replaces anchored on `^---`, and accepting an indented fence would widen behaviour
# rather than unify it.
_FENCE_RE = re.compile(r"---[ \t]*\r?")


def split_frontmatter(text: str) -> tuple[str | None, str]:
    """Split ``text`` into its front-matter YAML and the body that follows.

    Args:
        text: A document that may open with a ``---`` fenced YAML block.

    Returns:
        ``(yaml_text, body)`` when the document opens with a terminated fence, where
        ``yaml_text`` has CRLF normalised to LF. ``(None, text)`` otherwise — no fence,
        an unterminated fence, or an empty string — with ``text`` returned unchanged so a
        caller can fall back without reconstructing anything.

    Examples:
        >>> split_frontmatter("---\\nname: x\\n---\\nbody\\n")
        ('name: x', 'body\\n')
        >>> split_frontmatter("---\\r\\nname: x\\r\\n---\\r\\nbody\\r\\n")
        ('name: x', 'body\\r\\n')
        >>> split_frontmatter("---\\nname: x\\n---")
        ('name: x', '')
        >>> split_frontmatter("no front matter here")
        (None, 'no front matter here')
        >>> split_frontmatter("---\\nname: x\\nnever closed\\n")
        (None, '---\\nname: x\\nnever closed\\n')
    """
    if not text.startswith("---"):
        return None, text

    # `split("\n")` and not `splitlines()`: splitlines() also breaks on U+2028, U+2029,
    # \x0b and \x0c, so a front-matter value containing one would be silently cut in two
    # and the offset arithmetic below would no longer reconstruct the input.
    lines = text.split("\n")
    if not _FENCE_RE.fullmatch(lines[0]):
        return None, text

    for index in range(1, len(lines)):
        if not _FENCE_RE.fullmatch(lines[index]):
            continue
        yaml_text = "\n".join(_strip_cr(line) for line in lines[1:index])
        # Offset just past the newline that ended the closing fence. When the fence is
        # the final line the sum overshoots by one, and the slice is "" — which is the
        # right answer for a document that is nothing but front matter.
        consumed = sum(len(line) + 1 for line in lines[: index + 1])
        return yaml_text, text[consumed:]

    return None, text


def strip_frontmatter(text: str) -> str:
    """Return ``text`` without its front-matter block, or unchanged if it has none."""
    return split_frontmatter(text)[1]


def _strip_cr(line: str) -> str:
    """Drop one trailing carriage return, leaving any other ``\\r`` in place."""
    return line[:-1] if line.endswith("\r") else line
