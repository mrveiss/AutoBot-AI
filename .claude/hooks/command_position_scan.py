#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Report the commands a shell string actually *invokes*, with their arguments.

``block-dangerous-commands.sh`` answers "does this command do X?" two different
ways. The git guards tokenize, via :mod:`git_invocation_parse`, and so can tell
a real ``git switch`` from the same words quoted inside a PR body (#15296). The
non-git guards -- the permission guard, the disk guard, the publish guards --
still ``grep`` the whole command string, which cannot (#14144).

That difference is not academic. A read-only loop that merely *searches a file
for* a guard's own trigger words is denied by that guard, because the words it
searches for sit in its own argument list::

    for pat in "<trigger A>" "<trigger B>"; do grep -c -- "$pat" "$f"; done

Nothing is invoked there. The words are data -- arguments to ``for`` -- exactly
as the quoted prose in #15296 was data. The guard read them as an invocation
because a regex over a flat string has no notion of where a command begins.
Writing about a dangerous command is not running one, which is the defect
#14144 was filed for and the half that was never fixed.

This module supplies that notion for any command, not just ``git``. It walks
the same token stream as :mod:`git_invocation_parse`, tracking the one thing a
regex cannot: whether the current token sits at a *command position* -- the
start of the string, or just after a separator (``;`` ``|`` ``&&``), a shell
keyword, or an environment assignment.

Output is one record per invocation, ``name`` and its argument words joined by
:data:`FIELD_SEPARATOR`. The caller decides what is dangerous; this module only
answers what was invoked.

**Uncertainty is reported, never resolved.** A command position holding a
variable, a substitution or ``eval`` names a command this module cannot know, so
it emits :data:`UNKNOWN_COMMAND` rather than omitting the invocation. An omitted
invocation reads as "nothing dangerous here", which is the one answer that must
never be produced by not looking -- so the caller sees ``?`` and falls back to
its unconditional check. Same reasoning as ``git_invocation_parse``'s ``?``
directory and its ``ambiguous`` subcommand flag (#15303).

Scope is inherited from the shared lexer and stated rather than assumed:
quoting is tracked, ``$( ... )`` re-enters command context, heredoc bodies are
data, newlines separate commands. Backticks, ``eval``, shell functions and
aliases are NOT interpreted -- they surface as :data:`UNKNOWN_COMMAND`.
"""
import sys
from pathlib import Path

# ``.claude`` is not an import package, so the sibling lexer is reached by
# putting this file's own directory on the path -- the same approach, and for
# the same reason, as git_invocation_parse.py.
_HOOK_DIR = str(Path(__file__).resolve().parent)
if _HOOK_DIR not in sys.path:
    sys.path.insert(0, _HOOK_DIR)

from git_shell_tokenize import is_redirect, is_separator, tokenize

#: Exit code for a command that cannot be tokenized at all -- an unbalanced
#: quote or an unterminated heredoc. Matches git_invocation_parse so the calling
#: shell can treat both parsers identically.
EXIT_UNPARSEABLE = 3

#: Field separator for the records on stdout. 0x1f rather than tab for the
#: reason recorded in git_invocation_parse: tab is IFS whitespace, so `read`
#: collapses runs of it and drops leading empty fields.
FIELD_SEPARATOR = "\x1f"

#: Stands in for a command name this module cannot determine.
UNKNOWN_COMMAND = "?"

#: Shell words after which the next word is again a command name.
_KEYWORDS = frozenset(
    {"do", "then", "else", "elif", "if", "while", "until", "{", "}", "(", ")", "!", "case", "esac", "in", "fi", "done"}
)

#: Commands that run another command, so the next word is still a command name.
_WRAPPERS = frozenset({"sudo", "env", "nohup", "time", "timeout", "command", "builtin", "exec"})

#: A command position holding one of these names a command only at runtime.
_OPAQUE = frozenset({"eval", "source", "."})

#: ``for``/``select`` are followed by a NAME and a word LIST, not by commands.
#: ``in`` is a command-position keyword because ``case X in`` genuinely re-enters
#: command context; in a ``for`` header it does not, so without this the list
#: items are reported as invocations named after their own text. That direction
#: is safe -- a spurious invocation can only make a caller stricter -- but it is
#: still wrong, and "safe when wrong" is how a scanner earns misplaced trust.
_LIST_HEADERS = frozenset({"for", "select"})

#: Substitution markers: a command position containing one is not a literal name.
_SUBSTITUTION_MARKERS = ("$", "`")


def _skip_redirection(tokens: list[str], index: int) -> int | None:
    """Index past a redirection at *index*, or ``None`` if there is none."""
    if is_redirect(tokens[index]):
        return index + 2
    following = index + 1
    if tokens[index].isdigit() and following < len(tokens) and is_redirect(tokens[following]):
        return index + 3
    return None


def _collect_args(tokens: list[str], index: int) -> tuple[list[str], int]:
    """Argument words following the command word at *index*, and where they end."""
    args: list[str] = []
    position = index + 1
    while position < len(tokens):
        token = tokens[position]
        if is_separator(token) or token in _KEYWORDS:
            break
        jumped = _skip_redirection(tokens, position)
        if jumped is not None:
            position = jumped
            continue
        args.append(token)
        position += 1
    return args, position


def _skip_word_list(tokens: list[str], index: int) -> int:
    """Index past a ``for``/``select`` header, whose words are data, not commands."""
    position = index + 1
    while position < len(tokens):
        token = tokens[position]
        # `do` opens the body and `;`/newline ends the header; either way the
        # next token is a command again, and the main walk re-arms on both.
        if token == "do" or is_separator(token):
            return position
        position += 1
    return position


def _name_of(token: str) -> str:
    """The invoked command's name, or :data:`UNKNOWN_COMMAND` when unknowable."""
    if token in _OPAQUE or any(marker in token for marker in _SUBSTITUTION_MARKERS):
        return UNKNOWN_COMMAND
    # A path-qualified name invokes the same program: /usr/bin/X is X.
    return token.rsplit("/", 1)[-1] or UNKNOWN_COMMAND


def scan(tokens: list[str]) -> list[tuple[str, list[str]]]:
    """Every command invoked at a command position, in order, with its arguments."""
    found: list[tuple[str, list[str]]] = []
    at_command, index = True, 0
    while index < len(tokens):
        token = tokens[index]
        jumped = _skip_redirection(tokens, index)
        if jumped is not None:
            index = jumped
            continue
        if is_separator(token) or token in _KEYWORDS:
            at_command = True
            index += 1
            continue
        if not at_command:
            index += 1
            continue
        # A wrapper runs what follows, and an assignment prefixes it, so in both
        # cases the NEXT word is still the command name.
        if token in _WRAPPERS or ("=" in token and not token.startswith("-")):
            index += 1
            continue
        if token in _LIST_HEADERS:
            index = _skip_word_list(tokens, index)
            continue
        at_command = False
        args, end = _collect_args(tokens, index)
        found.append((_name_of(token), args))
        index = end
    return found


def main(argv: list[str]) -> int:
    """Print one record per invocation; :data:`EXIT_UNPARSEABLE` if unparseable."""
    tokens = tokenize(argv[1] if len(argv) > 1 else "")
    if tokens is None:
        return EXIT_UNPARSEABLE
    for name, args in scan(tokens):
        # stdout is this tool's interface, not a log line: the calling hook
        # parses these records. Written explicitly so that reads as deliberate.
        sys.stdout.write(name + FIELD_SEPARATOR + " ".join(args) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
