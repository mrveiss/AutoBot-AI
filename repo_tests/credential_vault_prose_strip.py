# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Blank comments and docstrings out of Python source before a text-based scan.

Split out of ``credential_vault_resolution_guard_test.py`` (#15280) to keep that
guard under its line budget -- :func:`strip_prose` is a general "make a
text-matching scanner blind to prose" pass, not something credential-specific.

A real credential read cannot live inside a comment or a docstring: Python never
evaluates either as anything but a no-op. Blanking them before the guard's regex
runs can therefore only remove false positives, never hide a genuine read. The
real shape #15267 shipped, ``getattr(config, "brave_search_api_key", "")``, is a
string used as a call *argument*, not a floating statement -- :func:`strip_prose`
leaves it untouched, so the guard's regex still catches it.
"""

from __future__ import annotations

import io
import tokenize

#: Token types that only delimit statements/lines, never contribute a statement's
#: own content -- excluded when deciding whether a STRING token opens a new
#: statement (a docstring), so a blank line or an indent/dedent never resets that.
_STATEMENT_JOINERS = (tokenize.NL, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING)


class UnparseableSourceError(RuntimeError):
    """A file failed to tokenize.

    Raised, not swallowed: every tracked production ``.py`` file is assumed to be
    valid Python, so a tokenize failure means that assumption broke, which the
    caller must surface rather than paper over by skipping the file -- silently
    skipping is the exact shape of bug this repo keeps finding (#15280).
    """


def _blank(lines: list[str], start: tuple[int, int], end: tuple[int, int]) -> None:
    """Overwrite ``lines[start:end]`` (tokenize's 1-indexed, end-exclusive span)
    with spaces, leaving every newline untouched -- so blanking a multi-line
    token never shifts any later token's reported line number.
    """
    start_row, start_col = start
    end_row, end_col = end
    for row in range(start_row, end_row + 1):
        line = lines[row - 1]
        has_nl = line.endswith("\n")
        body_len = len(line) - (1 if has_nl else 0)
        lo = start_col if row == start_row else 0
        hi = end_col if row == end_row else body_len
        lines[row - 1] = line[:lo] + " " * (hi - lo) + line[hi:]


def strip_prose(text: str) -> str:
    """Blank every comment and *floating* string statement in *text*.

    "Floating" means the STRING token is a whole statement by itself -- a module,
    class or function docstring, or any other bare string used as an inline
    comment -- detected as a STRING immediately preceded by a statement boundary
    and immediately followed by NEWLINE. A string used as a call *argument* (see
    the module docstring) is a different shape and is left untouched.
    """
    lines = text.splitlines(keepends=True)
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, SyntaxError, IndentationError) as exc:
        raise UnparseableSourceError(str(exc)) from exc
    at_stmt_start = True
    for index, tok in enumerate(tokens):
        if tok.type == tokenize.COMMENT:
            _blank(lines, tok.start, tok.end)
            continue
        if tok.type == tokenize.STRING and at_stmt_start:
            rest = tokens[index + 1 :]
            next_tok = next((t for t in rest if t.type not in (tokenize.COMMENT, tokenize.NL)), None)
            if next_tok is None or next_tok.type in (tokenize.NEWLINE, tokenize.ENDMARKER):
                _blank(lines, tok.start, tok.end)
        if tok.type not in _STATEMENT_JOINERS + (tokenize.COMMENT,):
            at_stmt_start = tok.type == tokenize.NEWLINE
    return "".join(lines)
