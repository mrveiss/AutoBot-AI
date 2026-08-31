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

Output: one tab-separated record per invocation on stdout --
``<directory>|<git-dir>|<flags>|<branch-arg>``, separated by 0x1f (see
:data:`FIELD_SEPARATOR`) -- where *directory* is empty
for "the caller's own working directory" and ``?`` for "could not be resolved",
and *flags* is a comma-separated subset of ``new``/``restore``/``ambiguous``
(the last means *branch-arg* is meaningless -- the subcommand itself, not the
branch, is what could not be read).
"""

from __future__ import annotations

import shlex
import sys

# Marks an unquoted newline, which separates commands exactly like ``;`` does.
# shlex treats newlines as plain whitespace once ``whitespace_split`` is on, so
# without this an invocation on the second line would look like an argument of
# the command on the first.
SENTINEL = "\x1eNL\x1e"

EXIT_UNPARSEABLE = 3

#: Field separator for the records written to stdout. Deliberately NOT a tab:
#: tab is IFS *whitespace*, so `read` in the calling shell collapses a run of
#: them and drops every leading empty field. A record for a plain branch switch
#: is three empty fields then the branch name, which arrived in the shell as the
#: branch name in the FIRST variable -- the guard then looked for a directory
#: named after the branch, found none, and allowed the switch (#15296). 0x1f is
#: not IFS whitespace, so empty fields survive.
FIELD_SEPARATOR = "\x1f"

#: Tokens made only of these characters end one command and start another.
_SEPARATOR_CHARS = set(";&|")

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
_SUBCOMMANDS = ("checkout", "switch")

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


def _is_redirect(token: str) -> bool:
    """True for a redirection operator token (``>``, ``>>``, ``2>&1``'s ``>&``)."""
    return bool(token) and (token[0] in "<>" or token in ("&>", "&>>"))


def _is_separator(token: str) -> bool:
    """True for ``;``, ``&&``, ``||``, ``|``, ``&`` and the newline sentinel."""
    return token == SENTINEL or (bool(token) and set(token) <= _SEPARATOR_CHARS)


def _read_word(src: str, index: int) -> tuple[str, int]:
    """Read one (possibly quoted) shell word starting at *index*."""
    letters: list[str] = []
    quote: str | None = None
    while index < len(src):
        char = src[index]
        if quote is not None:
            if char == quote:
                quote = None
            else:
                letters.append(char)
            index += 1
            continue
        if char in "'\"":
            quote = char
            index += 1
            continue
        if char == "\\":
            index += 1
            if index < len(src):
                letters.append(src[index])
                index += 1
            continue
        if char.isspace() or char in ";|&()<>":
            break
        letters.append(char)
        index += 1
    return "".join(letters), index


def _terminator_end(src: str, start: int, delimiter: str) -> int:
    """Index just past the line that closes a heredoc opened with *delimiter*."""
    cursor = start
    while cursor <= len(src):
        newline = src.find("\n", cursor)
        line = src[cursor:] if newline == -1 else src[cursor:newline]
        if line.strip() == delimiter:
            return len(src) if newline == -1 else newline + 1
        if newline == -1:
            return len(src)
        cursor = newline + 1
    return len(src)


class _Normalizer:
    """Rewrite a shell command so shlex can tokenize it with commands intact."""

    def __init__(self, src: str) -> None:
        self.src = src
        self.out: list[str] = []
        self.pos = 0
        self.quote: str | None = None
        self.subst: list[str | None] = []

    def run(self) -> str | None:
        """Normalized command, or ``None`` when the source cannot be parsed."""
        while self.pos < len(self.src):
            if self.quote == "'":
                self._single()
            elif self.quote == '"':
                self._double()
            else:
                self._plain()
        if self.quote is not None or self.subst:
            return None
        return "".join(self.out)

    def _emit(self, text: str, consumed: int) -> None:
        self.out.append(text)
        self.pos += consumed

    def _single(self) -> None:
        char = self.src[self.pos]
        if char == "'":
            self.quote = None
        self._emit(char, 1)

    def _double(self) -> None:
        src, pos = self.src, self.pos
        if src[pos] == "\\":
            self._emit(src[pos : pos + 2], 2)
            return
        if src.startswith("$(", pos):
            # Close the string, let the substitution run at a command position,
            # and reopen the string when it ends. A substitution inside double
            # quotes really does invoke commands; without this rewrite the whole
            # string would be one opaque token and the invocation invisible.
            self.subst.append('"')
            self.quote = None
            self._emit('" ' + SENTINEL + " $(", 2)
            return
        if src[pos] == '"':
            self.quote = None
        self._emit(src[pos], 1)

    def _plain(self) -> None:
        src, pos = self.src, self.pos
        char = src[pos]
        if char == "\\":
            self._emit(src[pos : pos + 2], 2)
        elif char == "\n":
            self._emit(" " + SENTINEL + " ", 1)
        elif char in "'\"":
            self.quote = char
            self._emit(char, 1)
        elif src.startswith("$(", pos):
            self.subst.append(None)
            self._emit("$(", 2)
        elif char == ")" and self.subst:
            self._close_subst()
        elif src.startswith("<<", pos) and not src.startswith("<<<", pos) and self._skip_heredoc():
            return
        else:
            self._emit(char, 1)

    def _close_subst(self) -> None:
        if self.subst.pop() == '"':
            self.quote = '"'
            self._emit(") " + SENTINEL + ' "', 1)
        else:
            self._emit(")", 1)

    def _skip_heredoc(self) -> bool:
        """Drop the heredoc body opened here; keep the rest of the line."""
        src = self.src
        cursor = self.pos + 2
        if cursor < len(src) and src[cursor] == "-":
            cursor += 1
        while cursor < len(src) and src[cursor] in " \t":
            cursor += 1
        delimiter, cursor = _read_word(src, cursor)
        newline = src.find("\n", cursor)
        if not delimiter or newline == -1:
            return False
        body_start = newline + 1
        self.src = src[:body_start] + src[_terminator_end(src, body_start, delimiter) :]
        self.out.append(" ")
        self.pos = cursor
        return True


def tokenize(command: str) -> list[str] | None:
    """Shell tokens for *command*, or ``None`` when it cannot be tokenized."""
    normalized = _Normalizer(command).run()
    if normalized is None:
        return None
    try:
        lexer = shlex.shlex(normalized, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError:
        return None


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
    if cursor >= len(tokens) or _is_separator(tokens[cursor]) or _is_redirect(tokens[cursor]):
        return UNKNOWN_DIR  # bare `cd` goes to $HOME, which only the shell knows
    return _join_dir(current, tokens[cursor])


def _skip_redirection(tokens: list[str], index: int) -> int | None:
    """Index past a redirection at *index*, or ``None`` if there is none."""
    if _is_redirect(tokens[index]):
        return index + 2
    following = index + 1
    if tokens[index].isdigit() and following < len(tokens) and _is_redirect(tokens[following]):
        return index + 3
    return None


def _parse_subcommand(tokens: list[str], index: int, directory: str, git_dir: str) -> tuple[dict[str, str], int]:
    """Describe the subcommand at *index*; return it and the index after it."""
    args: list[str] = []
    cursor = index + 1
    while cursor < len(tokens):
        token = tokens[cursor]
        if _is_separator(token) or token in _KEYWORDS:
            break
        jumped = _skip_redirection(tokens, cursor)
        if jumped is not None:
            cursor = jumped
            continue
        args.append(token)
        cursor += 1
    flags: list[str] = []
    if tokens[index] == "checkout" and args[:1] == ["--"]:
        flags.append("restore")
    if any(arg in _NEW_BRANCH for arg in args):
        flags.append("new")
    branch = next((arg for arg in args if not arg.startswith("-")), "")
    record = {"dir": directory, "git_dir": git_dir, "flags": ",".join(flags), "arg": branch}
    return record, cursor


def _ambiguous_record(directory: str, git_dir: str) -> dict[str, str]:
    """A report for a subcommand position this tool cannot read literally.

    Reported rather than silently skipped (#15303): ``SUB=switch; git $SUB
    main`` used to return no invocation at all, and the caller reads "no
    invocation" as "nothing to judge, allow". Denying an invocation whose
    shape it cannot rule out is the same choice already made for a directory
    only the shell could resolve -- see ``UNKNOWN_DIR`` above.
    """
    return {"dir": directory, "git_dir": git_dir, "flags": AMBIGUOUS_SUBCOMMAND_FLAG, "arg": ""}


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
        if _is_separator(token) or token in _KEYWORDS:
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
            invocation["flags"],
            invocation["arg"],
        )
        # stdout is this tool's interface, not a log line: the calling hook
        # parses these records. Written explicitly so that reads as deliberate.
        sys.stdout.write(FIELD_SEPARATOR.join(fields) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
