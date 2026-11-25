# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A small lexer for the JS family, for the duplicate normalizers (#22194).

A regex cannot match what JS nests (``${`x`}`) or tell a regex literal from a comment
(``/\\/\\//`` is not a ``//`` comment), so the scan walks the text once and names each
piece: ``code``, ``string`` (quoted or template, nesting included), ``regex`` or ``comment``.
"""

from __future__ import annotations

import re
from typing import Callable, List, Optional, Tuple

CODE, STRING, REGEX, COMMENT = "code", "string", "regex", "comment"

_QUOTED = {'"': re.compile(r'"(?:\\.|[^"\\\n])*"'), "'": re.compile(r"'(?:\\.|[^'\\\n])*'")}
_TAIL = 64
_WORD_END = re.compile(r"([A-Za-z_$][\w$]*)\s*$")
# A ``/`` after one of these starts a regex; after a value (identifier, number, ``)``, ``]``, ``}``) it divides.
_REGEX_AFTER = frozenset("(,=:[!&|?{};+-*%<>~^")
_REGEX_AFTER_WORDS = frozenset(
    {"return", "typeof", "instanceof", "in", "of", "new", "delete", "void", "throw", "case", "do", "else"}
)


def _template_end(text: str, i: int) -> int:
    """Index after the template literal opening at ``text[i]`` (a backtick), nested ``${...}`` included."""
    n = len(text)
    i += 1
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
        elif c == "`":
            return i + 1
        elif text.startswith("${", i):
            i = _expression_end(text, i + 2)
        else:
            i += 1
    return n


def _expression_end(text: str, i: int) -> int:
    """Index after the ``}`` closing a ``${`` whose body starts at ``i``; strings and templates inside are skipped."""
    n, depth = len(text), 1
    while i < n:
        c = text[i]
        if c == "`":
            i = _template_end(text, i)
            continue
        quoted = _QUOTED.get(c)
        match = quoted.match(text, i) if quoted else None
        if match:
            i = match.end()
            continue
        depth += (c == "{") - (c == "}")
        i += 1
        if depth == 0:
            return i
    return n


def _regex_end(text: str, i: int) -> Optional[int]:
    """Index after the regex literal (flags included) starting at ``text[i]``, or None when it is no literal."""
    n, in_class = len(text), False
    j = i + 1
    while j < n and text[j] != "\n":
        c = text[j]
        if c == "\\":
            j += 1
        elif c == "[":
            in_class = True
        elif c == "]":
            in_class = False
        elif c == "/" and not in_class:
            j += 1
            while j < n and (text[j].isalpha()):
                j += 1
            return j
        j += 1
    return None


def _regex_allowed(before: str) -> bool:
    """Whether a ``/`` after the code ``before`` (comments and strings already folded in) starts a regex literal."""
    tail = before.rstrip()
    if not tail:
        return True
    if tail[-1] in _REGEX_AFTER:
        return True
    word = _WORD_END.search(tail)
    return bool(word) and word.group(1) in _REGEX_AFTER_WORDS


def _next_piece(text: str, i: int, before: str) -> Tuple[str, int]:
    """``(kind, end)`` of the piece starting at ``text[i]``; plain code is one character."""
    c = text[i]
    quoted = _QUOTED.get(c)
    if quoted and quoted.match(text, i):
        return STRING, quoted.match(text, i).end()
    if c == "`":
        return STRING, _template_end(text, i)
    if text.startswith("//", i):
        end = text.find("\n", i)
        return COMMENT, len(text) if end < 0 else end
    if text.startswith("/*", i):
        end = text.find("*/", i + 2)
        return COMMENT, len(text) if end < 0 else end + 2
    if c == "/" and _regex_allowed(before):
        end = _regex_end(text, i)
        if end is not None:
            return REGEX, end
    return CODE, i + 1


def scan_js(text: str) -> List[Tuple[str, str]]:
    """``text`` as ordered ``(kind, piece)`` pairs that join back to ``text``."""
    pieces: List[Tuple[str, str]] = []
    i, n = 0, len(text)
    before = ""  # the tail of the code seen so far: strings and regexes as a value placeholder, comments dropped
    while i < n:
        kind, end = _next_piece(text, i, before)
        piece = text[i:end]
        if pieces and pieces[-1][0] == kind == CODE:
            pieces[-1] = (CODE, pieces[-1][1] + piece)
        else:
            pieces.append((kind, piece))
        if kind != COMMENT:
            before = (before + ("0" if kind != CODE else piece))[-_TAIL:]
        i = end
    return pieces


def map_js(text: str, on_piece: Callable[[str, str], str]) -> str:
    """``text`` with each piece replaced by ``on_piece(kind, piece)``."""
    return "".join(on_piece(kind, piece) for kind, piece in scan_js(text))
