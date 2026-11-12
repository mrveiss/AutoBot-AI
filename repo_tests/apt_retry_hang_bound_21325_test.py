# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A HUNG apt call can no longer hold a CI job for an hour (#21325).

Bounded in layers, each pinned here: the apt-retry wrapper kills an attempt that outlives its bound and
retries it; the Clean install job and install steps carry ``timeout-minutes``; the shared
``scripts/ci/apt_network_config.sh`` gives the installer's own apt calls apt's connection and lock bounds on
the CI runner; the expect script gives up before the step is killed. The installer's own apt calls on a real
host are NOT bounded (#21358). Static tests read the files; the behavioural ones run the wrapper against stubs.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest
import yaml
from repo_tests._paths import repo_root
from repo_tests.apt_retry_one_mechanism_21325_test import _APT

from tools.lint._comment_syntax import code_text

_ROOT = repo_root()
_HELPER = _ROOT / "docker/apt/apt-retry"
_ACTION = _ROOT / ".github/actions/setup-python-suite/action.yml"
_WORKFLOWS = [
    _ROOT / ".github/workflows" / name
    for name in ("clean-install.yml", "docker-smoke-test.yml", "hardened-smoke-test.yml")
]

# -- a HUNG command is bounded: wrapper attempts, job steps, apt network bounds, expect wait (#21325) --

_NETWORK_CONFIG = _ROOT / "scripts/ci/apt_network_config.sh"
_EXPECT = _ROOT / "scripts/ci/clean_install_tty.exp"
_CLEAN_INSTALL = _ROOT / ".github/workflows/clean-install.yml"
_TIMEOUT_VAR = "APT_RETRY_ATTEMPT_TIMEOUT_S"
_KILL_VAR = "APT_RETRY_KILL_AFTER_S"
# the per-attempt bound of the behavioural tests: the retry attempt must also finish inside it, so a loaded
# runner needs headroom; the stub hangs for 60 s, far beyond it
_ATTEMPT_BOUND_S = 3


def _install_steps() -> list[dict]:
    workflow = yaml.safe_load(_CLEAN_INSTALL.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["install"]["steps"]
    return [step for step in steps if str(step.get("name", "")).startswith("Step: install")]


def test_the_wrapper_runs_every_attempt_under_timeout_with_a_kill_after_and_no_foreground() -> None:
    code = code_text(_HELPER)
    assert re.search(r'timeout --kill-after="\$\{kill_after_s\}" "\$\{attempt_timeout_s\}" "\$@"', code), code
    assert (
        "--foreground" not in code
    ), "--foreground signals only the direct child; apt's helpers would outlive the kill"
    # The attempt and the refresh between attempts both go through the bounded helper, never bare.
    assert re.search(r'^\s*bounded "\$@" >"\$fifo" 2>&1$', code, re.M), "the attempt is not run through bounded"
    assert re.search(r"^\s*bounded apt-get update", code, re.M), "the refresh is not run through bounded"
    assert not re.search(r'^\s*"\$@" >', code, re.M), "an attempt runs outside the bound"


def test_the_bound_comes_from_one_variable_with_one_default() -> None:
    code = code_text(_HELPER)
    for var in (_TIMEOUT_VAR, _KILL_VAR):
        assert len(re.findall(rf"\b{var}\b", code)) == 2, f"{var}: one read with its default, one validation entry"
        assert len(re.findall(rf"\$\{{{var}:-\d+\}}", code)) == 1, f"{var}: the default is defined more than once"
    for workflow in (*_WORKFLOWS, _ACTION):
        assert _TIMEOUT_VAR not in workflow.read_text(encoding="utf-8"), f"{workflow.name} restates the bound"


def test_a_timed_out_attempt_is_logged_and_the_exhausted_message_is_distinct() -> None:
    code = code_text(_HELPER)
    assert re.search(r"case \"\$rc\" in 124 \| 137\) hung=1", code)
    assert "timed out (exit ${rc}): no result within the ${attempt_timeout_s}s bound" in code
    assert "apt command hung; ${hung_n} attempts timed out" in code


def test_both_install_steps_and_the_job_carry_a_timeout_well_under_an_hour() -> None:
    workflow = yaml.safe_load(_CLEAN_INSTALL.read_text(encoding="utf-8"))
    job = workflow["jobs"]["install"]
    steps = _install_steps()
    assert [s["name"] for s in steps] == ["Step: install (no tty)", "Step: install (tty)"]
    assert isinstance(job["timeout-minutes"], int) and job["timeout-minutes"] < 60
    for step in steps:
        assert isinstance(step["timeout-minutes"], int) and step["timeout-minutes"] < job["timeout-minutes"], step[
            "name"
        ]
    ppa = [s for s in job["steps"] if "add-apt-repository" in s.get("run", "")]
    assert len(ppa) == 1 and ppa[0]["timeout-minutes"] < job["timeout-minutes"]


def test_the_apt_network_bounds_are_written_before_the_installer_runs_from_the_one_shared_script() -> None:
    steps = yaml.safe_load(_CLEAN_INSTALL.read_text(encoding="utf-8"))["jobs"]["install"]["steps"]
    runs = [s.get("run", "") for s in steps]
    config = [i for i, run in enumerate(runs) if "scripts/ci/apt_network_config.sh" in run]
    installs = [i for i, s in enumerate(steps) if str(s.get("name", "")).startswith("Step: install")]
    assert len(config) == 1 and len(installs) == 2 and config[0] < min(installs), (config, installs)
    assert config[0] < min(i for i, run in enumerate(runs) if _APT.search(run)), "an apt call runs before the bounds"
    action = yaml.safe_load(_ACTION.read_text(encoding="utf-8"))["runs"]["steps"]
    assert any("apt_network_config.sh" in str(s.get("env", {})) for s in action), "the Python suite does not use it"
    for key in ("Acquire::Retries", "Acquire::http::Timeout", "Acquire::https::Timeout", "DPkg::Lock::Timeout"):
        assert code_text(_NETWORK_CONFIG).count(key) == 1, f"{key} must be defined once, in the shared script"
        for other in (_ACTION, _CLEAN_INSTALL):
            assert key not in code_text(other), f"{other.name} restates {key}"


def test_the_expect_wait_ends_before_the_install_step_timeout() -> None:
    text = code_text(_EXPECT)
    prompt, install = (
        int(re.search(rf"^set {name} (\d+)$", text, re.M).group(1)) for name in ("prompt_wait", "install_wait")
    )
    tty = next(s for s in _install_steps() if s["name"] == "Step: install (tty)")
    assert 2 * prompt + install < tty["timeout-minutes"] * 60, "the runner would kill the step before expect reports"
    assert "installer timed out" in text and "last output: $last_line" in text


# -- the wrapper's behaviour with a hung command ------------------------------------------------------


def _run_hung(tmp_path: Path, hang_times: int, attempts: int, args=("apt-get", "update")):
    """Run the wrapper with a stub that sleeps (in a child too) on its first `hang_times` calls."""
    if shutil.which("sh") is None or shutil.which("timeout") is None:
        pytest.skip("sh or timeout unavailable")
    calls, pids = tmp_path / "calls", tmp_path / "pids"
    calls.write_text("", encoding="utf-8")
    pids.write_text("", encoding="utf-8")
    for name, body in (
        (
            "apt-get",
            f'echo "$*" >> "{calls}"\nif [ "$(wc -l < "{calls}")" -le {hang_times} ]; then\n'
            f'  sleep 60 &\n  echo $! >> "{pids}"\n  wait\nfi\n',
        ),
        ("dpkg", "exit 0\n"),
    ):
        (tmp_path / name).write_text(f"#!/bin/sh\n{body}", encoding="utf-8")
        (tmp_path / name).chmod(0o755)
    env = {
        "PATH": f"{tmp_path}:/usr/bin:/bin",
        "APT_RETRY_ATTEMPTS": str(attempts),
        "APT_RETRY_DELAY_S": "0",
        "APT_RETRY_TEE_GRACE_S": "1",
        _TIMEOUT_VAR: str(_ATTEMPT_BOUND_S),
        _KILL_VAR: "1",
    }
    start = time.monotonic()
    done = subprocess.run(["sh", str(_HELPER), *args], env=env, capture_output=True, text=True, timeout=45, check=False)
    elapsed = time.monotonic() - start
    return done, calls.read_text(encoding="utf-8").splitlines(), pids.read_text(encoding="utf-8").split(), elapsed


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_a_hung_attempt_is_killed_with_its_children_logged_and_retried(tmp_path: Path) -> None:
    done, calls, pids, elapsed = _run_hung(tmp_path, hang_times=1, attempts=3)
    assert (done.returncode, calls) == (0, ["update", "update"]), done.stderr
    assert (
        "attempt 1/3 timed out (exit 124)" in done.stderr and f"{_ATTEMPT_BOUND_S}s bound" in done.stderr
    ), done.stderr
    assert elapsed < 20, f"the hang was not cut at the bound ({elapsed:.1f} s)"
    assert len(pids) == 1
    time.sleep(0.5)
    assert not _alive(int(pids[0])), "the hung command's child outlived the wrapper"


def test_attempts_that_all_hang_end_with_the_distinct_message_and_the_timeout_status(tmp_path: Path) -> None:
    done, calls, _, _ = _run_hung(tmp_path, hang_times=99, attempts=2)
    assert done.returncode in (124, 137) and len(calls) == 2, (done.returncode, done.stderr)
    assert "apt command hung; 2 attempts timed out" in done.stderr, done.stderr
    assert "giving up after" not in done.stderr


def test_a_hung_install_is_repaired_and_refreshed_before_the_retry(tmp_path: Path) -> None:
    done, calls, _, _ = _run_hung(tmp_path, hang_times=1, attempts=3, args=("apt-get", "install", "-y", "x"))
    assert done.returncode == 0, done.stderr
    assert calls == ["install -y x", "update", "install -y x"], calls
