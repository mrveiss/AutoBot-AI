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

A backtick literal is *mostly* text, but a `${...}` interpolation is **code** -- it
can contain comments, and a comment there would otherwise stay visible because the
surrounding literal is copied verbatim. Interpolations are therefore processed
recursively while the template text around them is left alone (#17670 review).

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


def _matching_brace(content: str, open_at: int) -> int:
    """Index of the `}` closing the `{` at *open_at*, counting **code only**.

    Braces inside a comment or a string are not delimiters. Counting raw characters
    let ``${/* } … */ ''}`` end at the brace inside the comment, after which the rest
    of the comment was copied out as template text and its contents became visible
    to the scanner -- the same leak this module exists to close, one level down
    (#17670 review).

    The counting view comes from `blank_comments` itself with strings blanked as
    well, so there is no second scanner to drift from the first: whatever the real
    pass treats as a comment or a string is what this refuses to count. Blanking
    preserves length, so indices in the view are indices in *content*.
    """
    view = blank_comments(content[open_at:], _strings_too=True)
    depth = 0
    for offset, ch in enumerate(view):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return open_at + offset
    return len(content)


def _consume_string(content: str, i: int, quote: str, *, blank_strings: bool = False) -> Tuple[str, int]:
    """Copy the string literal at *i* verbatim, honouring backslash escapes.

    Verbatim because the contents are what the scanner is looking for: an API path
    is a string literal, and a scheme's slash pair must not read as a comment.

    One exception, for backticks only: a `${...}` interpolation is code rather than
    text, so its contents go back through `blank_comments`. Without that, a comment
    inside an interpolation survives because the literal around it is copied
    (#17670 review). Length is preserved either way, so positions still hold.
    """
    out = ["#" if blank_strings else content[i]]
    j = i + 1
    while j < len(content):
        ch = content[j]
        if ch == "\\" and j + 1 < len(content):
            out.append(_blank_like(content[j : j + 2]) if blank_strings else content[j : j + 2])
            j += 2
            continue
        # In the counting view the whole literal is blanked, interpolations
        # included: a brace inside a nested template is not a delimiter of the
        # interpolation being measured, and skipping the recursion here is what
        # keeps `_matching_brace` from re-entering itself.
        if quote == "`" and not blank_strings and content.startswith("${", j):
            end = _matching_brace(content, j + 1)
            out.append("${" + blank_comments(content[j + 2 : end]) + content[end : end + 1])
            j = end + 1
            continue
        out.append(_blank_like(ch) if blank_strings else ch)
        j += 1
        if ch == quote:
            break
    return "".join(out), j


def blank_comments(content: str, *, _strings_too: bool = False) -> str:
    """Return *content* with comment bodies replaced by spaces, length preserved.

    Handles ``//`` to end of line, ``/* … */`` across lines, and ``<!-- … -->`` for
    Vue templates. Quoted strings pass through untouched.

    ``_strings_too`` is internal: it additionally blanks string bodies, producing the
    code-only view `_matching_brace` counts braces in. It is the same pass either
    way, deliberately -- a separate brace scanner could disagree with this one about
    what a string is.
    """
    out: list[str] = []
    i, n = 0, len(content)
    while i < n:
        ch = content[i]
        if ch in _QUOTES:
            text, i = _consume_string(content, i, ch, blank_strings=_strings_too)
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
