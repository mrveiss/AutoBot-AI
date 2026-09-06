# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shell lexing for ``git_invocation_parse.py``: words, quoting, heredocs.

Split out of that module in #15835, along the seam it already had. Everything
here answers "what are the words of this command line, and where does one
command end" and knows nothing about git; ``git_invocation_parse.py`` reads
git's grammar out of the words this produces. ``repo_tests/
sys_modules_leak_guard.py`` and its ``_test.py`` are divided on the same seam.

The scope of the shell parsing -- what is tracked and what is deliberately not
understood -- is stated once, in ``git_invocation_parse.py``'s module
docstring. This file is that contract's implementation, not a second copy of
it, so it is the wrong place to look for the reasoning.
"""

from __future__ import annotations

import shlex

# Marks an unquoted newline, which separates commands exactly like ``;`` does.
# shlex treats newlines as plain whitespace once ``whitespace_split`` is on, so
# without this an invocation on the second line would look like an argument of
# the command on the first.
SENTINEL = "\x1eNL\x1e"

#: Tokens made only of these characters end one command and start another.
_SEPARATOR_CHARS = set(";&|")


def is_redirect(token: str) -> bool:
    """True for a redirection operator token (``>``, ``>>``, ``2>&1``'s ``>&``)."""
    return bool(token) and (token[0] in "<>" or token in ("&>", "&>>"))


def is_separator(token: str) -> bool:
    """True for ``;``, ``&&``, ``||``, ``|``, ``&`` and the newline sentinel."""
    return token == SENTINEL or (bool(token) and set(token) <= _SEPARATOR_CHARS)


def _read_word(src: str, index: int) -> tuple[str, int]:
    """Read one (possibly quoted) shell word starting at *index*."""
    letters: list[str] = []
    quote: str | None = None
    while index < len(src):
        char = src[index]
        if quote is not None:
            if char == quote:
                quote = None
            else:
                letters.append(char)
            index += 1
            continue
        if char in "'\"":
            quote = char
            index += 1
            continue
        if char == "\\":
            index += 1
            if index < len(src):
                letters.append(src[index])
                index += 1
            continue
        if char.isspace() or char in ";|&()<>":
            break
        letters.append(char)
        index += 1
    return "".join(letters), index


def _terminator_end(src: str, start: int, delimiter: str) -> int:
    """Index just past the line that closes a heredoc opened with *delimiter*."""
    cursor = start
    while cursor <= len(src):
        newline = src.find("\n", cursor)
        line = src[cursor:] if newline == -1 else src[cursor:newline]
        if line.strip() == delimiter:
            return len(src) if newline == -1 else newline + 1
        if newline == -1:
            return len(src)
        cursor = newline + 1
    return len(src)


class _Normalizer:
    """Rewrite a shell command so shlex can tokenize it with commands intact."""

    def __init__(self, src: str) -> None:
        self.src = src
        self.out: list[str] = []
        self.pos = 0
        self.quote: str | None = None
        self.subst: list[str | None] = []

    def run(self) -> str | None:
        """Normalized command, or ``None`` when the source cannot be parsed."""
        while self.pos < len(self.src):
            if self.quote == "'":
                self._single()
            elif self.quote == '"':
                self._double()
            else:
                self._plain()
        if self.quote is not None or self.subst:
            return None
        return "".join(self.out)

    def _emit(self, text: str, consumed: int) -> None:
        self.out.append(text)
        self.pos += consumed

    def _single(self) -> None:
        char = self.src[self.pos]
        if char == "'":
            self.quote = None
        self._emit(char, 1)

    def _double(self) -> None:
        src, pos = self.src, self.pos
        if src[pos] == "\\":
            self._emit(src[pos : pos + 2], 2)
            return
        if src.startswith("$(", pos):
            # Close the string, let the substitution run at a command position,
            # and reopen the string when it ends. A substitution inside double
            # quotes really does invoke commands; without this rewrite the whole
            # string would be one opaque token and the invocation invisible.
            self.subst.append('"')
            self.quote = None
            self._emit('" ' + SENTINEL + " $(", 2)
            return
        if src[pos] == '"':
            self.quote = None
        self._emit(src[pos], 1)

    def _plain(self) -> None:
        src, pos = self.src, self.pos
        char = src[pos]
        if char == "\\":
            self._emit(src[pos : pos + 2], 2)
        elif char == "\n":
            self._emit(" " + SENTINEL + " ", 1)
        elif char in "'\"":
            self.quote = char
            self._emit(char, 1)
        elif src.startswith("$(", pos):
            self.subst.append(None)
            self._emit("$(", 2)
        elif char == ")" and self.subst:
            self._close_subst()
        elif src.startswith("<<", pos) and not src.startswith("<<<", pos) and self._skip_heredoc():
            return
        else:
            self._emit(char, 1)

    def _close_subst(self) -> None:
        if self.subst.pop() == '"':
            self.quote = '"'
            self._emit(") " + SENTINEL + ' "', 1)
        else:
            self._emit(")", 1)

    def _skip_heredoc(self) -> bool:
        """Drop the heredoc body opened here; keep the rest of the line."""
        src = self.src
        cursor = self.pos + 2
        if cursor < len(src) and src[cursor] == "-":
            cursor += 1
        while cursor < len(src) and src[cursor] in " \t":
            cursor += 1
        delimiter, cursor = _read_word(src, cursor)
        newline = src.find("\n", cursor)
        if not delimiter or newline == -1:
            return False
        body_start = newline + 1
        self.src = src[:body_start] + src[_terminator_end(src, body_start, delimiter) :]
        self.out.append(" ")
        self.pos = cursor
        return True


def tokenize(command: str) -> list[str] | None:
    """Shell tokens for *command*, or ``None`` when it cannot be tokenized."""
    normalized = _Normalizer(command).run()
    if normalized is None:
        return None
    try:
        lexer = shlex.shlex(normalized, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError:
        return None
