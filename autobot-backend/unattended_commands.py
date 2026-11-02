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

#: Characters that chain, substitute, redirect or continue a command. Refused anywhere
#: outside single quotes, where the shell treats them literally.
_SHELL_META = re.compile(r"[;&|<>$`\\\n\r(){}]")
_SINGLE_QUOTED = re.compile(r"'[^']*'")

#: Arguments that make a command run another program, whichever command carries them.
_EXEC_STYLE_ARGS: frozenset[str] = frozenset(
    {"-exec", "-execdir", "-ok", "-okdir", "--exec", "--eval", "--to-command", "--checkpoint-action"}
)
#: Per-command arguments that read a file or change state (``date -f FILE``, ``date -s``).
_COMMAND_SPECIFIC_ARGS: dict[str, frozenset[str]] = {"date": frozenset({"-f", "--file", "-s", "--set"})}


def unattended_refusal(command: str) -> str | None:
    """Why an unattended caller may not run *command*, or None. The reason never quotes the command."""
    if _SHELL_META.search(_SINGLE_QUOTED.sub("", command)):
        return "it chains, substitutes, redirects or continues over lines"
    try:
        words = shlex.split(command)
    except ValueError:
        return "it cannot be parsed as one command"
    if not words:
        return "it is empty"
    if words[0] not in UNATTENDED_ALLOWED_COMMANDS:
        return "its command is not on the unattended allowlist"
    banned = _EXEC_STYLE_ARGS | _COMMAND_SPECIFIC_ARGS.get(words[0], frozenset())
    if banned.intersection(words[1:]):
        return "it carries an argument that executes code or reads a file"
    return None
