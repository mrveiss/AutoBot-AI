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
import sys
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


# ---------------------------------------------------------------------------
# One definition of the FAIL exit code (#15074)
# ---------------------------------------------------------------------------
#
# `CHECK_FAILED_RC` was written out three times: once in the shell, once inside
# each of the two quoted python heredocs. The heredocs are `<<'PY'`, so the
# shell deliberately cannot interpolate into them and each copy was typed by
# hand. Nothing kept them in agreement, and disagreement is not a broken script
# — it is a silently wrong verdict: a probe exiting a code `classify_probe` no
# longer recognises is reported as ERROR ("this check could not run") when it
# means FAIL ("access control is broken"), and `print_summary` then declares the
# whole suite unable to vouch for access control. That is #14869's FAIL/ERROR
# confusion, back via a one-character edit.
#
# The shell now exports the value and the probes read it. These tests hold that
# shape from both ends: statically (no copy may reappear) and by running the
# real probe programs and watching them exit whatever the environment said.

_ASSIGNMENT = re.compile(r"^[ \t]*(export[ \t]+)?CHECK_FAILED_RC[ \t]*=[ \t]*(?P<rhs>.+?)[ \t]*$", re.MULTILINE)
_ENV_READ = 'int(os.environ["CHECK_FAILED_RC"])'
_PROBE = re.compile(r"<<'PY'\n(?P<program>.*?)\nPY\n", re.DOTALL)


def _assignments() -> list[str]:
    """Every place the script assigns the FAIL code, in any language."""
    return [m.group("rhs") for m in _ASSIGNMENT.finditer(SCRIPT.read_text(encoding="utf-8"))]


def _probe_programs() -> list[str]:
    """The python programs the script feeds to `python3 -c`."""
    return [m.group("program") for m in _PROBE.finditer(SCRIPT.read_text(encoding="utf-8"))]


def test_the_fail_code_has_exactly_one_definition():
    """One literal, exported; every other assignment derives from it.

    The enumeration is asserted non-empty first: a regex that matched nothing —
    because the constant was renamed, or the probes restructured — would
    otherwise sail through every assertion below having checked nothing.
    """
    assignments = _assignments()
    assert len(assignments) >= 3, (
        "expected the shell definition and one derivation per python probe; " f"found {len(assignments)}: {assignments}"
    )

    literals = [rhs for rhs in assignments if rhs.isdigit()]
    derived = [rhs for rhs in assignments if rhs == _ENV_READ]

    assert literals == ["20"], f"the FAIL code must be defined once, as a literal, in the shell; found {literals}"
    assert len(derived) == len(assignments) - 1, (
        "every assignment other than the definition must read the exported value, " f"not restate it; got {assignments}"
    )


def test_the_definition_is_exported_so_the_probes_can_read_it():
    """A definition the subprocesses cannot see would make every probe exit 1."""
    source = SCRIPT.read_text(encoding="utf-8")
    assert re.search(r"^export[ \t]+CHECK_FAILED_RC=20$", source, re.MULTILINE), (
        "CHECK_FAILED_RC is defined but not exported: `python3 -c` runs in a child "
        "process, so the probes would raise KeyError and every real failure would "
        "be reported as a check that could not run"
    )


def test_every_probe_that_reports_a_failure_reads_the_exported_code():
    """No probe may reintroduce a literal — the whole class, not one instance."""
    programs = _probe_programs()
    assert len(programs) >= 2, f"no probe programs found in the script — the extraction broke: {len(programs)}"

    users = [program for program in programs if "CHECK_FAILED_RC" in program]
    assert len(users) >= 2, "expected both the audit-logging and enforcement probes to signal FAIL by exit code"

    for program in users:
        assert _ENV_READ in program, f"a probe restates the FAIL code instead of reading it:\n{program}"
        assert not re.search(
            r"CHECK_FAILED_RC[ \t]*=[ \t]*\d", program
        ), f"a probe assigns the FAIL code a literal — the fourth copy this guard exists to catch:\n{program}"


def _stub_services(tmp_path: Path) -> Path:
    """A `services` package satisfying both probes, with each check reporting broken."""
    package = tmp_path / "stub-modules" / "services"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "audit_logger.py").write_text(
        "class _Logger:\n"
        "    async def log(self, **kwargs):\n"
        "        return None\n"
        "    async def flush(self):\n"
        "        return None\n"
        "    async def get_statistics(self):\n"
        "        return {'redis_available': False}\n"
        "\n"
        "async def get_audit_logger():\n"
        "    return _Logger()\n",
        encoding="utf-8",
    )
    (package / "feature_flags.py").write_text(
        "from enum import Enum\n"
        "\n"
        "class EnforcementMode(Enum):\n"
        "    DISABLED = 'disabled'\n"
        "    LOG_ONLY = 'log_only'\n"
        "    ENFORCED = 'enforced'\n"
        "\n"
        "class _Flags:\n"
        "    async def set_enforcement_mode(self, mode):\n"
        "        return None\n"
        "    async def get_enforcement_mode(self):\n"
        "        return EnforcementMode.DISABLED\n"
        "\n"
        "async def get_feature_flags():\n"
        "    return _Flags()\n",
        encoding="utf-8",
    )
    return package.parent


@pytest.mark.parametrize("fail_code", ["20", "37"])
def test_a_probe_exits_the_code_the_shell_exported(tmp_path, fail_code):
    """The linkage itself, executed: the probes agree with the shell BY CONSTRUCTION.

    `37` is the whole point. A probe carrying its own literal exits 20 whatever
    the shell says, so the shell would read 20 as "the check failed" while the
    probe that actually ran meant something else — or, after a drift in the
    other direction, read a real FAIL as a probe that never ran. Parametrising
    the exported value is the only assertion here that a third hand-written copy
    could not satisfy.
    """
    programs = [p for p in _probe_programs() if "CHECK_FAILED_RC" in p]
    assert len(programs) >= 2, "the probe programs could not be extracted — this test would prove nothing"

    env = dict(os.environ)
    env["CHECK_FAILED_RC"] = fail_code
    env["PYTHONPATH"] = str(_stub_services(tmp_path))

    for program in programs:
        result = subprocess.run(  # nosec B603  # fixed interpreter, no shell
            [sys.executable, "-c", program],
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
            check=False,
        )
        assert result.returncode == int(fail_code), (
            f"probe exited {result.returncode}, but the shell told it {fail_code} means FAIL:\n"
            f"{result.stderr}\n{program}"
        )
