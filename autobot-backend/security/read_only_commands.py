# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Whether a shell command only reads (#19950).

``CommandRisk.SAFE`` does not mean this: ``git push``, ``curl -X POST``, ``find -delete`` and
``echo x > ~/.bashrc`` are all rated SAFE. This is a narrowing applied on top of that rating, not
a second risk classification: a command must be SAFE first, and then every segment must be on
this allowlist. Anything not recognised counts as not read-only, so it is held for a person.
"""

import shlex
from typing import FrozenSet, List, Mapping, Optional

from security.command_segments import command_segments

_READ_ONLY_BASES: FrozenSet[str] = frozenset(
    {
        "basename",
        "cat",
        "df",
        "dirname",
        "du",
        "egrep",
        "fgrep",
        "file",
        "grep",
        "head",
        "id",
        "ls",
        "ps",
        "pwd",
        "readlink",
        "realpath",
        "stat",
        "uname",
        "wc",
        "which",
        "whoami",
    }
)

#: Commands that read only with the right arguments, and the arguments that stop them reading.
_FORBIDDEN_FLAGS: Mapping[str, FrozenSet[str]] = {
    "find": frozenset({"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprint0", "-fprintf", "-fls"}),
    "tail": frozenset({"-f", "-F", "--follow", "--retry"}),
}

#: ``git`` subcommands that only read. ``--output`` makes them write a file.
_READ_ONLY_GIT_SUBCOMMANDS: FrozenSet[str] = frozenset({"diff", "log", "show", "status"})

_SHELL_OPERATOR_CHARS = frozenset("<>&;|()")


def _tokens(segment: str) -> Optional[List[str]]:
    """The segment's words, or ``None`` when it cannot be parsed or carries a shell operator."""
    lexer = shlex.shlex(segment, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        words = list(lexer)
    except ValueError:
        return None
    if not words or any(set(word) <= _SHELL_OPERATOR_CHARS for word in words):
        return None
    return words


def _segment_is_read_only(segment: str) -> bool:
    words = _tokens(segment)
    if words is None:
        return False
    base, args = words[0], words[1:]
    if base in _READ_ONLY_BASES:
        return True
    if base in _FORBIDDEN_FLAGS:
        return not any(arg.split("=", 1)[0] in _FORBIDDEN_FLAGS[base] for arg in args)
    if base == "git":
        return bool(args) and args[0] in _READ_ONLY_GIT_SUBCOMMANDS and not any(a.startswith("--output") for a in args)
    return False


def is_read_only_command(command: str) -> bool:
    """Whether every segment of *command* only reads. Unknown means no."""
    segments = command_segments(command)
    return bool(segments) and all(_segment_is_read_only(segment) for segment in segments)
