# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Editable-install packaging guard (#14035).

`autobot_shared/pyproject.toml` lives INSIDE the package directory it
describes (`autobot_shared/pyproject.toml`, not `<repo>/pyproject.toml`).
A naive `[tool.setuptools.packages.find]` with `where = ["."]` treats the
*contents* of `autobot_shared/` (`auth/`, `browser/`, `components/`, ...)
as top-level installable packages, and never registers `autobot_shared`
itself. `pip show autobot_shared` still reports the package installed —
only the editable finder's mapping is wrong.

Running pytest from the repo root cannot catch this: the repo root sits
on `sys.path[0]`, so `import autobot_shared` "works" via a plain
filesystem lookup regardless of what the editable install actually
registered. These tests spawn a subprocess from a cwd that is NOT the
repo root, using the *installed* interpreter (`sys.executable`), so only
the real package-discovery mapping is exercised — cwd cannot mask a
regression here.

The main sharded `python-suite` CI job (ci.yml) never runs `pip install
-e ./autobot_shared` — it relies entirely on `pytest.ini`'s `pythonpath =
. autobot-backend autobot_shared ...` to make imports resolve, the same
cwd-adjacent mechanism this bug hides behind. This module is collected
by that job too (it globs the whole `autobot_shared/` tree), so these
tests skip themselves there rather than failing on an environment that
never claims to have installed the package. `startup-import-smoke.yml`
DOES run `pip install -e autobot_shared` and is where this guard is
meant to bite.
"""

from __future__ import annotations

import importlib.metadata
import shutil
import subprocess
import sys
import tempfile

import pytest


def _autobot_shared_is_pip_installed() -> bool:
    """True only where this interpreter has real distribution metadata.

    A bare checkout on `pythonpath`/`PYTHONPATH` has no dist-info at all —
    `import autobot_shared` can still "work" there via cwd, which is
    exactly the masking this guard exists to bypass.
    """
    try:
        importlib.metadata.distribution("autobot_shared")
        return True
    except importlib.metadata.PackageNotFoundError:
        return False


pytestmark = pytest.mark.skipif(
    not _autobot_shared_is_pip_installed(),
    reason=(
        "autobot_shared has no pip distribution metadata in this interpreter "
        "(a bare checkout on pythonpath/PYTHONPATH, not a real `pip install "
        "-e`) — the editable-install mapping this guard checks does not apply."
    ),
)


def _run_in_other_cwd(code: str) -> subprocess.CompletedProcess[str]:
    """Run `code` with `sys.executable` from a cwd that is not the repo root."""
    tmp_dir = tempfile.mkdtemp(prefix="autobot_shared_editable_guard_")
    try:
        return subprocess.run(
            [sys.executable, "-c", code],
            cwd=tmp_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_autobot_shared_importable_outside_repo_root():
    """The editable install must register `autobot_shared`, not rely on cwd."""
    result = _run_in_other_cwd("import autobot_shared")
    assert result.returncode == 0, (
        "`import autobot_shared` failed from a non-repo-root cwd — the "
        "editable install does not register the top-level package (#14035).\n"
        f"stderr:\n{result.stderr}"
    )


@pytest.mark.parametrize("polluted_name", ["auth", "browser", "components", "code_graph"])
def test_submodules_not_registered_as_top_level_names(polluted_name):
    """Submodules of autobot_shared must not shadow generic top-level names."""
    result = _run_in_other_cwd(f"import {polluted_name}")
    assert result.returncode != 0, (
        f"`import {polluted_name}` unexpectedly succeeded from a "
        "non-repo-root cwd — the editable install is registering "
        "autobot_shared's submodules as top-level package names again (#14035).\n"
        f"stdout:\n{result.stdout}"
    )


@pytest.mark.parametrize(
    "repo_root_sibling",
    ["scripts", "tools", "docs", "main", "conftest", "tasks", "security", "data"],
)
def test_repo_root_not_leaked_onto_sys_path(repo_root_sibling):
    """A `package-dir = {"" = ...}` root mapping is a DIFFERENT bug, not a fix.

    A single ""-keyed `package-dir` entry makes setuptools' editable-install
    `_select_strategy()` take the `_StaticPth` branch, which writes a raw
    `.pth` line adding the ENTIRE resolved source directory to `sys.path` —
    it never consults `include`/`exclude`. Pointed at the repo root, that
    puts every sibling of `autobot_shared/` (`scripts/`, `tools/`,
    `main.py`, `conftest.py`, ...) on `sys.path` as a bare top-level name —
    the same bug class #14035 exists to close, at a far larger blast
    radius than the original 16 submodules.
    """
    result = _run_in_other_cwd(f"import {repo_root_sibling}")
    assert result.returncode != 0, (
        f"`import {repo_root_sibling}` unexpectedly succeeded from a "
        "non-repo-root cwd — the editable install is leaking the repo "
        "root itself onto sys.path (#14035).\n"
        f"stdout:\n{result.stdout}"
    )
