# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one lexer for the JS family and the other `/* */` languages (#22194).

It names every piece of a text -- ``code``, ``string``, ``regex``, ``line_comment``
or ``block_comment`` -- and the pieces join back to the text exactly. Two callers
read it: the comment-syntax helper behind the repo guards
(``tools/lint/_comment_syntax.py``) and the duplicate-code normalizers
(``autobot-backend/api/codebase_analytics/duplicate_blocks.py``). Before this
module each carried its own copy and the two disagreed on which ``/`` opens a
regex literal.

Rules, all stated once here:

* A ``'`` or ``"`` string ends at its quote or at a newline, whichever comes
  first: an apostrophe in prose must not swallow the rest of the file (#21571).
* A template literal runs across newlines and nests: ``${`` opens an
  expression that is code again (comments, strings and further templates
  inside it are lexed as such) until its matching ``}``. The nesting is an
  explicit stack, so depth is bounded by memory and never by recursion.
* With ``line_comments`` (JS, TS, Vue scripts) a ``//`` comment runs to the end
  of its line, and a ``/`` where an operand may start opens a regex literal
  when it closes on the same line. Without it (CSS) neither exists, and a
  template literal is flat text to its closing backtick: with no regex rule an
  expression such as ``${c.replace(/"/g, '""')}`` cannot be lexed, and CSS has
  no templates to nest.

The regex-or-division decision reads the last few characters lexed, with
block comments as blanks; a ``/`` is a regex at a line start, after an operator
in ``REGEX_AFTER``, after a keyword in ``REGEX_AFTER_WORDS``, after ``=>`` or
after a prefix ``!``; never after ``++``/``--`` (they end an operand). ``<`` and
``>`` are left out (``</tag>`` and ``<br/>`` are everywhere in ``.vue``), as are
``in`` and ``of`` (a regex is neither iterable nor a sensible right operand of
``in``). Every regex scan remembers what it found from each position it read,
so a later ``/`` on the same line does not rescan it: a minified one-line file
stays linear.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

CODE, STRING, REGEX, LINE_COMMENT, BLOCK_COMMENT = "code", "string", "regex", "line_comment", "block_comment"
#: The two comment kinds, for a caller that drops comments whatever their form.
COMMENT_KINDS = frozenset({LINE_COMMENT, BLOCK_COMMENT})

#: A `/` after one of these (or after nothing, or a newline) begins a regex literal, not a division.
REGEX_AFTER = frozenset("(,=:[!&|?{};+-*%~^")
#: A `/` after one of these keywords begins a regex literal.
REGEX_AFTER_WORDS = frozenset({"return", "typeof", "case", "void", "delete", "throw"})

_TRAILING_WORD = re.compile(r"[A-Za-z0-9_$]+$")
_BLANK_RUN = re.compile(r"[ \t]+")
_NOT_NEWLINE = re.compile(r"[^\n]")
#: Characters of code that never start a construct: consumed as one run.
_PLAIN_CODE = re.compile(r"[^'\"`/{}]+")
_QUOTED_BODY = {q: re.compile(r"(?:[^%s\\\n]+|\\(?:\r\n|[\s\S])?)*" % q) for q in ("'", '"')}
_TEMPLATE_BODY = re.compile(r"(?:[^`\\$]+|\\(?:\r\n|[\s\S])?|\$(?!\{))*")
_FLAT_TEMPLATE_BODY = re.compile(r"(?:[^`\\]+|\\(?:\r\n|[\s\S])?)*")
_RECENT_SIZE = 16


@dataclass(frozen=True)
class JsLex:
    """A lexed text: its ``(kind, piece)`` pairs, which join back to it, and what it ended inside, if anything."""

    pieces: list[tuple[str, str]]
    #: ``"block comment"`` or ``"quote"`` (a string or template literal) when the text ends inside one; else None.
    unterminated: str | None


def _match_end(pattern: re.Pattern[str], text: str, pos: int) -> int:
    """Where *pattern*'s match at *pos* ends; every pattern passed here matches there, if only empty."""
    found = pattern.match(text, pos)
    if found is None:
        raise RuntimeError(f"js_lexer: {pattern.pattern!r} did not match at {pos}; the lexer's invariant is broken")
    return found.end()


def _ends_with_regex_word(before: str) -> bool:
    """Whether *before* ends in a keyword after which an expression, and so a regex, may start."""
    word = _TRAILING_WORD.search(before)
    return word is not None and word.group() in REGEX_AFTER_WORDS


def _prefix_position(prior: str) -> bool:
    """Whether a `!` that follows *prior* negates (so a regex may follow it) rather than asserts non-null (`x!`)."""
    if not prior or prior[-1] not in ")]" and _TRAILING_WORD.search(prior) is None:
        return True
    return _ends_with_regex_word(prior)


def regex_allowed(recent: str) -> bool:
    """Whether a `/` after the lexed tail *recent* opens a regex literal rather than divides."""
    before = recent.rstrip(" \t")
    if before[-2:] in ("++", "--"):
        return False  # a postfix increment ends an operand, so the slash divides
    if before[-2:] == "=>":
        return True  # an arrow function's body
    if before[-1:] == "!":
        return _prefix_position(before[:-1].rstrip(" \t"))
    if not before or before[-1] == "\n" or before[-1] in REGEX_AFTER:
        return True
    return _ends_with_regex_word(before)


class _Lexer:
    """One pass over a text; code is the only mode, every other construct is consumed whole."""

    def __init__(self, text: str, line_comments: bool) -> None:
        self.text = text
        self.line_comments = line_comments
        self.spans: list[list[Any]] = []  # [kind, start, end]; adjacent code spans are merged
        self.recent = ""  # the last few characters lexed, runs of blanks collapsed to one
        self.depths: list[int] = []  # one brace depth per open `${`, innermost last
        self.unterminated: str | None = None
        self.regex_memo: dict[int, int] = {}  # 2 * position + in-class -> the regex close found from there, or -1
        self.i = 0

    def run(self) -> JsLex:
        while self.i < len(self.text):
            self._code()
        if self.unterminated is None and self.depths:
            self.unterminated = "quote"  # ended inside a template literal's `${`
        pieces = [(kind, self.text[start:end]) for kind, start, end in self.spans]
        return JsLex(pieces, self.unterminated)

    def _code(self) -> None:
        """Consume the construct at ``self.i``; a plain-code run, or one opener."""
        text, i = self.text, self.i
        char = text[i]
        if char in ("'", '"'):
            self._quoted(char)
        elif char == "`":
            self._template_text(i, i + 1)
        elif text.startswith("/*", i):
            self._block_comment()
        elif char == "/":
            self._slash()
        elif char in "{}":
            self._brace(char)
        else:
            self._add(CODE, _match_end(_PLAIN_CODE, text, i))

    def _slash(self) -> None:
        """A `/` in code: a `//` comment, a regex literal, or a division."""
        if self.line_comments and self.text.startswith("//", self.i):
            end = self.text.find("\n", self.i)
            self._add(LINE_COMMENT, len(self.text) if end < 0 else end)
            return
        end = self._regex_end() if self.line_comments and regex_allowed(self.recent) else 0
        if end:
            self._add(REGEX, end)
        else:
            self._add(CODE, self.i + 1)

    def _regex_end(self) -> int:
        """Index after the closing `/` of the regex literal opening here, 0 when there is none to accept.

        0 when it does not close on this line, or when the close is followed by `/` or `*`: that is a division
        whose operand is followed by a comment opener, and the comment rules must see it.
        """
        close = self._regex_close()
        if close < 0 or self.text[close + 1 : close + 2] in ("/", "*"):
            return 0
        return close + 1

    def _regex_close(self) -> int:
        """Index of the `/` closing a regex literal opened at ``self.i``, -1 when the line ends first.

        Every ``(in class, position)`` a scan reads is remembered with its answer, which depends on nothing else:
        a later scan that reaches one stops there, so the scans of a whole text read each position at most twice.
        """
        text, memo, path = self.text, self.regex_memo, []
        in_class, j, close = False, self.i + 1, -1
        while j < len(text) and text[j] != "\n":
            key = 2 * j + in_class
            if key in memo:
                close = memo[key]
                break
            path.append(key)
            char = text[j]
            if char == "\\":
                j += 1  # an escape: the next character, a newline included, is part of the literal
            elif char == "[" and not in_class:
                in_class = True
            elif char == "]" and in_class:
                in_class = False
            elif char == "/" and not in_class:
                close = j
                break
            j += 1
        memo.update(dict.fromkeys(path, close))
        return close

    def _brace(self, char: str) -> None:
        """A brace: inside a `${` it counts depth, and its own closing `}` resumes the template text."""
        if self.depths and char == "}" and self.depths[-1] == 0:
            self.depths.pop()
            self._add(CODE, self.i + 1)
            self._template_text(self.i, self.i)
            return
        if self.depths:
            self.depths[-1] += 1 if char == "{" else -1
        self._add(CODE, self.i + 1)

    def _quoted(self, quote: str) -> None:
        """A `'` or `"` string: to its quote, to the end of its line (both kept), or to the end of the text."""
        end = _match_end(_QUOTED_BODY[quote], self.text, self.i + 1)
        if end < len(self.text):
            end += 1  # the closing quote, or the newline that ends an unclosed one
        else:
            self.unterminated = "quote"
        self._add(STRING, end)

    def _template_text(self, start: int, scan_from: int) -> None:
        """Template text from *start*: to its closing backtick, or to a `${` that opens an expression."""
        body = _TEMPLATE_BODY if self.line_comments else _FLAT_TEMPLATE_BODY
        end = _match_end(body, self.text, scan_from)
        if end >= len(self.text):
            self.unterminated = "quote"
            self._add(STRING, end, start)
        elif self.text[end] == "`":
            self._add(STRING, end + 1, start)
        else:
            self._add(STRING, end, start)
            self.depths.append(0)
            self._add(CODE, end + 2)

    def _block_comment(self) -> None:
        """A `/* */` comment, to its close or to the end of the text."""
        end = self.text.find("*/", self.i + 2)
        if end < 0:
            self.unterminated = "block comment"
        self._add(BLOCK_COMMENT, len(self.text) if end < 0 else end + 2)

    def _add(self, kind: str, end: int, start: int | None = None) -> None:
        """Record ``text[start:end]`` (from ``self.i`` by default) as one *kind* piece and move past it."""
        start = self.i if start is None else start
        if start < end:
            if kind == CODE and self.spans and self.spans[-1][0] == CODE and self.spans[-1][2] == start:
                self.spans[-1][2] = end
            else:
                self.spans.append([kind, start, end])
            self._note(kind, self.text[start:end])
        self.i = end

    def _note(self, kind: str, piece: str) -> None:
        """Fold *piece* into ``self.recent`` as the regex rule reads it: a block comment as its blanks."""
        if kind in (LINE_COMMENT, REGEX):
            self.recent = (self.recent + piece)[-_RECENT_SIZE:]
            return
        if kind == BLOCK_COMMENT:
            piece = _NOT_NEWLINE.sub(" ", _comment_body(piece))
        folded = _BLANK_RUN.sub(" ", piece)
        if self.recent.endswith(" ") and folded.startswith(" "):
            folded = folded[1:]
        if not folded.strip(" "):
            self.recent += folded
        elif folded.endswith(" "):
            self.recent = (self.recent + folded[:-1])[-_RECENT_SIZE:] + " "
        else:
            self.recent = (self.recent + folded)[-_RECENT_SIZE:]


def _comment_body(piece: str) -> str:
    """A `/* */` comment without its delimiters; an unclosed one has only its opener."""
    return piece[2:-2] if len(piece) >= 4 and piece.endswith("*/") else piece[2:]


def blank_block_comment(piece: str) -> str:
    """A `/* */` comment's body as blanks, newlines kept, so line numbers downstream still hold."""
    return _NOT_NEWLINE.sub(" ", _comment_body(piece))


def lex_js(text: str, *, line_comments: bool = True) -> JsLex:
    """*text* as ``(kind, piece)`` pairs that join back to it; see the module docstring for the rules."""
    return _Lexer(text, line_comments).run()
