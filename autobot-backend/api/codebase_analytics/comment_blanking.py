# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Blank comments out of JS/TS/Vue source before scanning it for API calls (#17668).

The frontend call scanner used to decide "is this a comment?" per line, by prefix:

    stripped = line.strip()
    if stripped.startswith("//") or stripped.startswith("/*"):
        continue

That knows two spellings and the class has at least three. A JSDoc example lives on
a **continuation** line -- ``*   const r = await ApiClient.get('/api/export')`` --
which starts with neither, so three of the four findings on the live "Potential
Bugs" panel were documentation. A comment trailing real code was scanned too,
because the line does not *start* with the marker. "Is this position inside a
comment" is not a property of one line, so it cannot be answered without carrying
block state across lines.

Comment characters are replaced with **spaces** rather than removed, so every
reported line and column still points at the same place in the original file.

String awareness is not optional here: an ``https`` scheme contains a slash pair,
and a comment stripper without it would blank the rest of that line -- silencing
genuine calls, which is the failure direction that looks like success.

**Known limit, stated rather than discovered later.** A JavaScript regex literal
containing a slash pair is not distinguished from a line comment; a full lexer is
the only way to separate those, and the scanner's input is API-path string
literals, where the shape does not arise. If a false negative is ever traced to a
regex literal, this is the place, and the fix is a tokenizer rather than another
special case.
"""

from __future__ import annotations

from typing import Tuple

_LINE = "//"
_BLOCK_OPEN, _BLOCK_CLOSE = "/*", "*/"
_HTML_OPEN, _HTML_CLOSE = "<!--", "-->"
_QUOTES = ("'", '"', "`")


def _blank_like(text: str) -> str:
    """*text* with every character replaced by a space, newlines kept."""
    return "".join("\n" if ch == "\n" else " " for ch in text)


def _consume_line_comment(content: str, i: int) -> Tuple[str, int]:
    """Blank from *i* to the end of the line, leaving the newline in place."""
    end = content.find("\n", i)
    if end == -1:
        return _blank_like(content[i:]), len(content)
    return _blank_like(content[i:end]), end


def _consume_until(content: str, i: int, closer: str) -> Tuple[str, int]:
    """Blank from *i* through *closer*, or to end of input if it never closes."""
    end = content.find(closer, i)
    if end == -1:
        return _blank_like(content[i:]), len(content)
    stop = end + len(closer)
    return _blank_like(content[i:stop]), stop


def _consume_string(content: str, i: int, quote: str) -> Tuple[str, int]:
    """Copy the string literal at *i* verbatim, honouring backslash escapes.

    Verbatim because the contents are what the scanner is looking for: an API path
    is a string literal, and a scheme's slash pair must not read as a comment.
    """
    out = [content[i]]
    j = i + 1
    while j < len(content):
        ch = content[j]
        out.append(ch)
        if ch == "\\" and j + 1 < len(content):
            out.append(content[j + 1])
            j += 2
            continue
        j += 1
        if ch == quote:
            break
    return "".join(out), j


def blank_comments(content: str) -> str:
    """Return *content* with comment bodies replaced by spaces, length preserved.

    Handles ``//`` to end of line, ``/* … */`` across lines, and ``<!-- … -->`` for
    Vue templates. Quoted strings pass through untouched.
    """
    out: list[str] = []
    i, n = 0, len(content)
    while i < n:
        ch = content[i]
        if ch in _QUOTES:
            text, i = _consume_string(content, i, ch)
        elif content.startswith(_LINE, i):
            text, i = _consume_line_comment(content, i)
        elif content.startswith(_BLOCK_OPEN, i):
            text, i = _consume_until(content, i, _BLOCK_CLOSE)
        elif content.startswith(_HTML_OPEN, i):
            text, i = _consume_until(content, i, _HTML_CLOSE)
        else:
            text, i = ch, i + 1
        out.append(text)
    return "".join(out)
