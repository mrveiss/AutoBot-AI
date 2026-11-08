# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A command line is judged by every command it runs, not by its first word (#19462)."""

import asyncio

import pytest

from autobot_shared.status_enums import CommandRisk
from secure_command_executor import SecureCommandExecutor
from security.command_segments import (
    UNTERMINATED_HEREDOC,
    command_line_pattern,
    command_segments,
    split_command_line,
)
from services.command_approval_manager import SUBCOMMAND_TOOLS, CommandApprovalManager


@pytest.fixture
def executor() -> SecureCommandExecutor:
    return SecureCommandExecutor()


@pytest.mark.parametrize(
    "command, segments",
    [
        ("ls -la /tmp", ["ls -la /tmp"]),
        ("cat x | sh", ["cat x", "sh"]),
        ("cat x && python3 run.py", ["cat x", "python3 run.py"]),
        ("a || b; c & d", ["a", "b", "c", "d"]),
        ("a |& b", ["a", "b"]),
        ("ls\nsh", ["ls", "sh"]),
        ("make 2>&1", ["make 2>&1"]),
        ("make &>log", ["make &>log"]),
        ("echo hi >|out", ["echo hi >|out"]),
        ("echo 'a | b; c' && d", ["echo 'a | b; c'", "d"]),
        ('echo "x \\" && y"', ['echo "x \\" && y"']),
        ("echo a\\;b", ["echo a\\;b"]),
        ("ls;", ["ls"]),
        ("a ;; b", ["a", "b"]),
        ("", []),
        ("echo $'\\'' ; sh ; echo $'\\''", ["echo $'\\''", "sh", "echo $'\\''"]),
        ("& sh", ["sh"]),
        ("ls; (sudo rm x)", ["ls", "sudo rm x"]),
        ("{ ls; }", ["ls"]),
        ("time ! sh", ["sh"]),
        ("timeout 5 ls", ["timeout 5 ls"]),
        ("time -p sh", ["sh"]),
        ("time -p -- sh", ["sh"]),
        ("time", ["time"]),
        ('echo $"a;b" ; sh', ['echo $"a;b"', "sh"]),
        ("ls\rsh", ["ls\rsh"]),
        ("cat x\r\nsh", ["cat x", "sh"]),
        ("ls \\\nsh", ["ls \\\nsh"]),
        ("cat <<< 'a;b' && sh", ["cat <<< 'a;b'", "sh"]),
        ("cat <<<x\nsh", ["cat <<<x", "sh"]),
    ],
)
def test_the_splitter_separates_commands_outside_quotes_and_redirections(command: str, segments: list) -> None:
    assert command_segments(command) == segments


def test_an_unterminated_quote_cannot_hide_the_commands_before_it() -> None:
    assert command_segments("cat x && sh 'oops") == ["cat x", "sh 'oops"]


def test_a_quote_inside_a_comment_cannot_hide_the_next_line() -> None:
    """To the shell `#'` is a comment, so the following line runs."""
    assert command_segments("ls #'\nsh\n'") == ["ls #'", "sh", "'"]
    assert command_segments("echo a#b 'c;d'") == ["echo a#b 'c;d'"]


@pytest.mark.parametrize(
    "command, segments",
    [
        ("cat <<E\n'\nE\nsh", ["cat <<E", "sh"]),
        ("cat <<'E'\na; b'\nE\nsh", ["cat <<'E'", "sh"]),
        ('cat <<"E" | sh\nbody\nE', ['cat <<"E"', "sh"]),
        ("cat <<\\E\n'\nE\nsh", ["cat <<\\E", "sh"]),
        ("cat <<-E\n\t'\n\tE\nsh", ["cat <<-E", "sh"]),
        ("cat <<A <<B\n'\nA\n'\nB\nsh", ["cat <<A <<B", "sh"]),
        ("cat <<E\nx\nE", ["cat <<E"]),
        ("cat <<E", ["cat <<E"]),
    ],
)
def test_a_here_doc_body_is_data_and_the_commands_after_its_terminator_split(command: str, segments: list) -> None:
    assert command_segments(command) == segments


def test_an_apostrophe_in_a_here_doc_cannot_hide_the_command_after_it(executor: SecureCommandExecutor) -> None:
    """The trainmaster's reproducer: the body's `'` used to swallow the next command into a quote.

    `sudo ls` rates HIGH; swallowed, the line took the unknown-command default.
    """
    command = "cat <<E\n'\nE\nsudo ls"
    risk, reasons = executor.assess_command_risk(command)
    assert risk == executor.assess_command_risk("sudo ls")[0] == CommandRisk.HIGH, reasons


@pytest.mark.parametrize(
    "command",
    ["cat <<E\n'\nsh", "cat <<E\n", "cat <<E\n\tE\nsh", "cat <<A <<B\nA\nsh", "cat << ;\nsh"],
)
def test_a_here_doc_without_its_terminator_fails_closed(executor: SecureCommandExecutor, command: str) -> None:
    """Plain `<<` does not strip tabs, and `<<` needs a word: no terminator, so FORBIDDEN."""
    assert command_segments(command)[-1] == UNTERMINATED_HEREDOC
    assert executor.assess_command_risk(command)[0] == CommandRisk.FORBIDDEN


def test_operators_are_kept_with_the_segment_they_follow() -> None:
    assert split_command_line("a && b | c") == [("a", "&&"), ("b", "|"), ("c", "")]


@pytest.mark.parametrize(
    "command",
    ["cat x | sh", "cat x && python3 run.py", "ls || chmod 777 f", "ls\nsh", "echo a & nc -l 9"],
)
def test_a_chain_is_rated_at_its_riskiest_segment(executor: SecureCommandExecutor, command: str) -> None:
    risk, reasons = executor.assess_command_risk(command)
    worst = max((executor.assess_command_risk(s)[0] for s in command_segments(command)), key=lambda r: r.rank)
    assert risk == worst, f"{command!r} rated {risk.value}, its riskiest segment is {worst.value}: {reasons}"
    assert risk != CommandRisk.SAFE, f"{command!r} must not rate SAFE by its first word alone: {reasons}"


def test_a_redirection_does_not_turn_one_command_into_a_chain(executor: SecureCommandExecutor) -> None:
    assert executor.assess_command_risk("ls -la 2>&1")[0] == executor.assess_command_risk("ls -la")[0]


@pytest.mark.parametrize(
    "wrapped, bare",
    [("(sudo rm x)", "sudo rm x"), ("time sudo ls", "sudo ls"), ("time -p sh", "sh"), ("ls;", "ls")],
)
def test_a_wrapped_command_is_judged_as_the_command_it_wraps(
    executor: SecureCommandExecutor, wrapped: str, bare: str
) -> None:
    assert executor.assess_command_risk(wrapped)[0] == executor.assess_command_risk(bare)[0]


@pytest.mark.parametrize("command", ["cat <(sh)", "cat >(sh)", "diff <(ls a) <(ls b)"])
def test_process_substitution_is_forbidden_like_command_substitution(
    executor: SecureCommandExecutor, command: str
) -> None:
    """`cat <(sh)` runs `sh` inside one segment, so no split can expose it."""
    assert executor.assess_command_risk(command)[0] == CommandRisk.FORBIDDEN


def test_a_pattern_spanning_separators_is_still_forbidden(executor: SecureCommandExecutor) -> None:
    risk, _reasons = executor.assess_command_risk(":(){ :|:& };:")
    assert risk == CommandRisk.FORBIDDEN


def test_a_plain_command_keeps_its_historical_pattern() -> None:
    assert command_line_pattern("ls -la /home", SUBCOMMAND_TOOLS) == "ls *"
    assert command_line_pattern("git status -s", SUBCOMMAND_TOOLS) == "git status *"
    assert command_line_pattern("pwd", SUBCOMMAND_TOOLS) == "pwd"


def test_a_chain_pattern_names_every_segment_and_operator() -> None:
    assert command_line_pattern("cat a && sh", SUBCOMMAND_TOOLS) == "cat * && sh"
    assert command_line_pattern("cat a &", SUBCOMMAND_TOOLS) == "cat * &"


def test_a_newline_renders_as_the_semicolon_it_is_equivalent_to() -> None:
    assert command_line_pattern("ls\nsh", SUBCOMMAND_TOOLS) == command_line_pattern("ls; sh", SUBCOMMAND_TOOLS)
    assert command_line_pattern("ls\nsh", SUBCOMMAND_TOOLS) == "ls ; sh"
    assert command_line_pattern("npm\ninstall x", SUBCOMMAND_TOOLS) != command_line_pattern(
        "npm install x", SUBCOMMAND_TOOLS
    )


def _approved(stored: str, candidate: str, risk: str = "safe") -> bool:
    manager = CommandApprovalManager()
    asyncio.run(manager.store_auto_approve_rule("u1", stored, risk))
    return asyncio.run(manager.check_auto_approve_rules("u1", candidate, risk))


def test_a_rule_learned_from_one_command_does_not_approve_a_chain_starting_with_it() -> None:
    """The #19462 reproducer: approving `cat notes.txt` must not pre-approve `cat notes.txt | sh`."""
    assert not _approved("cat notes.txt", "cat notes.txt | sh")
    assert not _approved("cat notes.txt", "cat notes.txt && python3 run.py")


def test_a_rule_still_approves_the_same_command_shape() -> None:
    assert _approved("cat notes.txt", "cat other.txt")
    assert _approved("cat a && grep b", "cat c && grep d")
