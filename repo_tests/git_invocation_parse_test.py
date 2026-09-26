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
    assert invocations(f"git -c core.foo=bar {CHECKOUT} -b issue-9999 origin/main")[0]["flags"] == "new"
    assert invocations(f"git {CHECKOUT} -- file.py")[0]["flags"] == "restore"
    assert invocations(f"git {SWITCH} --create issue-9999")[0]["flags"] == "new"


# ── git's option grammar, rather than a list of exact spellings ─────────────


@pytest.mark.parametrize(
    ("command", "flag"),
    [
        ("git reset --hard", "HARD_RESET_FLAG"),
        ("git reset --har", "HARD_RESET_FLAG"),
        ("git reset --ha", "HARD_RESET_FLAG"),
        ("git clean --force", "FORCE_CLEAN_FLAG"),
        ("git clean --for", "FORCE_CLEAN_FLAG"),
        ("git clean --fo", "FORCE_CLEAN_FLAG"),
        ("git clean -fd", "FORCE_CLEAN_FLAG"),
    ],
)
def test_an_abbreviated_long_option_is_the_option_it_abbreviates(command: str, flag: str) -> None:
    """git runs any unambiguous prefix of a long option, so the guard must too.

    Matching only the spelled-out form left a one-keystroke way past every rule
    that reads these flags: ``--har`` really does throw the working tree away.
    """
    assert [one["flags"] for one in invocations(command)] == [getattr(parser, flag)]


@pytest.mark.parametrize("command", ["git reset --h", "git reset --soft HEAD~1", "git clean -n", "git clean --dry-run"])
def test_a_flag_git_would_not_run_destructively_reports_nothing(command: str) -> None:
    """The inverse, and the abbreviation's own limit.

    ``--h`` is ambiguous with ``--help``, so git refuses it rather than reading
    it as ``--hard``; reporting it would be a denial of a command that does not
    exist. The ordinary safe flags of the same subcommands are untouched.
    """
    assert [one["flags"] for one in invocations(command)] == [""]


@pytest.mark.parametrize(
    "command",
    [
        "git restore --source=origin/release -- .",
        "git restore --source origin/release -- .",
        "git restore --sou=origin/release -- .",
        "git restore -s origin/release -- .",
        "git restore -sorigin/release -- .",
        "git restore -Ws origin/release -- .",
    ],
)
def test_every_spelling_that_names_a_source_is_an_overwrite(command: str) -> None:
    """A named source is another commit's content, however the option is written.

    ``-Ws <ref>`` bundles ``-W`` with ``-s``, which an exact match on ``-s``
    misses; the invocation was then reported as a bounded restore from the
    index and skipped the dirty-tree check entirely.
    """
    found = invocations(command)
    assert [(one["flags"], one["arg"]) for one in found] == [(parser.OVERWRITE_FLAG, "origin/release")]


@pytest.mark.parametrize(
    "command",
    ["git restore file.py", "git restore -S file.py", "git restore --staged file.py", "git restore -p file.py"],
)
def test_a_restore_that_names_no_source_stays_bounded_by_the_index(command: str) -> None:
    """The inverse: no source named is the safe operation, and stays allowed."""
    assert [one["flags"] for one in invocations(command)] == [parser.INDEX_RESTORE_FLAG]


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


# Read exactly as ``block-dangerous-commands.sh`` reads it (its line 238): same
# separator, same variable names, same field count. Reading fewer fields than
# the hook does would let a record grow one without this test noticing -- the
# last name would silently swallow the remainder, separator and all.
_HOOK_READ = "IFS=$'\\x1f' read -r wt_dir wt_git_dir subcommand invocation_flags ref_arg"
_HOOK_ECHO = 'printf \'%s\\n\' "$wt_dir" "$ref_arg"'


def test_a_record_survives_the_shell_read_it_is_written_for() -> None:
    """End to end through a real shell: the branch name reaches the hook's REF_ARG.

    Asserting the constant is necessary but not sufficient -- this runs the
    parser as the hook runs it and reads the record as the hook reads it.

    The defect (#15296) was a leading EMPTY field being eaten, which shifts the
    branch name out of the variable the hook reads it from and into the one it
    reads a directory from. That is what is asserted: the first field is still
    empty, the branch name is in ``ref_arg``, and nothing overflowed past it.
    Which ordinal that is belongs to the hook and has already moved once --
    #15835 inserted the subcommand -- so pinning the record's every field would
    fail on a change that leaves the guarded property intact.
    """
    parser_path = project_root() / ".claude" / "hooks" / "git_invocation_parse.py"
    script = f'python3 "$1" "git {CHECKOUT} some-branch" | {{ {_HOOK_READ}; {_HOOK_ECHO}; }}'
    result = subprocess.run(  # nosec B603 B607  # fixed argv; nothing here comes from input
        ["bash", "-c", script, "bash", str(parser_path)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    fields = result.stdout.split("\n")
    assert len(fields) >= 2, result.stdout
    wt_dir, ref_arg = fields[0], fields[1]
    assert wt_dir == "", f"a leading empty field was eaten: {result.stdout!r}"
    assert ref_arg == "some-branch", f"the branch name did not reach REF_ARG: {result.stdout!r}"
    assert parser.FIELD_SEPARATOR not in ref_arg, f"the record has more fields than the hook reads: {ref_arg!r}"


# ── #14144: push destinations, keyed on the refspec rather than the text ─────
#
# The shell guard's own suite exercises these end to end. These cases pin the
# CLASSIFICATION independently, because the shell side can only observe an exit
# code: it cannot tell "the destination resolved to main" from "some other rule
# fired", and a guard that denies for the wrong reason passes an exit-code test
# while protecting nothing it claims to.

PUSH = "pu" + "sh"
PROTECTED = "ma" + "in"


def push_records(command: str) -> list[dict[str, str]]:
    return [found for found in invocations(command) if found["sub"] == PUSH]


def destinations(command: str) -> list[str]:
    """Every ref the pushes in *command* would write to."""
    found: list[str] = []
    for record in push_records(command):
        found.extend(part for part in record["arg"].split(parser.DESTINATION_SEPARATOR) if part)
    return found


@pytest.mark.parametrize(
    "command",
    [
        f"git {PUSH} origin {PROTECTED}",
        f"git {PUSH} origin refs/heads/{PROTECTED}",
        f"git {PUSH} origin heads/{PROTECTED}",
        f"git {PUSH} origin +{PROTECTED}",
        f"git {PUSH} origin HEAD:{PROTECTED}",
        f"git {PUSH} origin HEAD:refs/heads/{PROTECTED}",
        f"git {PUSH} upstream {PROTECTED}",
        f"git -C . {PUSH} origin {PROTECTED}",
        f"git {PUSH} -o ci.skip origin {PROTECTED}",
        f"git {PUSH} origin :{PROTECTED}",
        f"git {PUSH} origin feature {PROTECTED}",
    ],
)
def test_every_spelling_of_the_protected_ref_resolves_to_one_name(command: str) -> None:
    """One ref, one spelling. The retired regex matched `origin <name>` or
    `:<name>` as text, so each of these was a separate hole rather than the
    same destination written differently."""
    assert PROTECTED in destinations(command), command


@pytest.mark.parametrize(
    "command,expected",
    [
        (f"git {PUSH} origin {PROTECTED}:feature", ["feature"]),
        (f"git {PUSH} origin feature", ["feature"]),
        (f"git {PUSH} origin refs/heads/issue-9999", ["issue-9999"]),
        (f"git {PUSH} -o ci.skip origin issue-9999", ["issue-9999"]),
        (f"git {PUSH} origin feature other", ["feature", "other"]),
    ],
)
def test_a_push_that_writes_elsewhere_reports_where_it_writes(command: str, expected: list[str]) -> None:
    """`main:feature` writes to a feature ref. The retired pattern refused it,
    so the fix removes a false denial as well as the false permissions."""
    assert destinations(command) == expected


def test_repo_option_leaves_the_first_positional_as_the_repository() -> None:
    """``--repo=<repository>`` is *equivalent to* the ``<repository>`` argument,
    and "if both are specified, the command-line argument takes precedence"
    (git-push(1)). So in ``git push --repo=origin main`` the word ``main`` is
    the REPOSITORY, not a refspec: there is no destination to read.

    Pinned because the obvious reading is the wrong one -- I first wrote this
    as a case expecting ``main`` to be a destination, and checked git's own
    documentation only when the parser disagreed. The guard stays safe anyway,
    and the second assertion is why: with no refspec the push falls back to
    whatever HEAD points at, so it is flagged for HEAD resolution rather than
    waved through for having no destination.
    """
    command = f"git {PUSH} --repo=origin {PROTECTED}"

    assert destinations(command) == []
    assert parser.PUSH_CURRENT_FLAG in push_records(command)[0]["flags"].split(",")


def test_an_option_value_is_not_read_as_a_destination() -> None:
    """`-o ci.skip` consumes its value; otherwise `ci.skip` becomes the remote,
    `origin` becomes a refspec, and every judgement after it is off by one."""
    assert destinations(f"git {PUSH} -o ci.skip origin issue-9999") == ["issue-9999"]
    assert "ci.skip" not in destinations(f"git {PUSH} -o ci.skip origin issue-9999")


@pytest.mark.parametrize(
    "command",
    [
        f"git {PUSH}",
        f"git {PUSH} origin",
        f"git {PUSH} --force-with-lease",
        f"git {PUSH} -u origin",
    ],
)
def test_a_push_with_no_refspec_says_so_rather_than_naming_nothing(command: str) -> None:
    """No refspec means the destination is whatever HEAD points at, which only
    the caller can resolve. `git push origin` is the case the retired
    bare-push pattern missed: it required nothing after `push`, so naming a
    remote was enough to slip past while still writing to the current branch."""
    records = push_records(command)
    assert records, command
    assert parser.PUSH_CURRENT_FLAG in records[0]["flags"].split(","), command
    assert records[0]["arg"] == ""


@pytest.mark.parametrize(
    "command",
    [f"git {PUSH} --all origin", f"git {PUSH} --mirror origin"],
)
def test_sending_every_branch_is_flagged_without_a_ref_being_named(command: str) -> None:
    """`--all` reaches a protected ref without spelling it, so no
    destination-based rule can see it. It needs its own flag or it is invisible."""
    assert parser.PUSH_EVERY_BRANCH_FLAG in push_records(command)[0]["flags"].split(",")


def test_tags_are_not_treated_as_every_branch() -> None:
    """The contrast case for the flag above: `--tags` sends tags, and a tag is
    not a branch this guard protects. Without this, widening the option set to
    anything plausible would go unnoticed."""
    flags = push_records(f"git {PUSH} --tags origin")[0]["flags"].split(",")
    assert parser.PUSH_EVERY_BRANCH_FLAG not in flags


@pytest.mark.parametrize(
    "command,forced",
    [
        (f"git {PUSH} --force origin feature", True),
        (f"git {PUSH} -f origin feature", True),
        (f"git {PUSH} -fu origin feature", True),
        (f"git {PUSH} origin +feature", True),
        (f"git {PUSH} --force-with-lease origin feature", False),
        (f"git {PUSH} --force-with-lease=feature origin feature", False),
        (f"git {PUSH} --force-if-includes origin feature", False),
        (f"git {PUSH} -u origin feature", False),
        (f"git {PUSH} --follow-tags origin feature", False),
    ],
)
def test_force_is_recognised_in_every_spelling_but_the_leased_ones(command: str, forced: bool) -> None:
    """`--force-with-lease` is the permitted form, so it must NOT set the flag;
    `-fu` must, or bundling hides a force behind an unrelated short option."""
    flags = push_records(command)[0]["flags"].split(",")
    assert (parser.FORCE_PUSH_FLAG in flags) is forced, command


@pytest.mark.parametrize(
    "command",
    [
        f"echo 'git {PUSH} origin {PROTECTED}'",
        f"grep -rn 'git {PUSH} origin {PROTECTED}' docs/",
        f"# git {PUSH} origin {PROTECTED}",
    ],
)
def test_a_push_named_in_prose_is_not_an_invocation(command: str) -> None:
    """Writing about a push is not running one — the second defect #14144
    reported, which stopped the issue itself from being filed."""
    assert push_records(command) == []


def test_the_separator_cannot_occur_inside_a_ref_name() -> None:
    """Destinations are joined by a control character on purpose: a comma is
    legal in a branch name and would split one destination into two."""
    assert parser.DESTINATION_SEPARATOR == "\x1e"
    assert ord(parser.DESTINATION_SEPARATOR) < 0x20
