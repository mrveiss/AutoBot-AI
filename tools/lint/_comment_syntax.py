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
_BLOCK_COMMENTS = frozenset({".ts", ".js", ".mjs", ".cjs", ".vue", ".json5"})


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


def strip_block_comments(text: str) -> str:
    """*text* with `/* ... */` runs removed, respecting string literals.

    Quote-aware for the reason above: the construct that broke the heuristic
    was a glob pattern inside quotes, and tracking quotes answers that exactly
    rather than approximately. Newlines inside a removed run are preserved, so
    line numbers downstream still refer to the original file.
    """
    out: list[str] = []
    quote: str | None = None
    in_block = False
    i = 0
    while i < len(text):
        char = text[i]
        if in_block:
            if text.startswith("*/", i):
                in_block = False
                i += 2
                continue
            out.append("\n" if char == "\n" else " ")
            i += 1
            continue
        if quote is not None:
            if char == "\\":
                out.append(text[i : i + 2])
                i += 2
                continue
            if char == quote:
                quote = None
            out.append(char)
            i += 1
            continue
        if char in ("'", '"', "`"):
            quote = char
            out.append(char)
            i += 1
            continue
        if text.startswith("/*", i):
            in_block = True
            i += 2
            continue
        out.append(char)
        i += 1
    return "".join(out)


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
    if isinstance(source, Path):
        name = name or source
        text = source.read_text(encoding="utf-8")
    else:
        text = source
    markers = markers_for(name) if name is not None else _DEFAULT_MARKERS
    suffix = Path(name).suffix if name is not None else ""
    escapes = suffix in _BACKSLASH_ESCAPES
    if suffix in _BLOCK_COMMENTS:
        text = strip_block_comments(text)

    kept: list[CodeLine] = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        stripped = raw.lstrip()
        if any(stripped.startswith(marker) for marker in markers):
            continue
        kept.append(CodeLine(lineno, strip_trailing_comment(raw, markers, escapes=escapes) if strip_trailing else raw))

    if join_continuations:
        kept = _join_continuations(kept)
    return kept


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
