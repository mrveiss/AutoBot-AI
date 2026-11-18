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

import os
import re
import shlex
from typing import FrozenSet, List, Optional

from autobot_shared.secret_file_names import is_secret_file_name
from security.command_segments import command_segments

_READ_ONLY_BASES: FrozenSet[str] = frozenset(
    {
        "basename",
        "df",
        "dirname",
        "du",
        "id",
        "ls",
        "ps",
        "pwd",
        "readlink",
        "realpath",
        "stat",
        "uname",
        "which",
        "whoami",
    }
)

#: These block on stdin without a file to read, unless a pipe feeds them.
_FILE_READERS: FrozenSet[str] = frozenset({"cat", "head", "tail", "wc"})
_PATTERN_READERS: FrozenSet[str] = frozenset({"egrep", "fgrep", "grep"})

#: The only flags ``tail`` may carry: any other could be a form of ``--follow``, which never returns.
_TAIL_FLAGS = re.compile(r"^(-n\d*|-\d+|--lines(=\d+)?)$")

#: ``find`` predicates that write or run something.
_FIND_FORBIDDEN: FrozenSet[str] = frozenset(
    {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprint0", "-fprintf", "-fls"}
)

#: ``git`` subcommands that only read, and the options that make them write or run a program.
#: A diff program already set in the repo's own config still runs: that takes an earlier approved write.
_READ_ONLY_GIT_SUBCOMMANDS: FrozenSet[str] = frozenset({"diff", "log", "show", "status"})
#: Git accepts unique abbreviations, so these are prefixes short enough to catch them. ``--oneline`` stays allowed.
_GIT_FORBIDDEN_PREFIXES = ("--ou", "--ex", "--te")

#: Paths with no end, or with reads that have effects.
_UNBOUNDED_PATHS = ("/dev/", "/proc/", "/sys/")

#: Reads its file list from stdin or a path, so the arguments do not say what it reads.
#: GNU tools accept any unique abbreviation of it.
_FILES_FROM_FLAG = "--files0-from"
_SHORTEST_FILES_FROM_ABBREVIATION = len("--fi")

#: What only the shell can resolve: where these end up cannot be read from the text.
_SHELL_EXPANSION_CHARS = frozenset("$*?[{~")

#: ``grep`` pattern flags: their value is not a file, so counting arguments would mistake it for one.
_RECURSIVE_FLAGS = re.compile(r"^(-[a-zA-Z]*[rR]|--(dereference-)?rec)")
_GREP_PATTERN_FLAGS = re.compile(r"^(-[a-zA-Z]*[ef]|--regexp|--file)")

#: ``grep -d recurse`` is ``-r``: the action may be abbreviated (``rec``) and sits in the next word or after ``=``.
_DIRECTORIES_FLAG = re.compile(r"^(-[a-zA-Z]*d|--di[a-z]*)$")
_DIRECTORIES_RECURSE = re.compile(r"^--di[a-z]*=rec")

#: Short flags whose next word is a number, not a file, per reader; ``cat -n 123`` reads a file named ``123``.
_NUMERIC_VALUED_FLAGS = {"head": "nc", "tail": "nc", "grep": "mABC", "egrep": "mABC", "fgrep": "mABC"}
_NUMERIC_VALUED_LONG = frozenset(
    {"--lines", "--bytes", "--max-count", "--after-context", "--before-context", "--context"}
)

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


def _arg_reads_unbounded(arg: str) -> bool:
    """Whether this argument may read stdin, an endless device, or somewhere the text cannot show."""
    flag, _, value = arg.partition("=")
    if "-" in (arg, value) or (len(flag) >= _SHORTEST_FILES_FROM_ABBREVIATION and _FILES_FROM_FLAG.startswith(flag)):
        return True
    path = value or arg
    if "$" in path or (path.startswith(("/", "~")) and _SHELL_EXPANSION_CHARS & set(path)):
        return True
    if ".." in path.split("/"):  # relative to a directory this check cannot see
        return True
    return ("/" + os.path.normpath(path).lstrip("/") + "/").startswith(_UNBOUNDED_PATHS) if path[0] == "/" else False


def _names_a_secret(arg: str) -> bool:
    """Whether any segment of this argument, or an option's value, is a secret file's name (``HEAD:id_rsa`` too)."""
    path = arg.partition("=")[2 if "=" in arg else 0]
    return any(is_secret_file_name(part) for part in re.split(r"[/:]", path) if part)


def _recurses_by_directories(args: List[str]) -> bool:
    """Whether ``-d recurse`` / ``--directories=recurse`` makes this grep read a tree it cannot name."""
    spaced = any(_DIRECTORIES_FLAG.match(flag) and value.startswith("rec") for flag, value in zip(args, args[1:]))
    return spaced or any(_DIRECTORIES_RECURSE.match(arg) for arg in args)


def _reads_files_unseen(args: List[str]) -> bool:
    """A glob or a recursive grep reads files this check never gets to name, ``.env`` among them."""
    return _recurses_by_directories(args) or any(
        _SHELL_EXPANSION_CHARS & set(arg) or _RECURSIVE_FLAGS.match(arg) for arg in args
    )


def _is_numeric_value(base: str, previous: str, arg: str) -> bool:
    """Whether *arg* is the number a valued flag takes, as in ``head -n 5``, rather than a file named for digits."""
    if not arg.isdigit():
        return False
    valued = _NUMERIC_VALUED_FLAGS.get(base, "")
    return previous in _NUMERIC_VALUED_LONG or bool(re.match(r"^-[a-zA-Z]+$", previous) and previous[-1] in valued)


def _operands(base: str, args: List[str]) -> List[str]:
    """The arguments that are not flags and not a flag's numeric value."""
    pairs = zip([""] + args, args)
    return [arg for previous, arg in pairs if not arg.startswith("-") and not _is_numeric_value(base, previous, arg)]


def _reads_bounded_input(base: str, args: List[str], piped: bool) -> bool:
    """Whether this reader has something to read that ends: a file, or a pipe into it."""
    if piped:
        return True
    if base in _PATTERN_READERS:
        return not any(_GREP_PATTERN_FLAGS.match(arg) for arg in args) and len(_operands(base, args)) >= 2
    return bool(_operands(base, args))


def _segment_is_read_only(segment: str, piped: bool) -> bool:
    words = _tokens(segment)
    if words is None:
        return False
    base, args = words[0], words[1:]
    if any(_arg_reads_unbounded(arg) or _names_a_secret(arg) for arg in args):
        return False
    if base in _READ_ONLY_BASES:
        return True
    if base in _FILE_READERS or base in _PATTERN_READERS:
        flags_ok = base != "tail" or all(_TAIL_FLAGS.match(arg) for arg in args if arg.startswith("-"))
        return flags_ok and not _reads_files_unseen(args) and _reads_bounded_input(base, args, piped)
    if base == "find":
        return not any(arg in _FIND_FORBIDDEN for arg in args)
    if base == "git":
        return (
            bool(args)
            and args[0] in _READ_ONLY_GIT_SUBCOMMANDS
            and not any(arg.startswith(_GIT_FORBIDDEN_PREFIXES) for arg in args)
        )
    return False


def _only_pipes(command: str) -> bool:
    """Whether segments are joined by ``|`` alone: after ``;`` or ``&&`` a reader's stdin is the terminal."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        operators = {word for word in lexer if set(word) <= _SHELL_OPERATOR_CHARS}
    except ValueError:
        return False
    return operators <= {"|"} and "\n" not in command


def is_read_only_command(command: str) -> bool:
    """Whether every segment of *command* only reads, and ends. Unknown means no."""
    segments = command_segments(command)
    piped = _only_pipes(command)
    return bool(segments) and all(
        _segment_is_read_only(segment, piped and index > 0) for index, segment in enumerate(segments)
    )
