# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for the pre-commit could-not-run gate (#14181)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MODULE = Path(__file__).with_name("check_precommit_hooks_executed.py")


@pytest.fixture
def gate():
    spec = importlib.util.spec_from_file_location("check_precommit_hooks_executed", _MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Hook display names are assembled, not written verbatim: several repo lint
# rules are line-based scans of raw source text, so a fixture quoting a real
# hook's name trips the rule that hook enforces. This file did exactly that on
# its first push -- `no-utcnow-isoformat` flagged a fixture line containing
# the tz-naive timestamp call it bans, which was sample *output*, not code. Same
# defect #14202 hit one PR earlier; see test_this_file_does_not_trip_a_sibling_lint.
_UTCNOW_HOOK_NAME = "Block datetime." + "utcnow()." + "isoformat() regressions"

_FINDINGS_ONLY = f"""\
black....................................................................Failed
- hook id: black
- files were modified by this hook
{_UTCNOW_HOOK_NAME}.....................................Failed
trim trailing whitespace.................................................Failed
Require encoding= on text-mode open()....................................Passed
"""

_CANNOT_RUN = f"""\
{_UTCNOW_HOOK_NAME}.....................................Failed
Executable `tools/lint/check_no_utcnow_isoformat.py` is not executable
"""


def test_findings_alone_do_not_fail(gate, capsys):
    """20 hooks report findings on a real run. Gating on those is the judgement
    call the original step was right to avoid — only inability to run is fatal."""
    assert gate.unrunnable_hooks(_FINDINGS_ONLY) == []


def test_a_hook_that_could_not_run_is_detected(gate):
    assert gate.unrunnable_hooks(_CANNOT_RUN) == ["tools/lint/check_no_utcnow_isoformat.py"]


def test_the_not_found_wording_is_also_detected(gate):
    """pre-commit says `not found` when the entry is a bare name off $PATH."""
    out = "myhook.................Failed\nExecutable `tools/lint/gone.py` not found\n"
    assert gate.unrunnable_hooks(out) == ["tools/lint/gone.py"]


def test_a_known_dormant_hook_is_tolerated(gate, tmp_path):
    dormant = next(iter(gate._KNOWN_DORMANT))
    log = tmp_path / "out.txt"
    log.write_text(f"x...Failed\nExecutable `{dormant}` is not executable\n", encoding="utf-8")

    assert gate.main([str(log)]) == 0


def test_an_unknown_hook_that_cannot_run_fails(gate, tmp_path):
    """The whole point: a hook outside the tracked backlog silently not running
    is the fail-open #14181 exists to remove."""
    log = tmp_path / "out.txt"
    log.write_text("x...Failed\nExecutable `tools/lint/brand_new_hook.py` is not executable\n", encoding="utf-8")

    assert gate.main([str(log)]) == 1


def test_findings_only_output_passes_end_to_end(gate, tmp_path):
    log = tmp_path / "out.txt"
    log.write_text(_FINDINGS_ONLY, encoding="utf-8")

    assert gate.main([str(log)]) == 0


def test_the_tolerated_set_is_imported_not_duplicated(gate):
    """A second copy of the dormant list is a second thing to go stale (#14202)."""
    import importlib.util as _ilu

    spec = _ilu.spec_from_file_location("check_hook_exec_bits", _MODULE.with_name("check_hook_exec_bits.py"))
    exec_bits = _ilu.module_from_spec(spec)
    spec.loader.exec_module(exec_bits)

    assert gate._KNOWN_DORMANT is exec_bits._KNOWN_DORMANT or gate._KNOWN_DORMANT == exec_bits._KNOWN_DORMANT
    source = _MODULE.read_text(encoding="utf-8")
    assert "from check_hook_exec_bits import _KNOWN_DORMANT" in source, "the list must be imported, not re-listed"


def test_this_file_does_not_trip_a_sibling_lint(gate) -> None:
    """A fixture quoting a banned pattern violates the rule that bans it.

    #14202 shipped this defect and had it caught in review; this file then
    reproduced it one PR later, with a fixture line containing
    the tz-naive timestamp call that rule bans, as sample *output*. Line-based
    checkers cannot tell a fixture from code, and the natural way to write
    realistic sample output is the way that breaks.

    Asserted rather than remembered.
    """
    import subprocess  # nosec B404  # fixed argv, no shell

    checker = Path(__file__).resolve().parents[1] / "tools/lint/check_no_utcnow_isoformat.py"
    if not checker.is_file():  # pragma: no cover - checker moved
        pytest.skip("check_no_utcnow_isoformat.py not present")

    result = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["python3", str(checker), str(Path(__file__).resolve())],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "this test file trips no-utcnow-isoformat — assemble banned patterns "
        f"from fragments instead of writing them verbatim:\n{result.stdout}{result.stderr}"
    )


def test_empty_output_is_fatal_not_clean(gate, tmp_path):
    """No output means no run, and a pass over it is the fail-open this gate removes.

    Found while reviewing this PR: with an empty capture the could-not-run scan
    finds nothing and the gate reported "every other hook executed", exit 0.
    Reachable whenever pre-commit dies before printing — a bootstrap failure, an
    unreadable config, an OOM — and the preceding step swallows that too.
    """
    log = tmp_path / "out.txt"
    log.write_text("", encoding="utf-8")

    assert gate.main([str(log)]) == 1


def test_a_crash_AFTER_some_hooks_ran_is_still_fatal(gate, tmp_path):
    """The case the run-happened check alone cannot catch.

    pre-commit can print results for several hooks and then die. The output
    then contains hook result lines, so the "did anything run" guard is
    satisfied, while the run was truncated and the remaining hooks never
    executed. Written this way deliberately: an earlier version of this test
    passed a crash message with no hook lines at all, which the run-happened
    guard caught on its own — so the fatal check was untested and could be
    removed with every test still green.
    """
    log = tmp_path / "out.txt"
    log.write_text(
        "black....................................................Passed\n"
        "An unexpected error has occurred: KeyError('x')\n",
        encoding="utf-8",
    )

    assert gate.main([str(log)]) == 1


def test_an_invalid_config_after_output_is_fatal(gate, tmp_path):
    log = tmp_path / "out.txt"
    log.write_text(
        "black....................................................Passed\n"
        "InvalidConfigError: .pre-commit-config.yaml is not valid\n",
        encoding="utf-8",
    )

    assert gate.main([str(log)]) == 1


def test_output_with_only_passes_is_accepted(gate, tmp_path):
    """The run-happened check must not demand a failure to be satisfied."""
    log = tmp_path / "out.txt"
    log.write_text("black....................................................Passed\n", encoding="utf-8")

    assert gate.main([str(log)]) == 0
