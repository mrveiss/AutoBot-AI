# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for the branch-switch guard's shell parser (#15296).

Three false denials are covered, one test per defect, each using the
reproduction from the issue verbatim so the case is traceable to the report:

1. the branch argument was read from the whole shell line, so a redirection or
   a pipeline argument became the "branch name";
2. ``-C``'s value was ignored, so a switch in an unrelated repository was
   attributed to this one;
3. the pattern matched anywhere in the string, so quoted prose was treated as
   an invocation.

Each has an inverse: the dangerous form of the same command must still be
reported. Without those, this file would pass just as happily against a parser
that reported nothing at all.

The end-to-end deny/allow decisions live in
``.claude/hooks/block-dangerous-commands_test.sh``, which
``repo_tests/shell_lib_test.py`` runs. This file tests the parsing in
isolation, where a failure names the token that was misread.
"""

from __future__ import annotations

import importlib.util
import string
import subprocess
import sys
from types import ModuleType

import pytest

from autobot_shared.paths import project_root

# Spelled in pieces so this file's own prose cannot be mistaken for an
# invocation by any guard that still matches on words rather than tokens.
SWITCH = "swi" + "tch"
CHECKOUT = "check" + "out"


def _load_parser() -> ModuleType:
    """Import the hook's parser by path — ``.claude`` is not an import package."""
    path = project_root() / ".claude" / "hooks" / "git_invocation_parse.py"
    assert path.is_file(), f"parser missing: {path}"
    spec = importlib.util.spec_from_file_location("git_invocation_parse", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


parser = _load_parser()


def invocations(command: str) -> list[dict[str, str]]:
    """Every checkout/switch the parser finds at a command position."""
    tokens = parser.tokenize(command)
    assert tokens is not None, f"expected {command!r} to tokenize"
    return parser.scan(tokens)


def branch_args(command: str) -> list[str]:
    return [found["arg"] for found in invocations(command)]


# ── Defect 1: a redirection or pipeline argument became the branch name ──────


@pytest.mark.parametrize(
    "command",
    [
        f"git {SWITCH} - 2>&1 | tail -2",  # the issue's reproduction, verbatim
        f"git {SWITCH} - >/dev/null 2>&1",
        f"git {SWITCH} - > /tmp/switch.log",
        f"git {SWITCH} - ; echo done",
    ],
)
def test_toggle_switch_keeps_its_exemption_past_a_redirect(command: str) -> None:
    """`git switch -` carries no branch argument, whatever follows it.

    The old scan took "the first token after the subcommand that does not start
    with ``-``" across the entire line, so ``2>&1`` became the branch name and
    the guard's own documented toggle exemption evaporated the moment anything
    was appended.
    """
    assert branch_args(command) == [""]


@pytest.mark.parametrize(
    "command",
    [
        f"git {SWITCH} release 2>&1 | tail -2",
        f"git {SWITCH} release >/dev/null 2>&1",
        f"git {CHECKOUT} main 2>&1 | tail -2",
    ],
)
def test_a_real_switch_is_still_found_behind_a_redirect(command: str) -> None:
    """The inverse: stopping at the redirect must not lose the real argument."""
    assert branch_args(command) == [command.split()[2]]


def test_arguments_of_a_later_command_are_not_read_as_a_branch() -> None:
    """The scan stops at the pipe, so ``tail``'s own flags are never in play."""
    assert branch_args(f"git status | tail -2 | grep {SWITCH}") == []


# ── Defect 2: -C's value was ignored, so another repository looked like ours ─


def test_dash_c_value_is_reported_so_the_caller_can_resolve_it() -> None:
    """``-C`` was tolerated as a global option but discarded, so an unrelated
    checkout — a plugin clone, a dotfiles repo — was judged as if it were this
    repository's main tree."""
    found = invocations(f"git -C /somewhere/else {SWITCH} release")
    assert [(one["dir"], one["arg"]) for one in found] == [("/somewhere/else", "release")]


def test_a_directory_change_earlier_in_the_line_is_applied() -> None:
    """``cd X && git switch Y`` acts on X, not on the caller's directory."""
    found = invocations(f"cd /somewhere/else && git {SWITCH} release")
    assert [(one["dir"], one["arg"]) for one in found] == [("/somewhere/else", "release")]


def test_an_unresolvable_directory_is_reported_as_unknown() -> None:
    """The inverse: a directory only the shell could expand is never guessed at.

    ``?`` is what keeps the caller conservative — it is treated as this tree, so
    a variable in the path cannot be used to slip a switch past the guard.
    """
    found = invocations("cd $SOMEWHERE && git " + SWITCH + " release")
    assert [one["dir"] for one in found] == [parser.UNKNOWN_DIR]


def test_git_dir_option_is_reported_in_both_spellings() -> None:
    for command in (f"git --git-dir=.git {CHECKOUT} feature", f"git --git-dir .git {CHECKOUT} feature"):
        assert [one["git_dir"] for one in invocations(command)] == [".git"]


# ── Defect 3: quoted prose matched ──────────────────────────────────────────


@pytest.mark.parametrize(
    "command",
    [
        # Filing #15296 was blocked on the first attempt by exactly this shape.
        f'gh issue create --title "guard bug" --body "git {SWITCH} - is allowed '
        f'but the same command with a redirect is not"',
        f'git commit -m "docs: explain why git {CHECKOUT} main is blocked"',
        f'git status | grep -c "git {SWITCH} main"',
        f"gh issue create --body \"$(cat <<'EOF'\n" f'reproduce with git {SWITCH} main on the main tree\nEOF\n)"\n',
    ],
)
def test_quoted_prose_is_not_an_invocation(command: str) -> None:
    """Words inside an argument are data. Nothing is being invoked."""
    assert invocations(command) == []


@pytest.mark.parametrize(
    "command",
    [
        f'echo "git {SWITCH} main is blocked" && git {SWITCH} release',
        f'echo "$(git {SWITCH} main)"',
        f"echo starting\ngit {SWITCH} release\n",
        f"sudo git {SWITCH} release",
        f"FOO=1 git {SWITCH} release",
    ],
)
def test_a_real_invocation_is_still_found_next_to_prose(command: str) -> None:
    """The inverse: quoting one mention must not hide a second, real one.

    A parser that simply stopped reporting would pass the test above and fail
    here, which is the only reason that test is worth anything.
    """
    assert invocations(command), f"expected an invocation in {command!r}"


# ── Refusing to judge, rather than judging a mis-parse ───────────────────────


@pytest.mark.parametrize("command", [f'git {SWITCH} " unbalanced', f"git {SWITCH} 'unbalanced"])
def test_an_untokenizable_command_is_refused_not_guessed(command: str) -> None:
    """``None`` is the signal the hook turns into an explicit refusal.

    Silently mis-parsing is worse than declining: the caller denies the command
    and says why, instead of inventing a branch name from a broken quote.
    """
    assert parser.tokenize(command) is None


def test_new_branch_and_restore_flags_survive_the_argument_scan() -> None:
    """The safe forms must keep their exemptions after the rewrite."""
    assert invocations(f"git -c core.foo=bar {CHECKOUT} -b issue-9999 origin/Dev_new_gui")[0]["flags"] == "new"
    assert invocations(f"git {CHECKOUT} -- file.py")[0]["flags"] == "restore"
    assert invocations(f"git {SWITCH} --create issue-9999")[0]["flags"] == "new"


# ── The wire format between the parser and the shell that reads it ──────────


def test_the_field_separator_is_not_ifs_whitespace() -> None:
    """A tab here silently deletes every leading empty field (#15296).

    ``read`` collapses a *run* of IFS whitespace into one delimiter and strips
    it at the start of the line, and tab is IFS whitespace. A plain branch
    switch emits three empty fields then the branch name, so with a tab the
    branch name arrived in the shell as the *directory* — the guard looked for a
    directory named after the branch, did not find one, concluded the command
    targeted some other repository, and allowed every switch on the main tree.
    Nothing about the parser was wrong; the wire format was.
    """
    assert parser.FIELD_SEPARATOR not in string.whitespace


def test_a_record_survives_the_shell_read_it_is_written_for() -> None:
    """End to end through a real shell: the branch name must land in field 4.

    Asserting the constant is necessary but not sufficient — this runs the
    parser as the hook runs it and reads the record as the hook reads it.
    """
    parser_path = project_root() / ".claude" / "hooks" / "git_invocation_parse.py"
    script = (
        f'python3 "$1" "git {CHECKOUT} some-branch" | '
        '{ IFS=$\'\\x1f\' read -r a b c d; printf \'%s|%s|%s|%s\' "$a" "$b" "$c" "$d"; }'
    )
    result = subprocess.run(  # nosec B603 B607  # fixed argv; nothing here comes from input
        ["bash", "-c", script, "bash", str(parser_path)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "|||some-branch", result.stdout
