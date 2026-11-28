#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pre-push budgets follow their work, not the changeset (#18578).

vue-tsc type-checks the whole project, so a changeset-scaled budget was shortest
for the smallest PRs: 99 s for 3 files against a measured 111 s idle, which blocked
every small frontend push. A kit change's `vitest related` runs every test reaching
the kit, so its budget comes from the project's test files, not the changed files.
Runs the hook's own function, as the other pre-push tests do.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from repo_tests._paths import repo_root

from autobot_shared.isolated_git import git, isolated_git_env, make_repo

_HOOK = repo_root() / "tools" / "git-hooks" / "pre-push"
_GIT_ROOT_LIB = repo_root() / "scripts" / "lib" / "git-root.sh"


def _source() -> str:
    return _HOOK.read_text(encoding="utf-8")


def _constant(name: str) -> int:
    match = re.search(rf"^{name}=(\d+)$", _source(), re.MULTILINE)
    assert match, f"{name} is no longer a plain constant in the hook"
    return int(match.group(1))


def _kit_budget(project: Path) -> int:
    func = re.search(r"^kit_related_budget\(\) \{\n(?:.*\n)*?\}$", _source(), re.MULTILINE)
    assert func, "the hook no longer defines kit_related_budget"
    prelude = "\n".join(f"{n}={_constant(n)}" for n in ("TEST_TIMEOUT", "MAX_BUDGET", "VITEST_COST_PER_FILE"))
    script = f'. "$1"\n{prelude}\n{func.group(0)}\nkit_related_budget "$2"'
    # Paths go in as positional args, never into the script text: a space in the tmp
    # path would split, and the budget would silently fall back to TEST_TIMEOUT.
    argv = ["bash", "-c", script, "kit_related_budget", str(_GIT_ROOT_LIB), str(project)]
    done = subprocess.run(argv, capture_output=True, text=True, check=True, env=isolated_git_env())
    return int(done.stdout)


def test_a_project_path_with_a_space_is_counted_not_split(tmp_path: Path) -> None:
    """CodeRabbit on #18589: an unquoted path would split and fall back to TEST_TIMEOUT."""
    assert _kit_budget(_project_with_tests(tmp_path / "has space", 150)) == 150 * _constant("VITEST_COST_PER_FILE")


def _project_with_tests(tmp_path: Path, count: int) -> Path:
    make_repo(tmp_path)
    for i in range(count):
        (tmp_path / f"t{i}.test.ts").write_text("", encoding="utf-8")
    git(tmp_path, "add", ".")
    return tmp_path


def _type_check_timeout(value: str | None) -> tuple[int, str]:
    """Run the hook's own type_check_timeout() with the knob set to *value*."""
    func = re.search(r"^type_check_timeout\(\) \{\n(?:.*\n)*?\}$", _source(), re.MULTILINE)
    assert func, "the hook no longer defines type_check_timeout"
    script = (
        f"MAX_BUDGET={_constant('MAX_BUDGET')}\nwarn() {{ echo \"WARN $*\" >&2; }}\n{func.group(0)}\ntype_check_timeout"
    )
    env = isolated_git_env()
    env.pop("AUTOBOT_PREPUSH_TYPE_CHECK_TIMEOUT", None)
    if value is not None:
        env["AUTOBOT_PREPUSH_TYPE_CHECK_TIMEOUT"] = value
    done = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True, env=env)
    return int(done.stdout), done.stderr


def test_vue_tsc_budget_is_project_sized_not_changeset_scaled() -> None:
    """The old `90 + 3 x changed` gave 99 s for 3 files against 111 s measured idle."""
    assert not re.search(r"TYPE_CHECK_TIMEOUT=\$\(\(.*changed_count", _source())
    assert "TYPE_CHECK_TIMEOUT=$(type_check_timeout)" in _source()
    default, warning = _type_check_timeout(None)
    assert default == 450 and not warning


def test_the_type_check_knob_overrides_validates_and_caps() -> None:
    assert _type_check_timeout("500")[0] == 500
    value, warning = _type_check_timeout("soon")
    assert value == 450 and "AUTOBOT_PREPUSH_TYPE_CHECK_TIMEOUT" in warning
    assert _type_check_timeout("0")[0] == 450
    # `timeout 00` is NO timeout to GNU timeout: every all-zero form must fall back too.
    for zero in ("00", "000"):
        value, warning = _type_check_timeout(zero)
        assert value == 450 and "AUTOBOT_PREPUSH_TYPE_CHECK_TIMEOUT" in warning, zero
    assert _type_check_timeout("0450")[0] == 450, "a leading zero is decimal, not octal"
    assert _type_check_timeout("5000")[0] == _constant("MAX_BUDGET")


def test_kit_related_budget_grows_with_the_projects_tests(tmp_path: Path) -> None:
    per_file = _constant("VITEST_COST_PER_FILE")
    small = _kit_budget(_project_with_tests(tmp_path / "small", 10))
    large = _kit_budget(_project_with_tests(tmp_path / "large", 150))
    assert small == _constant("TEST_TIMEOUT"), "a tiny project still gets the base budget"
    assert large == 150 * per_file
    assert _kit_budget(_project_with_tests(tmp_path / "huge", 2000)) == _constant("MAX_BUDGET")


def test_the_count_is_right_even_when_git_exports_GIT_DIR(tmp_path: Path) -> None:
    """Inside a hook git exports GIT_DIR, which outranks `-C`; the count must not follow it."""
    project = _project_with_tests(tmp_path / "p", 150)
    func = re.search(r"^kit_related_budget\(\) \{\n(?:.*\n)*?\}$", _source(), re.MULTILINE).group(0)
    prelude = "\n".join(f"{n}={_constant(n)}" for n in ("TEST_TIMEOUT", "MAX_BUDGET", "VITEST_COST_PER_FILE"))
    env = isolated_git_env()
    env["GIT_DIR"] = str(repo_root() / ".git")
    script = f'. "$1"\n{prelude}\n{func}\nkit_related_budget "$2"'
    argv = ["bash", "-c", script, "kit_related_budget", str(_GIT_ROOT_LIB), str(project)]
    done = subprocess.run(argv, capture_output=True, text=True, check=True, env=env)
    assert int(done.stdout) == 150 * _constant("VITEST_COST_PER_FILE")


def test_the_kit_step_uses_its_own_budget() -> None:
    src = _source()
    assert 'timeout "$kit_timeout" npx vitest related' in src
    assert 'did_not_run "vitest related (${project})" "${kit_timeout}"' in src


def test_pytest_workers_reads_a_leading_zero_as_decimal() -> None:
    """`08`/`09` are not valid octal; the workers knob is read base 10 (#18589 review)."""
    func = re.search(r"^pytest_workers\(\) \{\n(?:.*\n)*?\}$", _source(), re.MULTILINE)
    assert func, "the hook no longer defines pytest_workers"
    for raw, expected in (("08", "8"), ("09", "9"), ("0", "0"), ("4", "4")):
        env = isolated_git_env()
        env["AUTOBOT_PREPUSH_PYTEST_WORKERS"] = raw
        script = f'warn() {{ echo "WARN $*" >&2; }}\n{func.group(0)}\npytest_workers'
        done = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True, env=env)
        assert done.stdout == expected and not done.stderr, raw
