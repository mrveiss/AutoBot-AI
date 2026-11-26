# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Code blocks for the duplicate detector: model, normalization and qualification (#22157).

Two normalizations exist on purpose. ``normalize_exact`` removes comments and
whitespace only, so two blocks that agree after it are the same code. The
structural form additionally erases every string literal, so it also equates
blocks that differ only in their text (prompts, messages, paths). A block
qualifies on the size of its STRUCTURAL form: judged on the raw text, thirty
50-line ``_get_system_prompt`` methods normalised to nine tokens each and were
reported as one another's 100% duplicates.
"""

import re
from dataclasses import dataclass, field
from typing import Callable, Optional, Set

from autobot_shared.content_digest import content_digest
from autobot_shared.js_lexer import CODE, COMMENT_KINDS, STRING, lex_js
from utils.file_categorization import JS_EXTENSIONS, TS_EXTENSIONS, VUE_EXTENSIONS

# Minimum lines for a code block to be considered for duplicate detection
# Issue #609: Reduced from 5 to 4 to catch more smaller duplicates
MIN_DUPLICATE_LINES = 4
# Minimum characters of the NORMALIZED block (#22157: was measured on the raw text)
MIN_DUPLICATE_CHARS = 80

# Files whose comments are ``//`` and ``/* */``; every other scanned file is Python (``#``).
JS_FAMILY_SUFFIXES = tuple(sorted(JS_EXTENSIONS | TS_EXTENSIONS | VUE_EXTENSIONS))

# A quoted string is matched first, in the same pass as the comment, so a comment marker inside
# one is not a comment. Python also has triple-quoted strings. The JS family is lexed by the
# shared ``autobot_shared.js_lexer`` (nested templates, regex literals), the guards' lexer too.
_DQ = r'"(?:\\.|[^"\\\n])*"'
_SQ = r"'(?:\\.|[^'\\\n])*'"
_PY_STRING = r'(?P<string>""".*?"""' + r"|'''.*?'''" + "|" + _DQ + "|" + _SQ + ")"
_PY_COMMENT_RE = re.compile(_PY_STRING + r"|\#[^\n]*", re.DOTALL)
# The same strings, then a whitespace run: collapsing whitespace must not reach inside a literal.
_PY_SPACE_RE = re.compile(_PY_STRING + r"|\s+", re.DOTALL)


@dataclass
class CodeBlock:
    """Represents a block of code for duplicate detection."""

    file_path: str
    start_line: int
    end_line: int
    content: str
    normalized_content: str
    content_hash: str
    line_count: int
    # Issue #659: Pre-computed token set for 30-40% faster similarity computation
    # Avoids recomputing tokens on every comparison
    token_set: Set[str] = field(default_factory=set)
    # #22157: hash of the comment- and whitespace-normalized text only; equal here
    # means the same code, where ``content_hash`` also equates differing strings.
    exact_hash: str = ""


def _map_js(content: str, on_piece: Callable[[str, str], str]) -> str:
    """*content* with each lexed ``(kind, piece)`` replaced by ``on_piece(kind, piece)``, joined once."""
    return "".join([on_piece(kind, piece) for kind, piece in lex_js(content).pieces])


def _strip_comments(content: str, js_family: bool, string_as: Optional[str] = None) -> str:
    """*content* without comments, by the file's own syntax; strings kept verbatim, or replaced by *string_as*."""
    if js_family:
        return _map_js(
            content,
            lambda kind, piece: "" if kind in COMMENT_KINDS else (string_as or piece) if kind == STRING else piece,
        )
    pattern = _PY_COMMENT_RE
    return pattern.sub(lambda m: (string_as or m.group("string")) if m.group("string") else "", content)


def normalize_structural(content: str, js_family: bool = False) -> str:
    """Normalize for structural comparison: comments removed, every string's text erased, whitespace collapsed.

    Comments are removed by the file's own syntax, as in ``normalize_exact``: ``a // b`` is Python floor
    division and stays, so a block full of it keeps its real size against ``MIN_DUPLICATE_CHARS``.
    """
    content = _strip_comments(content, js_family, string_as='"STR"')
    return re.sub(r"\s+", " ", content).strip().lower()


def normalize_exact(content: str, js_family: bool = False) -> str:
    """Normalize by removing comments and whitespace variation ONLY; strings and case are kept.

    Comments are ``#`` in Python and ``//`` / ``/* */`` in the JS family; the other file
    type's markers are code (``a // b`` is Python floor division). Whitespace is collapsed
    outside string literals only: ``"first  name"`` and ``"first name"`` are different values.
    """
    content = _strip_comments(content, js_family)
    if js_family:
        return _map_js(content, lambda kind, piece: re.sub(r"\s+", " ", piece) if kind == CODE else piece).strip()
    return _PY_SPACE_RE.sub(lambda m: m.group("string") or " ", content).strip()


def make_block(file_path: str, start_line: int, end_line: int, content: str, line_count: int) -> Optional[CodeBlock]:
    """Build a block, or None when its normalized form is too small to be a duplicate (#22157)."""
    js_family = file_path.endswith(JS_FAMILY_SUFFIXES)
    normalized = normalize_structural(content, js_family)
    if len(normalized) < MIN_DUPLICATE_CHARS:
        return None
    return CodeBlock(
        file_path=file_path,
        start_line=start_line,
        end_line=end_line,
        content=content,
        normalized_content=normalized,
        content_hash=content_digest(normalized),
        line_count=line_count,
        token_set=set(normalized.split()),
        exact_hash=content_digest(normalize_exact(content, js_family)),
    )
