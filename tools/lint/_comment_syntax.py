# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The executable lines of a file, with its prose removed (#17941).

A guard that greps a file for a literal is satisfied when that literal appears
in the file's **own comment** -- so deleting the real thing leaves the guard
green. The comment explaining why a flag matters sits one line above the flag,
which is exactly the distance a whole-file substring check cannot see. Python
can retreat to an AST; shell, YAML and git hooks cannot, and those are written
to be self-documenting, so the hazard is worst exactly where the fallback is
missing.

Seven guards had each written their own stripper before this module existed,
with different blind spots and two different signatures. That duplication was
the enabler: a new text-keyed guard either rediscovered the problem,
re-implemented the fix, or forgot -- and forgetting is silent, because the
guard passes. One implementation, tested once, is the fix.

## What this does that the private copies did not

Every private copy dropped **whole-line** comments only, and
`git_repo_root_calls_are_guarded_17418_test` stated the reason honestly: a `#`
inside a string is not a comment, and a regex that ignores that reintroduces
the same class one level down. That reasoning was right, and it is why this
module scans character by character tracking quote state instead of using a
regex. A trailing comment is now stripped correctly, including the cases the
regex approach would have broken:

    echo "a # b"        # the inner # is data, the outer one is a comment
    grep '#!/bin/sh' f  # the # inside single quotes is data
    echo \\# literal     # an escaped # in shell is data

## What it deliberately does not do

Heredoc bodies are not parsed. Text inside `<<EOF ... EOF` is data, not code,
but tracking heredoc state needs a shell parser and the wrong answer there is
the permissive one. `strip_trailing=` therefore defaults to **False** for the
line-oriented API, so a caller opts in to the cleverness and the conservative
behaviour matches what the seven call sites already relied on.
"""

from __future__ import annotations

import re
from bisect import bisect_left
from pathlib import Path
from typing import Iterable, Iterator, NamedTuple, Sequence

#: Comment markers by file suffix. Selected by file type rather than assumed,
#: because the whole point is that the caller's file may not be Python.
_MARKERS: dict[str, tuple[str, ...]] = {
    ".py": ("#",),
    ".sh": ("#",),
    ".bash": ("#",),
    ".yml": ("#",),
    ".yaml": ("#",),
    ".toml": ("#",),
    ".cfg": ("#",),
    ".ini": ("#",),
    ".ts": ("//",),
    ".mts": ("//",),
    ".cts": ("//",),
    ".js": ("//",),
    ".mjs": ("//",),
    ".cjs": ("//",),
    ".vue": ("//",),
    ".json5": ("//",),
}

#: Files with no suffix -- git hooks, `install.sh`-style scripts invoked by
#: name. Hash is the only sane default and is what every such file here uses.
_DEFAULT_MARKERS: tuple[str, ...] = ("#",)

#: Suffixes whose quoting rules include a backslash escape outside quotes.
#: In shell `echo \# x` prints a literal `#`; in Python it does not.
_BACKSLASH_ESCAPES = frozenset({".sh", ".bash", ""})

#: Suffixes with C-style block comments. `slm_frontend_i18n_parity_test` had to
#: handle these and did it by anchoring `/*` to a line start or whitespace,
#: because `import.meta.glob('../locales/*.json')` contains `/*` and an
#: unanchored pattern ate the rest of the file up to the next `*/` -- failing on
#: the very line it guards. The anchor was a heuristic; quote tracking is the
#: actual answer, since a `/*` inside a string literal is data in every case the
#: heuristic was approximating.
_BLOCK_COMMENTS = frozenset({".ts", ".mts", ".cts", ".js", ".mjs", ".cjs", ".vue", ".json5"})


class CodeLine(NamedTuple):
    """One executable line: its 1-based number and its text."""

    lineno: int
    text: str


def markers_for(name: str | Path) -> tuple[str, ...]:
    """Comment markers for a file, chosen by suffix."""
    return _MARKERS.get(Path(name).suffix, _DEFAULT_MARKERS)


def strip_trailing_comment(line: str, markers: Sequence[str], *, escapes: bool = False) -> str:
    """*line* with any trailing comment removed, respecting quotes.

    Scans character by character rather than matching a pattern, because the
    only way to know whether a `#` opens a comment is to know whether it is
    inside a quoted run. `escapes` enables shell's backslash, where `\\#` is a
    literal and does not start a comment.
    """
    quote: str | None = None
    i = 0
    while i < len(line):
        char = line[i]
        if escapes and char == "\\" and quote != "'":
            i += 2  # the next character is data whatever it is
            continue
        if quote is not None:
            if char == quote:
                quote = None
            i += 1
            continue
        if char in ("'", '"'):
            quote = char
            i += 1
            continue
        for marker in markers:
            if line.startswith(marker, i):
                return line[:i]
        i += 1
    return line


#: A `/` after one of these (or after nothing, or a newline) begins a regex literal, not a division. `<` and `>`
#: are left out: `</tag>` and `<br/>` are everywhere in `.vue`, `a < /re/` is not (`=>` is handled apart, as are
#: `++`/`--` and a postfix `!`). `of` and `in` are left out of the words: `of` is an ordinary identifier, and a regex
#: literal is neither iterable nor a sensible right operand of `in`.
_REGEX_AFTER = frozenset("(,=:[!&|?{};+-*%~^")
_REGEX_AFTER_WORDS = frozenset({"return", "typeof", "case", "void", "delete", "throw"})
_TRAILING_WORD = re.compile(r"[A-Za-z0-9_$]+$")


def _ends_with_regex_word(before: str) -> bool:
    """Whether *before* ends in a keyword after which an expression, and so a regex, may start."""
    word = _TRAILING_WORD.search(before)
    return word is not None and word.group() in _REGEX_AFTER_WORDS


def _prefix_position(prior: str) -> bool:
    """Whether a `!` that follows *prior* negates (so a regex may follow it) rather than asserts non-null (`x!`)."""
    if not prior or prior[-1] not in ")]" and _TRAILING_WORD.search(prior) is None:
        return True
    return _ends_with_regex_word(prior)


class _BlockScan:
    """Position and string/comment state of one `strip_block_comments` pass; each method consumes one construct."""

    def __init__(self, text: str, line_comments: bool) -> None:
        self.text = text
        self.line_comments = line_comments
        self.out: list[str] = []
        self.recent = ""  # the last few emitted characters, runs of blanks collapsed to one
        self.size = 0  # characters emitted so far
        self.cuts: list[int] = []  # output offsets where a `//` comment starts: the one source for "where it begins"
        self.quote: str | None = None
        self.in_block = False
        self.i = 0

    def run(self) -> str:
        while self.i < len(self.text):
            if self.in_block:
                self._in_block()
            elif self.quote is not None:
                self._in_string()
            else:
                self._in_code()
        return "".join(self.out)

    def _emit(self, piece: str) -> None:
        self.out.append(piece)
        self.size += len(piece)
        if piece.strip(" \t"):
            self.recent = (self.recent + piece)[-16:]
        elif not self.recent.endswith(" "):
            self.recent += " "

    def _in_block(self) -> None:
        """Inside `/* ... */`: blank everything but newlines, leave at the closing `*/`."""
        if self.text.startswith("*/", self.i):
            self.in_block = False
            self.i += 2
            return
        self._emit("\n" if self.text[self.i] == "\n" else " ")
        self.i += 1

    def _in_string(self) -> None:
        """Inside a string literal: keep it, honour a backslash escape, leave at the matching quote."""
        char = self.text[self.i]
        if char == "\\":
            self._emit(self.text[self.i : self.i + 2])
            self.i += 2
            return
        if char == self.quote:
            self.quote = None
        self._emit(char)
        self.i += 1

    def _in_code(self) -> None:
        """Outside any string or block: open a string, a block, step over a `//` comment or a regex; else keep."""
        char = self.text[self.i]
        if char in ("'", '"', "`"):
            self.quote = char
        elif self.text.startswith("/*", self.i):
            self.in_block = True
            self.i += 2
            return
        elif self.line_comments and self.text.startswith("//", self.i):
            self.cuts.append(self.size)
            self._keep_to(self._line_end())
            return
        elif self.line_comments and char == "/" and self._regex_allowed() and self._regex_end():
            self._keep_to(self._regex_end())
            return
        self._emit(char)
        self.i += 1

    def _keep_to(self, end: int) -> None:
        self._emit(self.text[self.i : end])
        self.i = end

    def _line_end(self) -> int:
        end = self.text.find("\n", self.i)
        return len(self.text) if end < 0 else end

    def _regex_allowed(self) -> bool:
        """Whether a `/` here opens a regex literal: at a line start, or after an operator or a keyword."""
        before = self.recent.rstrip(" \t")
        if before[-2:] in ("++", "--"):
            return False  # a postfix increment ends an operand, so the slash divides
        if before[-2:] == "=>":
            return True  # an arrow function's body
        if before[-1:] == "!":
            return _prefix_position(before[:-1].rstrip(" \t"))
        if not before or before[-1] == "\n" or before[-1] in _REGEX_AFTER:
            return True
        return _ends_with_regex_word(before)

    def _regex_end(self) -> int:
        """Index after the closing `/` of the regex literal opening here, 0 when there is none to accept.

        0 when it does not close on this line, or when the close is followed by `/` or `*`: that is a division
        whose operand is followed by a comment opener, and the comment rules must see it.
        """
        in_class, j = False, self.i + 1
        while j < len(self.text) and self.text[j] != "\n":
            char = self.text[j]
            if char == "\\":
                j += 1
            elif char == "[":
                in_class = True
            elif char == "]":
                in_class = False
            elif char == "/" and not in_class:
                return 0 if self.text[j + 1 : j + 2] in ("/", "*") else j + 1
            j += 1
        return 0


def strip_block_comments(text: str, *, line_comments: bool = False) -> str:
    """*text* with `/* ... */` runs removed, respecting string literals.

    Quote-aware for the reason above: the construct that broke the heuristic
    was a glob pattern inside quotes, and tracking quotes answers that exactly
    rather than approximately. Newlines inside a removed run are preserved, so
    line numbers downstream still refer to the original file.

    `line_comments` makes the scan step over a `//` comment (outside a string)
    to the end of the line, keeping its text. Without it an apostrophe or `/*`
    in prose after `//` is read as code -- a `worker's` opens a "string" that
    swallows every later `/**/` glob in the file (#21509). Opt-in because CSS,
    the other direct caller, has no `//` comments.
    """
    return _BlockScan(text, line_comments).run()


def _scan_block_syntax(text: str, suffix: str) -> tuple[str, list[int] | None]:
    """*text* with block comments blanked, and the offsets where `//` comments start; `None` for other syntaxes."""
    if suffix not in _BLOCK_COMMENTS:
        return text, None
    scan = _BlockScan(text, True)
    return scan.run(), scan.cuts


def _cut_comment(raw: str, start: int, cuts: list[int]) -> str:
    """*raw* (the line that begins at output offset *start*) up to the `//` comment the scanner found in it.

    The scanner has already walked strings, templates, regex literals and block comments, so its offsets are the
    only answer to "where does a trailing comment begin" on this path; a quote-only re-scan of the line would
    disagree on a `//` inside a regex class.
    """
    index = bisect_left(cuts, start)
    if index < len(cuts) and cuts[index] < start + len(raw):
        return raw[: cuts[index] - start]
    return raw


def code_lines(
    source: str | Path,
    *,
    name: str | Path | None = None,
    strip_trailing: bool = False,
    join_continuations: bool = False,
) -> list[CodeLine]:
    """The lines of *source* that are not comments.

    *source* is the text, or a `Path` to read. `name` selects the comment
    syntax when the text is passed directly; with a `Path` the path supplies it.

    `join_continuations` folds backslash-continued lines into one entry,
    reported at the line number where the command **starts**. A guard that asks
    "does this command swallow its exit code" has to read the command, not the
    first physical line of it -- the redirect and the `|| true` can sit two
    lines below the thing the guard matched on.
    """
    text, name = _read(source, name)
    markers = markers_for(name) if name is not None else _DEFAULT_MARKERS
    suffix = Path(name).suffix if name is not None else ""
    text, cuts = _scan_block_syntax(text, suffix)
    trailing = (cuts, markers, suffix in _BACKSLASH_ESCAPES) if strip_trailing else None
    kept = _code_lines_of(text, markers, trailing)
    return _join_continuations(kept) if join_continuations else kept


def _read(source: str | Path, name: str | Path | None) -> tuple[str, str | Path | None]:
    """``(text, name)`` of *source*: a `Path` is read and names itself, a string is the text."""
    if isinstance(source, Path):
        return source.read_text(encoding="utf-8"), name or source
    return source, name


def _code_lines_of(text: str, markers: Sequence[str], trailing: tuple | None) -> list[CodeLine]:
    """The lines of *text* that do not start with a comment marker, each cut at its trailing comment if *trailing*.

    *trailing* is ``(scanner cuts or None, markers, backslash escapes)``; the scanner's cuts decide where a `//`
    comment starts on the block-comment suffixes, `strip_trailing_comment` everywhere else.
    """
    kept: list[CodeLine] = []
    offset = 0
    for lineno, (raw, whole) in enumerate(zip(text.splitlines(), text.splitlines(True)), 1):
        start, offset = offset, offset + len(whole)
        if any(raw.lstrip().startswith(marker) for marker in markers):
            continue
        kept.append(CodeLine(lineno, _cut_trailing(raw, start, trailing) if trailing else raw))
    return kept


def _cut_trailing(raw: str, start: int, trailing: tuple) -> str:
    cuts, markers, escapes = trailing
    if cuts is None:
        return strip_trailing_comment(raw, markers, escapes=escapes)
    return _cut_comment(raw, start, cuts)


def _join_continuations(lines: Iterable[CodeLine]) -> list[CodeLine]:
    """Fold backslash-continued lines, keeping the first line's number.

    Delegates to `_scan_helpers.logical_lines`, which already owns this fold
    and carries the subtlety worth not re-deriving: a whole-line comment never
    continues, because bash ends a comment at the newline, so folding a
    trailing backslash inside one would glue the next line behind a `#`
    (#16414). A second fold here would be the duplication this module exists
    to end, one level down.
    """
    from tools.lint._scan_helpers import logical_lines

    numbers = [line.lineno for line in lines]
    folded = logical_lines("\n".join(line.text for line in lines))
    # `logical_lines` numbers against the text it was handed, which comment
    # removal has already perforated; map its indices back to the real file.
    return [CodeLine(numbers[i - 1] if 0 < i <= len(numbers) else i, body) for i, body in folded]


def code_text(source: str | Path, **kwargs) -> str:
    """`code_lines` rejoined, for callers that search the whole file at once."""
    return "\n".join(line.text for line in code_lines(source, **kwargs))


def iter_code_lines(source: str | Path, **kwargs) -> Iterator[CodeLine]:
    """Streaming form, for the call sites written against a generator."""
    yield from code_lines(source, **kwargs)
