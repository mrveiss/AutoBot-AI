# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for check_baseline_no_growth.sh (#14371).

The baseline suppresses findings, so anything that can append to it can silence
the detector. `--audit-baseline` only ever checked that no entry had been
STRANDED; nothing checked that none had been ADDED, and that was a one-line
bypass of the whole gate: hardcode a value, append its key in the same change,
and the detector's correct finding is suppressed under a green check.

Every test below MUTATES a real two-commit repository and asserts the verdict.
Both directions are covered on purpose: a guard that blocks growth but also
blocks shrinkage would make the baseline unmaintainable, and removals are how a
fixed violation leaves.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GUARD_REL = "pipeline-scripts/check_baseline_no_growth.sh"
BASELINE_REL = "pipeline-scripts/hardcoded_values_baseline.txt"
LIBS = ("scripts/lib/git-scope.sh", "scripts/lib/hardcoded-value-rules.sh")


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)


@pytest.fixture()
def repo(tmp_path: Path) -> tuple[Path, str]:
    """A two-commit repo whose base commit holds the real baseline."""
    root = tmp_path / "repo"
    for rel in (GUARD_REL, BASELINE_REL, *LIBS):
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO_ROOT / rel, dest)
    (root / GUARD_REL).chmod(0o755)
    _git(root.parent, "init", "--quiet", "-b", "main", str(root))
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    _git(root, "add", "-A")
    _git(root, "commit", "--quiet", "-m", "base")
    return root, _git(root, "rev-parse", "HEAD").stdout.strip()


def _run(repo_and_base: tuple[Path, str]) -> subprocess.CompletedProcess:
    root, base = repo_and_base
    return subprocess.run(
        ["bash", str(root / GUARD_REL)],
        cwd=root,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(root), "BASE_SHA": base},
    )


def _baseline(root: Path) -> Path:
    return root / BASELINE_REL


def _first_entry_index(lines: list[str]) -> int:
    for i, line in enumerate(lines):
        if line[:1].isdigit():
            return i
    raise AssertionError("no baseline entry found — the fixture is wrong, not the guard")


def test_an_unchanged_baseline_passes(repo) -> None:
    result = _run(repo)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "no key added and no count increased" in result.stdout


def test_a_fabricated_new_key_fails(repo) -> None:
    """The bypass itself: append a key for a violation introduced in the same change."""
    root, _ = repo
    with _baseline(root).open("a", encoding="utf-8") as handle:
        handle.write("1|ssot|autobot-backend/brand_new_file.py|172.16.168.77\n")
    result = _run(repo)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "NEW-KEY" in result.stdout
    assert "brand_new_file.py" in result.stdout


def test_bumping_an_existing_count_fails(repo) -> None:
    root, _ = repo
    lines = _baseline(root).read_text(encoding="utf-8").splitlines(keepends=True)
    i = _first_entry_index(lines)
    count, _, rest = lines[i].partition("|")
    lines[i] = f"{int(count) + 1}|{rest}"
    _baseline(root).write_text("".join(lines), encoding="utf-8")
    result = _run(repo)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "COUNT-UP" in result.stdout


def test_removing_an_entry_passes(repo) -> None:
    """Shrinking is how a fixed violation leaves; blocking it makes the file unmaintainable."""
    root, _ = repo
    lines = _baseline(root).read_text(encoding="utf-8").splitlines(keepends=True)
    del lines[_first_entry_index(lines)]
    _baseline(root).write_text("".join(lines), encoding="utf-8")
    result = _run(repo)
    assert result.returncode == 0, result.stdout + result.stderr


def test_decreasing_a_count_passes(repo) -> None:
    root, _ = repo
    lines = _baseline(root).read_text(encoding="utf-8").splitlines(keepends=True)
    for i, line in enumerate(lines):
        count, _, rest = line.partition("|")
        if count.isdigit() and int(count) > 1:
            lines[i] = f"{int(count) - 1}|{rest}"
            break
    else:
        pytest.skip("no multi-count entry in the baseline to decrease")
    _baseline(root).write_text("".join(lines), encoding="utf-8")
    result = _run(repo)
    assert result.returncode == 0, result.stdout + result.stderr


def test_an_unparseable_baseline_fails_rather_than_skipping(repo) -> None:
    root, _ = repo
    lines = _baseline(root).read_text(encoding="utf-8").splitlines(keepends=True)
    i = _first_entry_index(lines)
    lines[i] = "notanumber|" + lines[i].partition("|")[2]
    _baseline(root).write_text("".join(lines), encoding="utf-8")
    result = _run(repo)
    assert result.returncode != 0
    assert "refusing to report clean" in (result.stdout + result.stderr)


def test_a_missing_baseline_fails_rather_than_skipping(repo) -> None:
    root, _ = repo
    _baseline(root).unlink()
    result = _run(repo)
    assert result.returncode != 0
    assert "refusing to report clean" in (result.stdout + result.stderr)


def test_an_unresolvable_base_fails_rather_than_skipping(repo) -> None:
    """'Cannot determine' must never read as 'clean' — the class this PR fixes."""
    root, _ = repo
    absent = "0" * 40
    result = subprocess.run(
        ["bash", str(root / GUARD_REL)],
        cwd=root,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(root), "BASE_SHA": absent, "HEAD_SHA": absent},
    )
    assert result.returncode != 0
    assert "cannot resolve a base commit" in (result.stdout + result.stderr)


def test_an_absent_baseline_at_base_is_the_introduction_not_a_reset(repo) -> None:
    """A baseline that does not exist at the base ref is the commit adding it.

    Not a bypass route: deleting the file to reset it makes the detector itself
    fatal on its very next run, so a delete-and-regrow lands red first.
    """
    root, _ = repo
    _git(root, "rm", "--quiet", BASELINE_REL)
    _git(root, "commit", "--quiet", "-m", "remove baseline")
    empty_base = _git(root, "rev-parse", "HEAD").stdout.strip()
    shutil.copy(REPO_ROOT / BASELINE_REL, _baseline(root))
    result = subprocess.run(
        ["bash", str(root / GUARD_REL)],
        cwd=root,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(root), "BASE_SHA": empty_base},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "does not exist at" in result.stdout
