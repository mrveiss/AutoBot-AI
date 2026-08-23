# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for check_workflow_path_filters.py (#12986).

Every test here MUTATES a copy of the real `.github/` tree and asserts the
guard goes red. Re-running a guard against an unchanged tree proves only that
it is quiet, which is the state a guard that checks nothing is also in.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
GUARD = REPO_ROOT / "pipeline-scripts" / "check_workflow_path_filters.py"
CANONICAL = Path(".github/filters/backend-python-paths.yml")


def _sandbox(tmp_path: Path) -> Path:
    """A copy of the real `.github/` tree the guard can be pointed at."""
    shutil.copytree(REPO_ROOT / ".github", tmp_path / ".github")
    return tmp_path


def _run(cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(GUARD)], cwd=cwd, capture_output=True, text=True)


def _edit(path: Path, old: str, new: str) -> None:
    """Replace *old* with *new*, refusing to proceed if *old* is not there.

    A mutation whose target is missing produces an unchanged file and the test
    then reports a confident PASS over a guard that was never exercised.
    """
    text = path.read_text(encoding="utf-8")
    assert old in text, f"mutation target missing in {path}: {old!r}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def test_the_real_tree_passes(tmp_path: Path) -> None:
    result = _run(_sandbox(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr
    # Presence, not absence-of-failure: a guard that scanned nothing is silent
    # in exactly the same way as a guard that scanned a clean tree.
    assert "inline path list(s) match the canonical set" in result.stdout
    assert result.stdout.count("  OK     ") >= 7


def test_dropping_a_canonical_path_from_an_inline_copy_fails(tmp_path: Path) -> None:
    root = _sandbox(tmp_path)
    _edit(root / ".github/workflows/api-wiring.yml", "      - 'autobot_shared/**/*.py'\n", "")
    result = _run(root)
    assert result.returncode == 1, result.stdout
    assert "api-wiring.yml" in result.stdout
    assert "autobot_shared/**/*.py" in result.stdout


def test_adding_to_the_canonical_set_reds_every_inline_consumer(tmp_path: Path) -> None:
    """"Adding a path in one place demonstrably affects all consumers"."""
    root = _sandbox(tmp_path)
    _edit(
        root / CANONICAL,
        "  - 'autobot_shared/**/*.py'",
        "  - 'autobot_shared/**/*.py'\n  - 'autobot-new-backend/**/*.py'",
    )
    result = _run(root)
    assert result.returncode == 1, result.stdout
    assert result.stdout.count("  FAIL   ") == 6, result.stdout


def test_reintroducing_api_wiring_pull_request_paths_fails(tmp_path: Path) -> None:
    """#12934's deliberate asymmetry must not be tidied back into a deadlock."""
    root = _sandbox(tmp_path)
    _edit(
        root / ".github/workflows/api-wiring.yml",
        "    branches: [ main, Dev_new_gui ]\n\nconcurrency:",
        "    paths:\n      - 'autobot-backend/**/*.py'\n    branches: [ main, Dev_new_gui ]\n\nconcurrency:",
    )
    result = _run(root)
    assert result.returncode == 1, result.stdout
    assert "must stay ABSENT" in result.stdout


def test_a_stale_declaration_fails_rather_than_exempting_silently(tmp_path: Path) -> None:
    """An allowlist entry naming a moved file exempts nothing, silently."""
    root = _sandbox(tmp_path)
    (root / ".github/workflows/api-wiring.yml").rename(root / ".github/workflows/api-wiring-renamed.yml")
    result = _run(root)
    assert result.returncode == 1, result.stdout
    assert "the table is stale" in result.stdout


def test_an_undeclared_consumer_of_the_filter_file_fails(tmp_path: Path) -> None:
    root = _sandbox(tmp_path)
    (root / ".github/workflows/zz-new-gate.yml").write_text(
        "name: zz\n"
        "on:\n  pull_request:\n    branches: [Dev_new_gui]\n"
        "jobs:\n"
        "  changes:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - uses: dorny/paths-filter@ceb8a2b8f2d89434be7ff52d3de7ec3738c5cc9d\n"
        "        with:\n"
        f"          filters: {CANONICAL}\n",
        encoding="utf-8",
    )
    result = _run(root)
    assert result.returncode == 1, result.stdout
    assert "is not declared in INLINE_CONSUMERS" in result.stdout


def test_an_unparseable_canonical_file_is_fatal_not_a_pass(tmp_path: Path) -> None:
    root = _sandbox(tmp_path)
    (root / CANONICAL).write_text("backend-python: [\n", encoding="utf-8")
    result = _run(root)
    assert result.returncode != 0
    assert "FATAL" in (result.stdout + result.stderr)


def test_an_empty_canonical_set_is_fatal_not_a_pass(tmp_path: Path) -> None:
    """An empty result must not read as a clean result."""
    root = _sandbox(tmp_path)
    (root / CANONICAL).write_text("backend-python: []\n", encoding="utf-8")
    result = _run(root)
    assert result.returncode != 0
    assert "nothing to enforce" in (result.stdout + result.stderr)


@pytest.mark.parametrize(
    "workflow",
    ["phase_validation.yml", "security.yml", "ai-security-review.yml", "startup-import-smoke.yml", "api-wiring.yml", "auto-fix-generated-types.yml"],
)
def test_every_declared_consumer_is_actually_reached(tmp_path: Path, workflow: str) -> None:
    """Each declared consumer must be one the guard really inspects.

    A guard narrower than its own declared subject reads as coverage. Deleting
    the canonical entry from one workflow at a time proves that workflow is on
    the path the guard walks, rather than merely named in a table.
    """
    root = _sandbox(tmp_path)
    _edit(root / ".github/workflows" / workflow, "      - 'autobot-backend/**/*.py'\n", "")
    result = _run(root)
    assert result.returncode == 1, result.stdout
    assert workflow in result.stdout
