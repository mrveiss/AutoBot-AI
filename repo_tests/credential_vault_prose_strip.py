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

Two prose shapes need a run of tokens, not a single one, to recognise (#15285):
implicit string concatenation (``"a" "b"``) puts a second ``STRING`` where the
single-token check expects ``NEWLINE``, and an f-string is not a ``STRING`` at
all under PEP 701 (3.12+) -- it decomposes into ``FSTRING_START`` /
``FSTRING_MIDDLE`` / ``FSTRING_END``. :func:`_floating_literal_run_end` folds
both into the same "one floating statement" unit the trailing-token test uses.
"""

from __future__ import annotations

import io
import tokenize

#: Token types that only delimit statements/lines, never contribute a statement's
#: own content -- excluded when deciding whether a STRING token opens a new
#: statement (a docstring), so a blank line or an indent/dedent never resets that.
_STATEMENT_JOINERS = (tokenize.NL, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING)

#: Python 3.10 tokenizes an f-string as a single STRING; 3.12+ (PEP 701) splits it
#: into FSTRING_START ... FSTRING_END. These are ``None`` on 3.10, where they
#: simply never match any real token's ``.type``.
_FSTRING_START = getattr(tokenize, "FSTRING_START", None)
_FSTRING_END = getattr(tokenize, "FSTRING_END", None)

#: Tokens that may sit between two literals of an implicitly-concatenated string
#: statement (inside parens, or a continuation) without ending the run.
_RUN_GAP_TOKENS = (tokenize.NL, tokenize.COMMENT)


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


def _one_literal_end(tokens: list, start: int) -> int:
    """Return the index of the last token of the single literal starting at
    ``start`` -- itself for a plain ``STRING``, or the matching ``FSTRING_END``
    for an ``FSTRING_START`` (tracking nesting, since 3.12+ allows an f-string
    literal inside another f-string's ``{...}``).
    """
    if tokens[start].type != _FSTRING_START:
        return start
    depth, index = 1, start + 1
    while depth > 0 and index < len(tokens):
        if tokens[index].type == _FSTRING_START:
            depth += 1
        elif tokens[index].type == _FSTRING_END:
            depth -= 1
        index += 1
    return index - 1


def _floating_literal_run_end(tokens: list, start: int) -> int:
    """Return the index of the last token belonging to the (possibly implicitly
    concatenated) string/f-string literal run beginning at ``start``, so the
    whole run is treated as one unit for the "followed by NEWLINE" test.
    """
    last = _one_literal_end(tokens, start)
    peek = last + 1
    while peek < len(tokens) and tokens[peek].type in _RUN_GAP_TOKENS:
        peek += 1
    if peek < len(tokens) and tokens[peek].type in (tokenize.STRING, _FSTRING_START):
        return _floating_literal_run_end(tokens, peek)
    return last


def _next_real_token(tokens: list, after: int):
    """First token after index ``after`` that isn't a comment or a blank line."""
    rest = tokens[after + 1 :]
    return next((t for t in rest if t.type not in (tokenize.COMMENT, tokenize.NL)), None)


def _consume_floating_literal(tokens: list, lines: list[str], index: int) -> int:
    """Blank the floating literal run starting at ``tokens[index]`` when it is a
    whole statement (run followed by NEWLINE/ENDMARKER), then return the index of
    the token right after the run either way.
    """
    end_index = _floating_literal_run_end(tokens, index)
    next_tok = _next_real_token(tokens, end_index)
    if next_tok is None or next_tok.type in (tokenize.NEWLINE, tokenize.ENDMARKER):
        _blank(lines, tokens[index].start, tokens[end_index].end)
    return end_index + 1


def _paren_wrapped_run(tokens: list, index: int):
    """If ``tokens[index]`` opens ``( <literal run> )`` with nothing else inside
    -- parens solely grouping a literal, which Python still recognises as a
    docstring (parens don't create their own AST node) -- return
    ``(run_start, run_end, close_index)``; otherwise ``None``.
    """
    if not (tokens[index].type == tokenize.OP and tokens[index].string == "("):
        return None
    peek = index + 1
    while peek < len(tokens) and tokens[peek].type in _RUN_GAP_TOKENS:
        peek += 1
    if peek >= len(tokens) or tokens[peek].type not in (tokenize.STRING, _FSTRING_START):
        return None
    run_end = _floating_literal_run_end(tokens, peek)
    close = run_end + 1
    while close < len(tokens) and tokens[close].type in _RUN_GAP_TOKENS:
        close += 1
    if close >= len(tokens) or not (tokens[close].type == tokenize.OP and tokens[close].string == ")"):
        return None
    return peek, run_end, close


def _consume_paren_literal(tokens: list, lines: list[str], index: int) -> int | None:
    """Blank a ``_paren_wrapped_run`` at ``tokens[index]`` when the closing paren
    is itself followed by NEWLINE/ENDMARKER, then return the index of the token
    right after the ``)``. Returns ``None`` when ``tokens[index]`` isn't such a
    run at all, so the caller falls back to ordinary token handling.
    """
    run = _paren_wrapped_run(tokens, index)
    if run is None:
        return None
    run_start, run_end, close_index = run
    next_tok = _next_real_token(tokens, close_index)
    if next_tok is None or next_tok.type in (tokenize.NEWLINE, tokenize.ENDMARKER):
        _blank(lines, tokens[run_start].start, tokens[run_end].end)
    return close_index + 1


def strip_prose(text: str) -> str:
    """Blank every comment and *floating* string statement in *text*.

    "Floating" means a run of one or more adjacent STRING/f-string literals --
    plain, implicitly concatenated, or wrapped in a bare pair of parens for a
    line continuation -- forms a whole statement by itself: a docstring or a
    bare string/f-string used as an inline comment. A string used as a call
    *argument* (see the module docstring) is a different shape and is left
    untouched.
    """
    lines = text.splitlines(keepends=True)
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, SyntaxError, IndentationError) as exc:
        raise UnparseableSourceError(str(exc)) from exc
    at_stmt_start = True
    index = 0
    while index < len(tokens):
        tok = tokens[index]
        if tok.type == tokenize.COMMENT:
            _blank(lines, tok.start, tok.end)
            index += 1
            continue
        if tok.type in (tokenize.STRING, _FSTRING_START) and at_stmt_start:
            index = _consume_floating_literal(tokens, lines, index)
            at_stmt_start = False
            continue
        if at_stmt_start:
            next_index = _consume_paren_literal(tokens, lines, index)
            if next_index is not None:
                index = next_index
                at_stmt_start = False
                continue
        if tok.type not in _STATEMENT_JOINERS:
            at_stmt_start = tok.type == tokenize.NEWLINE
        index += 1
    return "".join(lines)
