# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Split a shell command line into the commands it runs (#19462).

Risk assessment and learned auto-approve rules must judge every command a line
runs, not only the first one: ``cat x | sh`` is two commands, and naming it by
``cat`` alone rated it SAFE. This is the one splitter both use.

Separators are recognised outside quotes only: ``;``, ``&&``, ``||``, ``|``,
``|&``, ``&`` and newline. A ``&`` or ``|`` that belongs to a redirection
(``2>&1``, ``&>``, ``<&``, ``>|``) is not a separator. Command substitution is
not parsed here; ``security.command_patterns`` forbids it outright.

An unterminated quote never makes the scanner give up: separators before the
quote still split, and the rest of the line stays in the last segment, so a
trailing stray quote cannot hide the commands ahead of it.

A here-doc body (``<<WORD`` / ``<<-WORD`` with any quoting of ``WORD``) is data,
not shell: it is skipped from the end of its line to its terminator line, so an
apostrophe in the body cannot hide the commands after the terminator. A body
that never reaches its terminator line ends the split with ``UNTERMINATED_HEREDOC``,
which the risk check rates FORBIDDEN. That fails closed: the alternative, skipping to
the end as bash does, would trust this parser's reading of ``WORD`` -- a misread
delimiter would then hide every command after the real terminator. (``cat <<E``
with no line after it has no body to hide anything, so it splits normally.) A here-string
(``<<<``) is one ordinary word and is not a here-doc.
"""

from __future__ import annotations

from typing import AbstractSet, List, Optional, Tuple

#: Longest first, so ``&&`` is never read as two ``&``.
_OPERATORS = ("&&", "||", "|&", ";", "|", "&", "\n")

#: The segment standing for the rest of a line whose here-doc has no terminator.
UNTERMINATED_HEREDOC = "<<here-doc-without-terminator>>"

#: Characters that end a here-doc's delimiter word when unquoted.
_WORD_END = " \t\n;&|<>()"

#: A pending here-doc: its delimiter (``None`` if unreadable) and whether ``<<-`` strips tabs.
_HereDoc = Tuple[Optional[str], bool]


def _operator_at(command: str, i: int) -> str:
    """The separator starting at ``command[i]`` outside quotes, or ``""``."""
    prev = command[i - 1] if i > 0 else ""
    nxt = command[i + 1] if i + 1 < len(command) else ""
    for op in _OPERATORS:
        if not command.startswith(op, i):
            continue
        if op == "&" and (prev in ("<", ">") or nxt == ">"):
            return ""  # 2>&1, <&3, &>file: a redirection, not a separator
        if op == "|" and prev == ">":
            return ""  # >|file: clobbering redirection
        return op
    return ""


def _quoted_end(command: str, i: int, escapes: bool = False) -> int:
    """Index just past the quoted run opening at ``command[i]`` (or the end).

    ``escapes``: a backslash escapes inside it -- always for ``"``, and for
    ``'`` only in ANSI-C ``$'...'``, where ``\\'`` does not close the string.
    """
    quote = command[i]
    j = i + 1
    while j < len(command):
        if (quote == '"' or escapes) and command[j] == "\\":
            j += 2
            continue
        if command[j] == quote:
            return j + 1
        j += 1
    return len(command)


def _skip_literal(command: str, i: int) -> int | None:
    """Index past a quote, an escape or a comment at ``command[i]``; else ``None``.

    A comment runs to the newline, which is left to split: a quote inside a
    comment is not a quote to the shell, so ``ls #'`` + newline + ``sh`` runs ``sh``.
    """
    ch = command[i]
    if command.startswith("<<<", i):
        return i + 3  # a here-string: the word after it is ordinary shell text
    if ch == "$" and command.startswith("$'", i):
        return _quoted_end(command, i + 1, escapes=True)
    if ch in "'\"":
        return _quoted_end(command, i)
    if ch == "\\":
        return i + 2
    if ch == "#" and (i == 0 or command[i - 1] in " \t\n;&|()"):
        newline = command.find("\n", i)
        return len(command) if newline == -1 else newline
    return None


def split_command_line(command: str) -> List[Tuple[str, str]]:
    """``(segment, operator_after_it)`` pairs; the last operator is ``""``.

    Empty segments (``ls;``, ``a;;b``) are dropped, keeping the operator of the
    segment before them. Here-doc bodies are skipped (see the module docstring).
    """
    pairs: List[Tuple[str, str]] = []
    heredocs: List[_HereDoc] = []
    start = i = 0
    while 0 <= i < len(command):
        skipped = _skip_literal(command, i)
        if skipped is not None:
            i = skipped
        elif command.startswith("<<", i):
            i = _read_heredoc(command, i + 2, heredocs)
        elif op := _operator_at(command, i):
            _append(pairs, command[start:i], op)
            start = i = _past_bodies(command, i, heredocs) if op == "\n" and heredocs else i + len(op)
        else:
            i += 1
    if start < 0:  # a here-doc body never reached its terminator: fail closed (module docstring)
        pairs.append((UNTERMINATED_HEREDOC, ""))
    else:
        _append(pairs, command[start:], "")
    return pairs


def _read_heredoc(command: str, j: int, heredocs: List[_HereDoc]) -> int:
    """Record the here-doc whose ``<<`` ends at ``command[j]``; index past its word."""
    strip_tabs = command.startswith("-", j)
    j += strip_tabs
    while j < len(command) and command[j] in " \t":
        j += 1
    end, delimiter = _heredoc_word(command, j)
    heredocs.append((delimiter or None, strip_tabs))  # `<<` with no word never terminates
    return end


def _heredoc_word(command: str, j: int) -> Tuple[int, str]:
    """The delimiter word at ``command[j]`` with its quotes removed, as bash compares it."""
    word: List[str] = []
    while j < len(command) and command[j] not in _WORD_END:
        if command[j] in "'\"":
            close = _quoted_end(command, j)
            word.append(command[j + 1 : close - 1])
            j = close
        elif command[j] == "\\":
            word.append(command[j + 1 : j + 2])
            j += 2
        else:
            word.append(command[j])
            j += 1
    return j, "".join(word)


def _past_bodies(command: str, newline: int, heredocs: List[_HereDoc]) -> int:
    """Index of the newline ending the last pending terminator line, ``-1`` if one is missing.

    ``newline`` ends the line that opened them; bodies follow in order.
    """
    pos = newline
    for delimiter, strip_tabs in heredocs:
        while True:
            if pos >= len(command):
                return -1
            line_end = command.find("\n", pos + 1)
            line_end = len(command) if line_end == -1 else line_end
            line = command[pos + 1 : line_end]
            pos = line_end
            if delimiter is not None and (line.lstrip("\t") if strip_tabs else line) == delimiter:
                break
    heredocs.clear()
    return pos


#: Openers that wrap a command without being it: ``(cmd)``, ``{ cmd; }``, ``! cmd``.
_LEADING_WRAPPERS = ("(", "{", "!")

#: The options bash's ``time`` keyword takes before the command it times.
_TIME_OPTIONS = frozenset({"-p", "--"})


def _unwrapped(segment: str) -> str:
    """``segment`` without the grouping and prefix words around its command."""
    segment = segment.strip()
    while True:
        wrapper = next((w for w in _LEADING_WRAPPERS if segment.startswith(w)), None)
        inner = _past_time(segment) if wrapper is None else segment[len(wrapper) :].lstrip()
        if inner == segment:
            break
        segment = inner
    return _without_unbalanced_closers(segment)


def _past_time(segment: str) -> str:
    """``time -p -- cmd`` → ``cmd``; ``segment`` itself unless ``time`` wraps a command."""
    words = segment.split(None, 1)
    if len(words) < 2 or words[0] != "time":
        return segment
    while len(words) == 2 and words[0] in _TIME_OPTIONS | {"time"}:
        segment, words = words[1], words[1].split(None, 1)
    return segment


def _without_unbalanced_closers(segment: str) -> str:
    """Drop trailing ``)``/``}`` left by an opener on another segment; ``<(sh)`` keeps its own."""
    while segment and segment[-1] in ")}":
        closer, opener = segment[-1], "(" if segment[-1] == ")" else "{"
        if segment.count(closer) <= segment.count(opener):
            break
        segment = segment[:-1].rstrip()
    return segment


def _append(pairs: List[Tuple[str, str]], segment: str, op: str) -> None:
    """Add a non-empty segment; an empty one passes its operator to the last."""
    segment = _unwrapped(segment)
    if segment:
        pairs.append((segment, op))
    elif pairs and op:
        pairs[-1] = (pairs[-1][0], op)


def command_segments(command: str) -> List[str]:
    """The commands ``command`` runs, in order (one entry for a plain command)."""
    return [segment for segment, _op in split_command_line(command)]


def unparsed_segment_reasons(segments: List[str]) -> List[str]:
    """Why ``segments`` must be FORBIDDEN unread: a here-doc that never terminates."""
    return ["Here-doc without a terminator line (#19462)"] if UNTERMINATED_HEREDOC in segments else []


def single_command_pattern(command: str, subcommand_tools: AbstractSet[str]) -> str:
    """Pattern for one command: ``ls -la`` → ``ls *``, ``git status x`` → ``git status *``."""
    parts = command.split()
    if not parts:
        return command
    base_cmd = parts[0]
    if len(parts) == 1:
        return base_cmd
    # Issue #326: tools with subcommands keep the subcommand in the pattern
    if base_cmd in subcommand_tools:
        return f"{base_cmd} {parts[1]} *"
    return f"{base_cmd} *"


def command_line_pattern(command: str, subcommand_tools: AbstractSet[str]) -> str:
    """Auto-approve pattern for a whole line: one pattern per segment, operators kept.

    A plain command keeps its historical pattern, so stored rules still match.
    ``cat a && sh`` → ``cat * && sh`` and ``cat a &`` → ``cat * &``, which a
    stored ``cat *`` rule cannot match. ``a`` + newline + ``b`` equals ``a; b``.
    """
    pairs = split_command_line(command)
    if not pairs:
        return command
    if pairs == [(command, "")]:
        return single_command_pattern(command, subcommand_tools)
    # A newline separates exactly as `;` does, so it renders as `;`: `npm` + newline +
    # `install x` must not collapse into the single-command pattern `npm install *`.
    rendered = ((single_command_pattern(seg, subcommand_tools), ";" if op == "\n" else op) for seg, op in pairs)
    return " ".join(f"{pattern} {op}".strip() for pattern, op in rendered)
