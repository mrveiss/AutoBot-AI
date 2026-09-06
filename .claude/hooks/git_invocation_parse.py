#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Find real ``git checkout`` / ``git switch`` invocations in a shell command.

``block-dangerous-commands.sh`` used to answer that question with a regex over
the whole command string, which produced three classes of false denial (#15296):

1. **Redirections became branch names.** The branch argument was "the first
   token after the subcommand that does not start with ``-``", scanned across
   the entire line. ``git switch - 2>&1 | tail -2`` skipped ``-`` as
   dash-prefixed and settled on ``2>&1``, so the guard's own documented toggle
   exemption held for the bare form and failed for the same command with a
   redirect appended.
2. **Arguments of *other* commands in the pipeline were in play**, for the same
   reason: the scan never stopped at ``|``, ``;``, ``&&`` or a redirection.
3. **Quoted prose matched.** The pattern was unanchored, so a PR body, commit
   message or heredoc that merely *quoted* a branch switch was denied even
   though nothing was being invoked.

The fix is to tokenize instead of to match, and to report only invocations that
sit at a *command position*. ``worktree-cap.sh`` already solved the same class
of false positive this way.

Scope of the shell parsing, stated rather than assumed:

* quoting (``'``, ``"``, backslash) is tracked, so quoted prose is one token;
* ``$( ... )`` re-enters command context, including inside double quotes,
  because a substitution really does invoke commands;
* heredoc bodies are skipped -- they are data, not commands;
* newlines separate commands, so an invocation on line 2 is still seen;
* ``cd``/``pushd`` at a command position are followed, so a directory change
  earlier in the line is applied to the invocation that follows it.

What it deliberately does **not** understand: backtick substitution, ``eval``,
shell functions and aliases -- these still evaluate the words they carry
without this tool trying to. A directory it cannot pin down is reported as
``?`` so the caller can stay conservative, and a command it cannot tokenize at
all exits :data:`EXIT_UNPARSEABLE` so the caller can refuse to judge out loud
instead of guessing silently.

**Variable expansion at the subcommand position is the one exception**
(#15303): ``SUB=switch; git $SUB main`` used to produce no invocation at all,
because the subcommand check matched a literal ``"switch"`` token and nothing
else -- a variable there was simply invisible, and no invocation meant nothing
to judge, so the command was allowed on this repository's main tree, which is
exactly what the guard exists to prevent. A command-position token this tool
cannot read as a literal (``$VAR``, ``${VAR}``, the ``$`` a ``$(...)``
substitution leaves at that position, or a backtick) is now reported instead
of skipped, with :data:`AMBIGUOUS_SUBCOMMAND_FLAG` in its ``flags`` field, so
the caller can deny it rather than treat "cannot read" as "nothing there". This
is deliberately measured against false positives, not assumed safe: a
repository-wide grep of AutoBot's own shell tooling for ``git $VAR``,
``git ${VAR}``, ``git $(...)`` or a backtick at that position found zero real
invocations of the shape, only a mocked ``git "$@"`` forwarder inside a test
file's function body -- text the guard never sees, since it inspects a typed
command line, not file contents. The trade is recorded here because the next
reader should not have to re-derive it: denying an *unresolvable* subcommand
is a wider net than denying only a *resolved-but-forbidden* one, and that is
accepted specifically because this repository's own tooling never triggers
it. This tool still does not resolve the variable's VALUE -- it cannot, without
evaluating shell -- so it denies the whole shape rather than guessing what the
value would have been (module scope note above, "Attempt limited expansion.
Do not do this").

``restore``, ``reset`` and ``clean`` joined the reported subcommands in
#15835. Every destructive git rule in ``block-dangerous-commands.sh`` used to
be a grep over the raw command text, so a heredoc *writing a file* about a
hard reset was refused three times running -- once for a memory file, once for
an issue body, once for a commit message that explained the fix. The machinery
to tell an invocation from a mention already lived here; it simply was not
applied to those rules.

The same change lets the caller separate two operations that share a syntax. A
path-scoped ``checkout``/``restore`` takes its content from the index when no
source is named (``git checkout -- <path>``: bounded by what you staged) and
from another commit when one is (``git checkout <ref> -- <path>``,
``git restore --source=<ref> -- <path>``: an overwrite that destroys
uncommitted work). Only the second gets :data:`OVERWRITE_FLAG`.

Options are read as git's own parse-options reads them rather than as exact
strings: an unambiguous long-option prefix and a bundled short option name the
same operation as their spelled-out forms, so matching only the full spelling
left a way past every rule that reads these flags (see :func:`_abbreviates`).

Output: one record per invocation on stdout --
``<directory>|<git-dir>|<subcommand>|<flags>|<arg>``, separated by 0x1f (see
:data:`FIELD_SEPARATOR`) -- where *directory* is empty
for "the caller's own working directory" and ``?`` for "could not be resolved",
*subcommand* is the literal subcommand (empty when it could not be read), and
*flags* is a comma-separated subset of ``new``/``restore``/``overwrite``/
``hard``/``force``/``ambiguous`` (the last means the other fields are
meaningless -- the subcommand itself is what could not be read). *arg* is the
overwrite source for ``overwrite``, and otherwise the first positional
argument.

The lexing -- words, quoting, ``$( )``, heredocs, the newline sentinel -- lives
in the sibling ``git_shell_tokenize`` module, which knows nothing about git.
Split there in #15835 for size, along the seam the file already had.
"""

from __future__ import annotations

import sys
from pathlib import Path

# ``.claude`` is not an import package, so the sibling lexer is reached by
# putting this file's own directory on the path. Running this file as a script
# already puts it there; loading it by path -- which the tests do, and which is
# the only way anything can import it -- does not.
_HOOK_DIR = str(Path(__file__).resolve().parent)
if _HOOK_DIR not in sys.path:
    sys.path.insert(0, _HOOK_DIR)

from git_shell_tokenize import is_redirect, is_separator, tokenize

EXIT_UNPARSEABLE = 3

#: Field separator for the records written to stdout. Deliberately NOT a tab:
#: tab is IFS *whitespace*, so `read` in the calling shell collapses a run of
#: them and drops every leading empty field. A record for a plain branch switch
#: opens with two empty fields, so with a tab the branch name arrived in the
#: shell as the FIRST variable -- the guard then looked for a directory named
#: after the branch, found none, and allowed the switch (#15296). 0x1f is not
#: IFS whitespace, so empty fields survive.
FIELD_SEPARATOR = "\x1f"

#: Shell words after which the next word is again a command name.
_KEYWORDS = frozenset(
    {
        "do",
        "then",
        "else",
        "elif",
        "if",
        "while",
        "until",
        "{",
        "}",
        "(",
        ")",
        "!",
        "case",
        "esac",
        "in",
        "fi",
        "done",
    }
)

#: Commands that run another command, so the next word is still a command name.
_WRAPPERS = frozenset({"sudo", "env", "nohup", "time", "timeout", "command", "builtin", "exec"})

#: git global options that consume the following word as their value.
_VALUE_GLOBALS = frozenset(
    {
        "-c",
        "-C",
        "--git-dir",
        "--work-tree",
        "--namespace",
        "--exec-path",
        "--super-prefix",
        "--config-env",
    }
)

#: Flags that make the subcommand *create* a branch rather than move onto one.
_NEW_BRANCH = frozenset({"-b", "-B", "-c", "--create", "--orphan"})

#: Subcommands this parser reports on.
_SUBCOMMANDS = ("checkout", "switch", "restore", "reset", "clean")

#: Subcommands that accept a pathspec, so naming a source ref makes the
#: invocation an overwrite of the working tree rather than a branch move.
_PATHSPEC_SUBCOMMANDS = frozenset({"checkout", "restore"})

#: Subcommands whose argument may move HEAD onto a shared branch.
_BRANCH_SUBCOMMANDS = frozenset({"checkout", "switch"})

#: ``git restore``'s spellings for "take the content from this commit".
_SOURCE_FLAGS = frozenset({"-s", "--source"})

#: Flag: forks a new branch instead of moving onto an existing one.
NEW_BRANCH_FLAG = "new"

#: Flag: a path-scoped restore that takes its content from the index.
INDEX_RESTORE_FLAG = "restore"

#: Flag: a path-scoped checkout/restore that takes its content from another
#: commit, overwriting whatever the working tree holds (#15835).
OVERWRITE_FLAG = "overwrite"

#: Flag: a reset that throws the working tree away.
HARD_RESET_FLAG = "hard"

#: Flag: ``git clean`` with its force flag, in any spelling.
FORCE_CLEAN_FLAG = "force"

#: A directory whose real value only the shell knows.
UNKNOWN_DIR = "?"

#: A word starting with one of these cannot be a literal git subcommand --
#: the shell has not expanded it yet at the point this tool inspects the
#: command text (#15303). ``$`` covers a bare variable (``$SUB``), a braced
#: one (``${SUB}``) and the ``$`` this tokenizer leaves behind when a
#: ``$(...)`` substitution sits at this position (see ``tokenize``'s handling
#: of ``$(``); a backtick covers the other substitution syntax, which this
#: parser has never evaluated (module docstring, "What it deliberately does
#: not understand").
_UNRESOLVED_SUBCOMMAND_MARKERS = ("$", "`")

#: The ``flags`` value for an invocation reported because its subcommand is
#: unresolvable, not because it is known to be ``checkout``/``switch``.
AMBIGUOUS_SUBCOMMAND_FLAG = "ambiguous"


def _join_dir(current: str, value: str) -> str:
    """Apply a directory change to the directory in effect so far."""
    if not value or any(marker in value for marker in ("$", "~", "*", "?")):
        return UNKNOWN_DIR
    if current == UNKNOWN_DIR:
        return UNKNOWN_DIR
    if value.startswith("/"):
        return value
    return current + "/" + value if current else value


def _apply_cd(tokens: list[str], index: int, current: str) -> str:
    """Directory in effect after the ``cd``/``pushd`` starting at *index*."""
    cursor = index + 1
    while cursor < len(tokens) and tokens[cursor].startswith("-") and tokens[cursor] != "-":
        cursor += 1
    if cursor >= len(tokens) or is_separator(tokens[cursor]) or is_redirect(tokens[cursor]):
        return UNKNOWN_DIR  # bare `cd` goes to $HOME, which only the shell knows
    return _join_dir(current, tokens[cursor])


def _skip_redirection(tokens: list[str], index: int) -> int | None:
    """Index past a redirection at *index*, or ``None`` if there is none."""
    if is_redirect(tokens[index]):
        return index + 2
    following = index + 1
    if tokens[index].isdigit() and following < len(tokens) and is_redirect(tokens[following]):
        return index + 3
    return None


def _first_positional(args: list[str]) -> str:
    """The first argument that is not an option -- a branch, ref or path."""
    return next((arg for arg in args if not arg.startswith("-")), "")


def _abbreviates(token: str, option: str) -> bool:
    """True when *token* is a long option git itself would read as *option*.

    git's parse-options accepts any unambiguous prefix of a long option, so
    ``--har`` really does select ``--hard`` and ``--for`` really does select
    ``--force``. Matching only the full spelling left a one-keystroke way past
    every rule that reads these flags. ``--`` plus a single letter is excluded
    because git rejects it itself, as ambiguous with ``--help``.
    """
    return len(token) > 3 and option.startswith(token)


def _is_clean_force(arg: str) -> bool:
    """True for ``git clean``'s force flag, bundled (``-fd``) or spelled out."""
    if _abbreviates(arg, "--force"):
        return True
    return arg.startswith("-") and not arg.startswith("--") and "f" in arg


def _bundled_source(token: str, args: list[str], position: int) -> str | None:
    """The ref a single-dash bundle names as ``git restore``'s source, if any.

    Short options bundle behind one dash, and ``-s`` is the only one of this
    subcommand's that takes a value, so what follows the ``s`` inside the bundle
    is that value -- or the next word, when the bundle ends there. ``-Ws <ref>``
    names a source that an exact match on ``-s`` misses, which reported the
    invocation as a bounded index restore and skipped the dirty-tree check.
    """
    if not token.startswith("-") or token.startswith("--") or "s" not in token:
        return None
    rest = token[token.index("s") + 1 :]
    if rest:
        return rest
    return args[position + 1] if position + 1 < len(args) else ""


def _restore_source(args: list[str]) -> str:
    """The ref ``git restore`` was told to take content from, if any.

    ``git restore <path>`` restores from the index and is bounded; every
    spelling that names a source -- ``--source=<ref>``, ``--source <ref>``,
    ``-s <ref>``, ``-s<ref>``, an unambiguous abbreviation of the long form, and
    a bundle carrying ``s`` -- overwrites the tree from another commit.
    """
    for position, token in enumerate(args):
        if token in _SOURCE_FLAGS or _abbreviates(token, "--source"):
            return args[position + 1] if position + 1 < len(args) else ""
        if "=" in token and _abbreviates(token.split("=", 1)[0], "--source"):
            return token.split("=", 1)[1]
        bundled = _bundled_source(token, args, position)
        if bundled is not None:
            return bundled
    return ""


def _checkout_source(args: list[str]) -> str:
    """The tree-ish a path-scoped ``git checkout`` overwrites the tree from.

    ``git checkout -- <path>`` names no tree-ish and takes what you staged.
    ``git checkout <ref> -- <path>`` and its ``--``-less form
    ``git checkout <ref> <path>`` take another commit's content, which is a
    different operation wearing the same syntax (#15835). Two positional
    arguments can only be tree-ish plus pathspec: the one-argument form is the
    branch move this parser has always reported.
    """
    if "--" in args:
        return _first_positional(args[: args.index("--")])
    positional = [arg for arg in args if not arg.startswith("-")]
    return positional[0] if len(positional) > 1 else ""


def _collect_args(tokens: list[str], index: int) -> tuple[list[str], int]:
    """This invocation's own arguments, and the index after the last of them."""
    args: list[str] = []
    cursor = index + 1
    while cursor < len(tokens):
        token = tokens[cursor]
        if is_separator(token) or token in _KEYWORDS:
            break
        jumped = _skip_redirection(tokens, cursor)
        if jumped is not None:
            cursor = jumped
            continue
        args.append(token)
        cursor += 1
    return args, cursor


def _classify(subcommand: str, args: list[str]) -> tuple[list[str], str]:
    """``(flags, arg)`` for *subcommand* -- what it does, and to which ref."""
    if subcommand == "reset":
        wipes = any(_abbreviates(arg, "--hard") for arg in args)
        return ([HARD_RESET_FLAG] if wipes else []), _first_positional(args)
    if subcommand == "clean":
        return ([FORCE_CLEAN_FLAG] if any(_is_clean_force(arg) for arg in args) else []), ""
    if subcommand in _BRANCH_SUBCOMMANDS and any(arg in _NEW_BRANCH for arg in args):
        return [NEW_BRANCH_FLAG], _first_positional(args)
    if subcommand in _PATHSPEC_SUBCOMMANDS:
        source = _restore_source(args) if subcommand == "restore" else _checkout_source(args)
        if source:
            return [OVERWRITE_FLAG], source
        if subcommand == "restore" or args[:1] == ["--"]:
            return [INDEX_RESTORE_FLAG], _first_positional(args)
    return [], _first_positional(args)


def _parse_subcommand(tokens: list[str], index: int, directory: str, git_dir: str) -> tuple[dict[str, str], int]:
    """Describe the subcommand at *index*; return it and the index after it."""
    subcommand = tokens[index]
    args, cursor = _collect_args(tokens, index)
    flags, arg = _classify(subcommand, args)
    record = {
        "dir": directory,
        "git_dir": git_dir,
        "sub": subcommand,
        "flags": ",".join(flags),
        "arg": arg,
    }
    return record, cursor


def _ambiguous_record(directory: str, git_dir: str) -> dict[str, str]:
    """A report for a subcommand position this tool cannot read literally.

    Reported rather than silently skipped (#15303): ``SUB=switch; git $SUB
    main`` used to return no invocation at all, and the caller reads "no
    invocation" as "nothing to judge, allow". Denying an invocation whose
    shape it cannot rule out is the same choice already made for a directory
    only the shell could resolve -- see ``UNKNOWN_DIR`` above.
    """
    return {"dir": directory, "git_dir": git_dir, "sub": "", "flags": AMBIGUOUS_SUBCOMMAND_FLAG, "arg": ""}


def _skip_global_flags(tokens: list[str], index: int, directory: str) -> tuple[int, str, str]:
    """``(cursor, directory, git_dir)`` just past ``git``'s global options."""
    cursor = index + 1
    git_dir = ""
    while cursor < len(tokens) and tokens[cursor].startswith("-"):
        token = tokens[cursor]
        if token in _VALUE_GLOBALS:
            value = tokens[cursor + 1] if cursor + 1 < len(tokens) else ""
            if token == "-C":
                directory = _join_dir(directory, value)
            elif token == "--git-dir":
                git_dir = value
            cursor += 2
            continue
        if token.startswith("--git-dir="):
            git_dir = token.split("=", 1)[1]
        cursor += 1
    return cursor, directory, git_dir


def _parse_git(tokens: list[str], index: int, directory: str) -> tuple[dict[str, str] | None, int]:
    """Parse the ``git`` invocation at *index*.

    Reports the two subcommands this tool understands, PLUS a subcommand
    position it cannot read at all -- everything else (``git status``, an
    absent subcommand, a global-flag-only invocation) stays unreported, same
    as before #15303.
    """
    cursor, directory, git_dir = _skip_global_flags(tokens, index, directory)
    if cursor >= len(tokens):
        return None, cursor
    subcommand = tokens[cursor]
    if subcommand in _SUBCOMMANDS:
        return _parse_subcommand(tokens, cursor, directory, git_dir)
    if subcommand.startswith(_UNRESOLVED_SUBCOMMAND_MARKERS):
        return _ambiguous_record(directory, git_dir), cursor + 1
    return None, cursor


def scan(tokens: list[str]) -> list[dict[str, str]]:
    """Every reported subcommand invoked at a command position, in order."""
    found: list[dict[str, str]] = []
    directory, at_command, index = "", True, 0
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
        if token in _WRAPPERS or ("=" in token and not token.startswith("-")):
            index += 1
            continue
        at_command = False
        if token in ("cd", "pushd"):
            directory = _apply_cd(tokens, index, directory)
        elif token == "git":
            invocation, index = _parse_git(tokens, index, directory)
            if invocation is not None:
                found.append(invocation)
            continue
        index += 1
    return found


def main(argv: list[str]) -> int:
    """Print one record per invocation; :data:`EXIT_UNPARSEABLE` if unparseable."""
    tokens = tokenize(argv[1] if len(argv) > 1 else "")
    if tokens is None:
        return EXIT_UNPARSEABLE
    for invocation in scan(tokens):
        fields = (
            invocation["dir"],
            invocation["git_dir"],
            invocation["sub"],
            invocation["flags"],
            invocation["arg"],
        )
        # stdout is this tool's interface, not a log line: the calling hook
        # parses these records. Written explicitly so that reads as deliberate.
        sys.stdout.write(FIELD_SEPARATOR.join(fields) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
