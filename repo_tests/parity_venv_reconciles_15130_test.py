# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The CI-parity venv is judged by its contents, not by its existence (#15130).

``scripts/setup-ci-parity-env.sh`` used to stop as soon as the directory was
there and the interpreter was 3.14. Measured against the two requirement files
it installs, the venv it had left behind was 21 of 86 declared versions short
and missing 9 declared packages outright — while ``pr-preflight.sh`` went on
printing ``ok python 3.14.x from the CI-parity venv``, which reads as parity.

These exercise the real script in ``--check`` mode, which is the mode
``pr-preflight.sh`` uses precisely because it installs nothing.
"""

from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "setup-ci-parity-env.sh"
PREFLIGHT = REPO_ROOT / "scripts" / "pr-preflight.sh"

#: The script refuses any interpreter that is not the one CI runs, so a box on
#: anything else cannot exercise it at all. CI's suite is 3.14, so this skip
#: never fires there.
REQUIRED = (3, 14)
needs_ci_interpreter = pytest.mark.skipif(
    sys.version_info[:2] != REQUIRED,
    reason=f"setup-ci-parity-env.sh only builds python {REQUIRED[0]}.{REQUIRED[1]} venvs",
)


def _run(venv_path: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, CI_PARITY_VENV=str(venv_path), CI_PARITY_PYTHON=sys.executable)
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _site_packages_entries(venv_path: Path) -> set[str]:
    """Everything under the venv, so an install of any size would show up."""
    return {str(path.relative_to(venv_path)) for path in venv_path.rglob("*")}


@pytest.fixture
def empty_venv(tmp_path: Path) -> Path:
    """A structurally valid venv with none of the declared packages in it."""
    target = tmp_path / "parity"
    venv.create(target, with_pip=False)
    return target


@needs_ci_interpreter
def test_check_calls_a_package_starved_venv_stale(empty_venv: Path):
    """Existence is not the test any more — contents are."""
    result = _run(empty_venv, "--check")

    assert result.returncode == 1, result.stdout + result.stderr
    assert "STALE" in result.stdout, result.stdout


@needs_ci_interpreter
def test_check_names_what_is_wrong_rather_than_only_that_something_is(empty_venv: Path):
    """A developer has to be able to act on the report without re-deriving it."""
    result = _run(empty_venv, "--check")

    assert "NOT INSTALLED" in result.stdout, result.stdout
    assert "requirements-ci" in result.stdout, result.stdout


@needs_ci_interpreter
def test_check_installs_nothing(empty_venv: Path):
    """pr-preflight.sh calls this; it must never mutate the developer's env."""
    before = _site_packages_entries(empty_venv)

    _run(empty_venv, "--check")

    assert _site_packages_entries(empty_venv) == before


@needs_ci_interpreter
def test_check_on_an_absent_venv_refuses_instead_of_building_one(tmp_path: Path):
    """--check answers a question; it does not take a 10-minute action to do it."""
    absent = tmp_path / "never-built"

    result = _run(absent, "--check")

    assert result.returncode == 1
    assert not absent.exists()
    assert "setup-ci-parity-env.sh" in result.stderr


class TestTheCheckMatchesWhatIsInstalled:
    """The set installed and the set checked must be one list, not two.

    If they can differ, the check is measuring an environment the script never
    tried to build — which is how a number nobody can act on gets reported.
    """

    SOURCE = SCRIPT.read_text(encoding="utf-8")

    def test_the_requirement_files_are_named_exactly_once(self):
        assert self.SOURCE.count("REQUIREMENT_FILES=(") == 1

    def test_both_the_install_and_the_check_read_that_one_list(self):
        expansions = self.SOURCE.count('"${REQUIREMENT_FILES[@]}"')
        assert expansions >= 2, f"install and check must both expand the list, found {expansions}"

    def test_the_check_is_scoped_and_counts_absence(self):
        assert '--roots "${REQUIREMENT_FILES[@]}"' in self.SOURCE
        assert "--require-present" in self.SOURCE

    def test_no_requirements_file_is_installed_outside_that_list(self):
        """A stray `pip install -r other.txt` would be installed and never checked."""
        installs = [line.strip() for line in self.SOURCE.splitlines() if "pip install -r" in line]
        assert installs, "no requirement install found — this test would otherwise be vacuous"
        for line in installs:
            assert '"$file"' in line, f"installs a file the check never sees: {line}"


def test_preflight_no_longer_claims_parity_without_asking():
    """The `ok ... from the CI-parity venv` line must be conditional on the check."""
    source = PREFLIGHT.read_text(encoding="utf-8")

    assert "setup-ci-parity-env.sh --check" in source
    ok_line = 'pass "python $PY_VERSION from the CI-parity venv"'
    assert ok_line in source
    guarded = source.split("setup-ci-parity-env.sh --check", 1)[1]
    assert ok_line in guarded, "the unqualified ok is printed before the check runs"
