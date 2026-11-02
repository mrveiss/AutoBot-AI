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

#: Commands that cannot execute other code, read file contents or write files. Each is also SAFE
#: in the classifier (a test pins that), which still runs after this list.
UNATTENDED_ALLOWED_COMMANDS: frozenset[str] = frozenset(
    {"echo", "pwd", "whoami", "hostname", "uname", "uptime", "date", "id", "ls"}
)

#: Characters that chain, substitute, redirect, quote-escape or continue a command. Refused anywhere in the
#: text, quoted or not: a quote span is not a safe place, and an unattended run has no shell to need them
#: (``run_bounded`` executes the parsed words directly).
_SHELL_META = re.compile(r"[;&|<>$`\\\n\r(){}]")

#: Arguments that make a command run another program, whichever command carries them.
_EXEC_STYLE_ARGS: frozenset[str] = frozenset(
    {"-exec", "-execdir", "-ok", "-okdir", "--exec", "--eval", "--to-command", "--checkpoint-action"}
)
#: Per-command arguments that read a named file or change state, matched by prefix so ``-f/etc/x`` and
#: ``--file=/etc/x`` are caught as well as ``-f /etc/x``. ``date``: -f/--file read dates from a file,
#: -r/--reference read a file's mtime, -s/--set change the clock; a short cluster such as ``-uf`` counts.
#: ``hostname``: -F/--file read a name from a file. The other allowlisted commands take no file-reading flag.
_COMMAND_SPECIFIC_ARGS: dict[str, re.Pattern[str]] = {
    "date": re.compile(r"^(-[A-Za-z]*[fsr]|--(file|reference|set))"),
    "hostname": re.compile(r"^(-[A-Za-z]*F|--file)"),
}


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
    specific = _COMMAND_SPECIFIC_ARGS.get(words[0])
    if _EXEC_STYLE_ARGS.intersection(words[1:]) or (specific and any(specific.match(w) for w in words[1:])):
        return "it carries an argument that executes code or reads a file"
    return None
