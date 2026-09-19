# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for the non-git guards' command-position scanner (#14144).

``block-dangerous-commands.sh`` had two ways of answering "does this command do
X?". The git guards tokenize (#15296). The rest matched a regex over the whole
command string, so a command that merely *named* a trigger in an argument was
denied — the defect #14144 was filed for, and the half that stayed open after
the git guards were fixed.

The scanner under test supplies the missing notion of a *command position*. Its
job is narrow and stated here so a future reader does not widen it by accident:
report what a shell string invokes, never decide what is dangerous.

Every case has an inverse. A test file that only asserted the false positives
are gone would pass against a scanner that reported nothing at all — which is
precisely the failure this whole change exists to prevent, so the "still
detected" half is not optional padding.

End-to-end deny/allow decisions live in
``.claude/hooks/block-dangerous-commands_test.sh``, which
``repo_tests/shell_lib_test.py`` runs. This file tests the scan in isolation,
where a failure names the token that was misread.
"""

from __future__ import annotations

import importlib.util
import sys
from types import ModuleType

from autobot_shared.paths import project_root

# Spelled in pieces so this file's own prose cannot be mistaken for an
# invocation by any guard that still matches on words rather than tokens —
# the same precaution git_invocation_parse_test.py takes, and the same defect.
PERM = "chm" + "od"
FMT = "mk" + "fs"
MODE = "777"


def _load_scanner() -> ModuleType:
    """Import the scanner by path — ``.claude`` is not an import package."""
    path = project_root() / ".claude" / "hooks" / "command_position_scan.py"
    assert path.is_file(), f"scanner missing: {path}"
    spec = importlib.util.spec_from_file_location("command_position_scan", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


scanner = _load_scanner()


def invoked(command: str) -> list[str]:
    """Names of the commands *command* actually invokes, in order."""
    tokens = scanner.tokenize(command)
    assert tokens is not None, f"expected {command!r} to tokenize"
    return [name for name, _args in scanner.scan(tokens)]


def args_for(command: str, name: str) -> list[str]:
    """Argument words of the first invocation of *name*."""
    tokens = scanner.tokenize(command)
    assert tokens is not None, f"expected {command!r} to tokenize"
    for found, found_args in scanner.scan(tokens):
        if found == name:
            return found_args
    raise AssertionError(f"{name} was not invoked by {command!r}")


# ---------------------------------------------------------------------------
# The reported defect: a trigger word in an argument is not an invocation.
# ---------------------------------------------------------------------------


def test_a_trigger_inside_a_for_list_is_not_an_invocation():
    """The reproduction from #14144: a read-only probe denied by its own search terms."""
    command = f'for p in "{PERM} {MODE}" x; do grep -c -- "$p" f; done'
    assert PERM not in invoked(command)
    assert "grep" in invoked(command)


def test_a_for_header_word_list_is_data_not_commands():
    """`in` re-enters command context for `case`, but a `for` header is a word list.

    The list deliberately contains ``ls`` — a real command name — because a
    scanner that re-armed on ``in`` would report it, and no assertion about the
    trigger word alone would catch that.
    """
    command = f'for p in "{PERM} {MODE}" ls; do grep -c -- "$p" f; done'
    assert invoked(command) == ["grep"]


def test_a_trigger_quoted_in_an_issue_body_is_not_an_invocation():
    command = f'gh issue create --body "{PERM} {MODE} is refused, which is correct"'
    assert invoked(command) == ["gh"]


def test_a_trigger_in_a_heredoc_body_is_not_an_invocation():
    command = f"cat > notes.md <<'EOF'\nnever run {PERM} {MODE} on a shared host\nEOF\n"
    assert PERM not in invoked(command)


# ---------------------------------------------------------------------------
# The inverse: the real invocation is still reported.
# ---------------------------------------------------------------------------


def test_a_real_invocation_is_reported_with_its_arguments():
    command = f"{PERM} {MODE} /etc/passwd"
    assert invoked(command) == [PERM]
    assert args_for(command, PERM) == [MODE, "/etc/passwd"]


def test_an_invocation_after_a_separator_is_reported():
    """`at_command` must be re-armed by `;`, `|` and `&&`, or only the first is seen."""
    for separator in (";", "|", "&&"):
        command = f"echo hello {separator} {PERM} {MODE} /tmp/x"
        assert PERM in invoked(command), f"missed the invocation after {separator!r}"


def test_a_path_qualified_name_is_the_same_program():
    assert invoked(f"/usr/bin/{PERM} {MODE} /tmp/x") == [PERM]


def test_an_env_assignment_prefix_does_not_hide_the_command():
    assert invoked(f"LC_ALL=C {PERM} {MODE} /tmp/x") == [PERM]


def test_a_wrapper_does_not_hide_the_command():
    assert invoked(f"sudo {PERM} {MODE} /tmp/x") == [PERM]


def test_a_suffixed_tool_name_is_reported_verbatim():
    """The guard matches the family with its own pattern; the scanner reports the name."""
    assert invoked(f"{FMT}.ext4 /dev/sdb1") == [f"{FMT}.ext4"]


# ---------------------------------------------------------------------------
# Uncertainty is reported, never silently resolved.
# ---------------------------------------------------------------------------


def test_a_variable_command_is_reported_as_unknown():
    """Not omitted: an omission reads as 'nothing dangerous here'."""
    assert scanner.UNKNOWN_COMMAND in invoked(f"C={PERM}; $C {MODE} /etc/passwd")


def test_eval_is_reported_as_unknown():
    assert scanner.UNKNOWN_COMMAND in invoked(f'eval "{PERM} {MODE} /etc/passwd"')


def test_a_backtick_command_is_reported_as_unknown():
    assert scanner.UNKNOWN_COMMAND in invoked("`which ls` -la")


def test_an_unparseable_command_tokenizes_to_none():
    """The caller must be able to tell 'could not read' from 'found nothing'."""
    assert scanner.tokenize('echo "unbalanced') is None


# ---------------------------------------------------------------------------
# The control: the scanner finds something, so an empty result means empty.
# ---------------------------------------------------------------------------


def test_the_scanner_reports_ordinary_invocations():
    """Without this, every assertion above passes against a scanner returning []."""
    assert invoked("ls -la | grep foo && echo done") == ["ls", "grep", "echo"]
