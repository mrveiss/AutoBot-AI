# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The pre-push pytest budget follows the selected work (#17451).

A hub file changes one path and selects dozens of guards; sizing by changed-file
count gave it the SMALLER budget and it timed out. Drives the hook's real
``pytest_budget`` function (extracted from the script, not reimplemented).
"""

from __future__ import annotations

import re
import shutil
import subprocess

import pytest
from repo_tests._paths import repo_root

from tools.lint._comment_syntax import code_text

HOOK = repo_root() / "tools" / "git-hooks" / "pre-push"
_BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(_BASH is None, reason="bash not found -- did not look, not a pass")


def _budget(changed: int, selected: int, parallel: int) -> int:
    src = HOOK.read_text(encoding="utf-8")
    fn = re.search(r"^pytest_budget\(\) \{.*?^\}", src, re.S | re.M)
    assert fn, "pytest_budget() missing from the pre-push hook"
    consts = "\n".join(re.findall(r"^(?:MAX_BUDGET|PYTEST_COST_\w+)=\d+$", src, re.M))
    script = f"{consts}\n{fn.group(0)}\npytest_budget $((120 + {changed} * 4)) {selected} {parallel}\n"
    out = subprocess.run([_BASH, "-c", script], capture_output=True, text=True, check=True)
    return int(out.stdout)


@pytest.mark.parametrize("parallel", [0, 1])
def test_hub_file_gets_no_smaller_budget_than_wide_changeset(parallel):
    hub = _budget(changed=4, selected=28, parallel=parallel)
    wide = _budget(changed=22, selected=0, parallel=parallel)
    assert hub >= wide


def test_budget_grows_with_selection_and_is_capped():
    assert _budget(5, 46, 0) > _budget(5, 6, 0)
    assert _budget(100, 500, 0) == 600


def test_parallel_budget_is_not_larger_than_serial():
    assert _budget(15, 46, 1) <= _budget(15, 46, 0)


def test_hook_gates_parallel_on_xdist_import_and_enforces_printed_budget():
    src = HOOK.read_text(encoding="utf-8")
    assert "import xdist" in src
    assert 'timeout "$PYTEST_TIMEOUT"' in src and "budget ${PYTEST_TIMEOUT}s" in src


def _extract(name: str) -> str:
    src = HOOK.read_text(encoding="utf-8")
    fn = re.search(rf"^{name}\(\) \{{.*?^\}}", src, re.S | re.M)
    assert fn, f"{name}() missing from the pre-push hook"
    return fn.group(0)


def _xdist_args(tmp_path, xdist: bool, workers: str | None) -> tuple[str, str]:
    """Run the hook's real pytest_xdist_args against a stub interpreter."""
    stub = tmp_path / "py"
    stub.write_text(f"#!/bin/sh\nexit {0 if xdist else 1}\n", encoding="utf-8")
    stub.chmod(0o755)
    fns = "\n".join(_extract(n) for n in ("pytest_xdist_available", "pytest_workers", "pytest_xdist_args"))
    script = f'warn() {{ printf "WARN %s\\n" "$*" >&2; }}\nPYTEST_PYTHON={stub}\n{fns}\npytest_xdist_args\n'
    env = {"PATH": "/usr/bin:/bin"}
    if workers is not None:
        env["AUTOBOT_PREPUSH_PYTEST_WORKERS"] = workers
    out = subprocess.run([_BASH, "-c", script], capture_output=True, text=True, check=True, env=env)
    return out.stdout, out.stderr


@pytest.mark.parametrize(
    "xdist,workers,expected,warns",
    [
        (True, None, "-n 4 --dist loadscope", False),
        (True, "2", "-n 2 --dist loadscope", False),
        (True, "0", "", False),
        (True, "abc", "-n 4 --dist loadscope", True),
        (True, "-3", "-n 4 --dist loadscope", True),
        (False, None, "", False),
        (False, "2", "", False),
    ],
)
def test_xdist_args_follow_workers_knob_and_xdist_availability(tmp_path, xdist, workers, expected, warns):
    out, err = _xdist_args(tmp_path, xdist, workers)
    assert out == expected
    assert ("AUTOBOT_PREPUSH_PYTEST_WORKERS" in err) is warns
    assert "-n auto" not in out


def test_budget_constants_defined_once_and_cap_not_duplicated():
    src = HOOK.read_text(encoding="utf-8")
    for const in ("MAX_BUDGET=600", "PYTEST_COST_SERIAL=6", "PYTEST_COST_PARALLEL=3"):
        assert src.count(f"\n{const}\n") == 1
    code = code_text(src, name="pre-push.sh", strip_trailing=True)
    assert not re.search(r"-gt 600\b|=600\b(?!\s*$)", code.replace("MAX_BUDGET=600", ""))


def test_budget_uses_the_serial_cost_for_the_mode_chosen():
    assert _budget(0, 10, 0) - _budget(0, 0, 0) == 60
    assert _budget(0, 10, 1) - _budget(0, 0, 1) == 30
