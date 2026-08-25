# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The access-control validation suite must report, not abort (#14869).

`validate_access_control.sh` ran under a bare `set -e` with two defects that
both turned "something failed" into "the run finished":

* ``((TESTS_PASSED++))`` is a POST-increment. With the counter at 0 the
  expression evaluates to 0, which ``((...))`` reports as exit status 1, which
  ``set -e`` treats as a fatal error. The suite therefore died on its FIRST
  verdict -- one check printed, eight never ran, no summary, exit 1. On screen
  that is indistinguishable from "the suite ran and something failed";
* ``test_audit_logging`` and ``test_security_enforcement`` invoked ``python3 -c``
  as bare statements, so a non-zero exit aborted the run before the
  ``if [ $? -eq 0 ]`` beneath it could report FAIL.

These tests drive the real script with stubbed ``python3`` / ``redis-cli`` on
PATH, so no probe touches Redis, the backend, or the enforcement mode. The stub
exit code is the whole experiment: 0 = healthy, 20 = the probe ran and the thing
it checks is broken, anything else = the probe could not run at all.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "autobot-infrastructure" / "shared" / "scripts" / "deployment" / "validate_access_control.sh"

# --security-only exercises the six checks that need no network: the three basic
# ones and the three security ones. It skips the performance and infrastructure
# sections, which is why curl never has to be stubbed.
_MODE = "--security-only"

_STUB = """#!/bin/sh
if [ -n "${STUB_STDOUT}" ]; then printf '%s\\n' "${STUB_STDOUT}"; fi
if [ -n "${STUB_STDERR}" ]; then printf '%s\\n' "${STUB_STDERR}" >&2; fi
exit "${STUB_RC:-0}"
"""

# Every check label the suite prints. A run that reports fewer than all of them
# stopped early, which is the defect.
_CHECK_LABELS = (
    "Feature flags system exists",
    "Get current enforcement mode",
    "Redis connectivity",
    "Session ownership coverage",
    "Audit logging system",
    "Unauthorized access enforcement",
)

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _stub_bin(tmp_path: Path) -> Path:
    """A PATH front-end whose python3/redis-cli obey STUB_RC and STUB_STDOUT."""
    bin_dir = tmp_path / "stub-bin"
    bin_dir.mkdir()
    for name in ("python3", "redis-cli"):
        stub = bin_dir / name
        stub.write_text(_STUB, encoding="utf-8")
        stub.chmod(0o755)
    return bin_dir


def _run_suite(tmp_path: Path, *, rc: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PATH"] = f"{_stub_bin(tmp_path)}{os.pathsep}{env['PATH']}"
    env["STUB_RC"] = str(rc)
    env["STUB_STDOUT"] = stdout
    env["STUB_STDERR"] = stderr
    result = subprocess.run(  # nosec B603 B607  # fixed path, no shell
        ["bash", str(SCRIPT), _MODE],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
        check=False,
    )
    result.stdout = _ANSI.sub("", result.stdout)
    result.stderr = _ANSI.sub("", result.stderr)
    return result


def _summary_count(output: str, label: str) -> int:
    match = re.search(rf"^\s*{label}:\s+(\d+)", output, re.MULTILINE)
    assert match, f"the summary has no '{label}' line:\n{output}"
    return int(match.group(1))


def test_a_healthy_run_reports_all_six_checks_and_a_summary(tmp_path):
    """The counter regression, head on.

    Against the old script this stops after the first PASS: one check reported,
    five never run, no summary, exit 1 -- a healthy system reported as a failing
    one, which is why nobody read the exit code as meaningful.
    """
    result = _run_suite(tmp_path, rc=0, stdout="4|4|100.0")

    for label in _CHECK_LABELS:
        assert label in result.stdout, f"the run never reached '{label}' — it aborted partway"
    assert "Validation Summary" in result.stdout, "the run produced no summary at all"
    assert _summary_count(result.stdout, "Passed") == len(_CHECK_LABELS)
    assert result.returncode == 0, f"a clean run exited {result.returncode}:\n{result.stdout}"


def test_a_crashing_probe_reports_error_and_the_run_continues(tmp_path):
    """A probe that could not run says so, and does not take the suite with it."""
    result = _run_suite(tmp_path, rc=1, stderr="ModuleNotFoundError: no such module")

    for label in _CHECK_LABELS:
        assert label in result.stdout, f"a crashing probe aborted the run before '{label}'"
    # The two probes the issue names. Both exit 1 here, which is ALSO the code a
    # genuine assertion failure used to use, so a classifier that collapses the
    # two would report FAIL on this line.
    assert "Audit logging system ... ERROR" in result.stdout
    assert "Unauthorized access enforcement ... ERROR" in result.stdout
    assert _summary_count(result.stdout, "Errored") > 0, "a crashed probe was not counted as un-run"
    assert _summary_count(result.stdout, "Failed") == 2, (
        "a crashed probe was counted as a measured failure — only the two checks whose "
        "own semantics make a non-zero exit a real FAIL should be there"
    )
    assert "ModuleNotFoundError" in result.stdout, "the probe's own error was swallowed"
    assert result.returncode != 0


def test_a_failing_probe_reports_fail_not_error(tmp_path):
    """'The check ran and it is broken' must not read as 'the check never ran'.

    Both used to reach the shell as exit status 1 — an uncaught Python exception
    exits 1 too — so the two verdicts were the same output. The probes now exit
    20 for a real failure and the classifier keeps them apart.
    """
    result = _run_suite(tmp_path, rc=20)

    assert "Audit logging system ... FAIL" in result.stdout
    assert "Unauthorized access enforcement ... FAIL" in result.stdout
    assert (
        "Audit logging not working (probe exited" not in result.stdout
    ), "a genuine FAIL was reported as an un-run check"
    assert _summary_count(result.stdout, "Failed") > 0
    assert result.returncode != 0


def test_un_run_checks_dominate_the_verdict(tmp_path):
    """An un-run check is the loudest thing in the summary, not a footnote.

    The operator has to be told the difference between "access control is
    broken" and "this suite could not tell you anything about access control".
    The second is the reading that hid the original defect, so it takes
    precedence in the closing verdict.
    """
    result = _run_suite(tmp_path, rc=127, stderr="python3: not found")

    errored = _summary_count(result.stdout, "Errored")
    assert errored > 0, "a missing interpreter was not counted as an un-run check"
    assert f"{errored} check(s) could not run" in result.stdout
    assert "All tests passed" not in result.stdout, "a suite that measured nothing reported success"
    assert result.returncode != 0


def test_an_unknown_option_prints_usage_instead_of_dying_on_a_missing_function(tmp_path):
    """`log_error` was called here and had never been defined: exit 127, no usage."""
    env = dict(os.environ)
    env["PATH"] = f"{_stub_bin(tmp_path)}{os.pathsep}{env['PATH']}"
    result = subprocess.run(  # nosec B603 B607  # fixed path, no shell
        ["bash", str(SCRIPT), "--not-an-option"],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )

    assert result.returncode == 1, f"expected a usage error, got exit {result.returncode}"
    assert "command not found" not in result.stderr
    assert "Usage:" in _ANSI.sub("", result.stdout)


@pytest.mark.parametrize(
    "shape,why",
    [
        (r"\(\(\s*TESTS_\w+\+\+\s*\)\)", "post-increment returns 1 on the first bump and `set -e` aborts the run"),
        (r"^\s*python3 -c", "a bare `python3 -c` statement under `set -e` aborts before its verdict is read"),
    ],
)
def test_the_script_carries_neither_abort_shape(shape, why):
    """Static floor: the two shapes that made a failure look like a finished run."""
    source = SCRIPT.read_text(encoding="utf-8")
    offenders = [
        f"{n}: {line.strip()}"
        for n, line in enumerate(source.splitlines(), 1)
        if re.search(shape, line) and not line.lstrip().startswith("#")
    ]
    assert not offenders, f"{why}:\n" + "\n".join(offenders)
