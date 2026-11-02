# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The commands an unattended caller may run (#19807).

The risk classifier rates many commands SAFE for a person at a terminal -- an
interpreter, ``env``, ``find``, ``git``, a file reader -- because a person reads
the command before it runs. A workflow step has no such reader, so a
``CommandRunPolicy`` replaces "SAFE from the classifier" with this list. The
classifier itself is unchanged; the terminal still uses it.

Reason for each omission, kept here so it is not re-added without a decision:

* interpreters (``python``, ``node``, ``sh``, ``perl`` ...) execute arbitrary code;
* ``env``, ``printenv`` print the process environment;
* ``curl``, ``wget`` send data out and fetch code in;
* ``find``, ``xargs``, ``git``, ``npm``, ``pip``, ``tar`` run other programs
  (``-exec``, hooks, scripts, ``--to-command``);
* file readers (``cat``, ``head``, ``tail``, ``grep``, ``sort``, ``wc``, ``stat``,
  ``file``) read any file the backend can, secrets included (#19974);
* ``tee`` and every redirection write files.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

#: Commands that cannot execute other code, read file contents or write files. Each is also SAFE
#: in the classifier (a test pins that), which still runs after this list.
UNATTENDED_ALLOWED_COMMANDS: frozenset[str] = frozenset(
    {"echo", "pwd", "whoami", "hostname", "uname", "uptime", "date", "id", "ls"}
)

#: Characters that chain, substitute, redirect, quote-escape or continue a command. Refused anywhere in the
#: text, quoted or not: a quote span is not a safe place, and an unattended run has no shell to need them
#: (``run_bounded`` executes the parsed words directly).
_SHELL_META = re.compile(r"[;&|<>$`\\\n\r(){}]")


@dataclass(frozen=True)
class ArgSpec:
    """The only arguments an allowlisted command accepts when nobody is watching.

    GNU tools accept any unambiguous prefix of a long option (``date --fil`` is
    ``--file``), so banning option names cannot work; everything not named here is
    refused. ``short`` lists permitted single-letter flags (clusters allowed); no long
    option is ever permitted. ``positional`` judges each non-flag word.
    """

    short: str = ""
    positional: Callable[[str], bool] = lambda word: False


def _any_word(word: str) -> bool:
    return True


def _date_format(word: str) -> bool:
    """``date +FORMAT`` only: a bare positional such as ``0101120026`` sets the clock."""
    return word.startswith("+")


def _user_name(word: str) -> bool:
    """``id NAME``: a plain account name, never a path."""
    return re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", word) is not None


def _local_path(word: str) -> bool:
    """``ls PATH``: relative to the working directory, no parent, no home, no option look-alike."""
    return not word.startswith(("/", "~", "-")) and ".." not in Path(word).parts


#: Per command, what it may be given. Flags that name a file or change state are simply absent.
_ARG_SPECS: dict[str, ArgSpec] = {
    "echo": ArgSpec(short="neE", positional=_any_word),
    "pwd": ArgSpec(short="LP"),
    "whoami": ArgSpec(),
    "hostname": ArgSpec(short="sfdi"),  # no positional: ``hostname NAME`` renames the host
    "uname": ArgSpec(short="asnrvmpio"),
    "uptime": ArgSpec(short="ps"),
    "id": ArgSpec(short="ugGnr", positional=_user_name),
    "date": ArgSpec(short="uIR", positional=_date_format),
    "ls": ArgSpec(short="lAahtrS1dF", positional=_local_path),
}


def _arguments_refused(command: str, args: list[str]) -> bool:
    """Whether any of *args* falls outside what *command*'s spec permits."""
    spec = _ARG_SPECS[command]
    for arg in args:
        if arg.startswith("--") or arg == "-":
            return True  # no long option is ever permitted; "--" and "-" are not needed
        if arg.startswith("-"):
            if not set(arg[1:]) <= set(spec.short):
                return True
        elif not spec.positional(arg):
            return True
    return False


def unattended_refusal(command: str) -> str | None:
    """Why an unattended caller may not run *command*, or None. The reason never quotes the command."""
    if _SHELL_META.search(command):
        return "it chains, substitutes, redirects, escapes or continues over lines"
    try:
        words = shlex.split(command)
    except ValueError:
        return "it cannot be parsed as one command"
    if not words:
        return "it is empty"
    if words[0] not in UNATTENDED_ALLOWED_COMMANDS:
        return "its command is not on the unattended allowlist"
    if _arguments_refused(words[0], words[1:]):
        return "it carries an argument outside what the command may be given unattended"
    return None
