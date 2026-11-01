# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#19681: a Windows script installing requirements.txt stages its relative -c include first."""

from __future__ import annotations

from pathlib import Path

import pytest
from repo_tests._paths import repo_root

_ROOT = "autobot-npu-worker/resources/windows-npu-worker"
_STAGE = "Set-InstalledConstraints"


def _pip_scripts(root: Path) -> list[Path]:
    """Every install-time PowerShell script that gives pip the installed requirements file."""
    found = []
    for path in sorted((root / _ROOT / "scripts").glob("*.ps1")):
        text = path.read_text(encoding="utf-8")
        if "pipExe" in text and '-r (Join-Path $InstallPath "requirements.txt")' in text:
            found.append(path)
    return found


def _stages_before_pip(text: str) -> bool:
    pip = text.index('-r (Join-Path $InstallPath "requirements.txt")')
    return f"{_STAGE} -InstallPath" in text[:pip] and "stage-constraints.ps1" in text[:pip]


def test_requirements_still_has_a_relative_include_so_this_guard_means_something() -> None:
    text = (repo_root() / _ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "-c ../../../constraints/shared.txt" in text


def test_both_install_scripts_are_found() -> None:
    assert {p.name for p in _pip_scripts(repo_root())} == {"install.ps1", "update.ps1"}


@pytest.mark.parametrize("path", _pip_scripts(repo_root()), ids=lambda p: p.name)
def test_each_script_stages_the_constraints_before_pip(path: Path) -> None:
    assert _stages_before_pip(path.read_text(encoding="utf-8"))


def test_contrast_a_script_that_goes_straight_to_pip_is_caught() -> None:
    assert not _stages_before_pip('& $pipExe install -r (Join-Path $InstallPath "requirements.txt")')


def test_the_stager_points_the_include_at_the_copy_it_makes() -> None:
    text = (repo_root() / _ROOT / "scripts/stage-constraints.ps1").read_text(encoding="utf-8")
    assert "'-c constraints-shared.txt'" in text and '"constraints-shared.txt"' in text
    assert "throw" in text
    assert "GetUnresolvedProviderPathFromPSPath($staged)" in text  # an update must not copy the file onto itself
