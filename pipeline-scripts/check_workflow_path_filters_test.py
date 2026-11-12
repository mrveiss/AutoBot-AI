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
CODE_QUALITY = Path(".github/filters/code-quality-paths.yml")
GATE_PATHS = ".github/filters/gate-paths.yml"
CI = ".github/workflows/ci.yml"


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
    assert "inline path list(s) match their canonical set" in result.stdout
    assert result.stdout.count("  OK     ") >= 6


def test_dropping_a_canonical_path_from_an_inline_copy_fails(tmp_path: Path) -> None:
    root = _sandbox(tmp_path)
    _edit(root / ".github/workflows/phase_validation.yml", "      - 'autobot_shared/**/*.py'\n", "")
    result = _run(root)
    assert result.returncode == 1, result.stdout
    assert "phase_validation.yml" in result.stdout
    assert "autobot_shared/**/*.py" in result.stdout


def test_adding_to_the_canonical_set_reds_every_copy(tmp_path: Path) -> None:
    """ "Adding a path in one place demonstrably affects all consumers": two triggers and one filter key."""
    root = _sandbox(tmp_path)
    _edit(
        root / CANONICAL,
        "  - 'autobot_shared/**/*.py'",
        "  - 'autobot_shared/**/*.py'\n  - 'autobot-new-backend/**/*.py'",
    )
    result = _run(root)
    assert result.returncode == 1, result.stdout
    assert result.stdout.count("  FAIL   ") == 3, result.stdout
    assert "security_scope" in result.stdout


def test_dropping_a_canonical_path_from_the_security_scope_key_fails(tmp_path: Path) -> None:
    """security.yml's `on.pull_request.paths` became a filter key; it must still carry the whole set."""
    root = _sandbox(tmp_path)
    text = (root / GATE_PATHS).read_text(encoding="utf-8")
    head, _, tail = text.partition("security_scope:\n")
    assert "  - 'autobot_shared/**/*.py'\n" in tail
    (root / GATE_PATHS).write_text(
        head + "security_scope:\n" + tail.replace("  - 'autobot_shared/**/*.py'\n", "", 1), encoding="utf-8"
    )
    result = _run(root)
    assert result.returncode == 1, result.stdout
    assert "filter 'security_scope' is missing" in result.stdout


def test_reintroducing_ci_pull_request_paths_fails(tmp_path: Path) -> None:
    """#12934's deliberate asymmetry must not be tidied back into a deadlock."""
    root = _sandbox(tmp_path)
    _edit(
        root / CI,
        "    types: [opened, synchronize, reopened, ready_for_review]\n",
        "    types: [opened, synchronize, reopened, ready_for_review]\n    paths:\n      - 'autobot-backend/**/*.py'\n",
    )
    result = _run(root)
    assert result.returncode == 1, result.stdout
    assert "must stay ABSENT" in result.stdout


def test_a_stale_declaration_fails_rather_than_exempting_silently(tmp_path: Path) -> None:
    """An allowlist entry naming a moved file exempts nothing, silently."""
    root = _sandbox(tmp_path)
    (root / ".github/workflows/phase_validation.yml").rename(root / ".github/workflows/phase_validation_renamed.yml")
    result = _run(root)
    assert result.returncode == 1, result.stdout
    assert "the table is stale" in result.stdout


def test_a_stale_filter_file_declaration_fails(tmp_path: Path) -> None:
    root = _sandbox(tmp_path)
    (root / GATE_PATHS).rename(root / ".github/filters/gate-paths-renamed.yml")
    result = _run(root)
    assert result.returncode == 1, result.stdout
    assert "gate-paths.yml: declared in this guard's table but does not exist" in result.stdout


def test_an_undeclared_consumer_of_the_filter_file_fails(tmp_path: Path) -> None:
    root = _sandbox(tmp_path)
    (root / ".github/workflows/zz-new-gate.yml").write_text(
        "name: zz\n"
        "on:\n  pull_request:\n    branches: [main]\n"
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


# ── the second canonical set: `code-quality`'s path list (#15608) ────────────
#
# Its `on.push.paths` copy went away with code-quality.yml (#18208), so what is left to police
# is that the file stays a non-empty list and that a new consumer cannot arrive undeclared.


def test_an_empty_code_quality_set_is_fatal_not_a_pass(tmp_path: Path) -> None:
    """An emptied second set must not read as a clean scan of nothing."""
    root = _sandbox(tmp_path)
    (root / CODE_QUALITY).write_text("backend: []\n", encoding="utf-8")
    result = _run(root)
    assert result.returncode != 0
    assert "nothing to enforce" in (result.stdout + result.stderr)


def test_an_undeclared_consumer_of_the_code_quality_filter_fails(tmp_path: Path) -> None:
    """A new consumer of the second set cannot arrive undeclared either."""
    root = _sandbox(tmp_path)
    workflow = root / ".github/workflows/undeclared-code-quality-consumer.yml"
    workflow.write_text(
        "name: undeclared\n"
        "on:\n"
        "  pull_request:\n"
        "jobs:\n"
        "  changes:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - uses: dorny/paths-filter@v4\n"
        "        with:\n"
        f"          filters: {CODE_QUALITY}\n",
        encoding="utf-8",
    )
    result = _run(root)
    assert result.returncode == 1, result.stdout
    assert "undeclared-code-quality-consumer.yml" in result.stdout
    assert "is not declared in INLINE_CONSUMERS" in result.stdout


@pytest.mark.parametrize("workflow", ["phase_validation.yml", "auto-fix-generated-types.yml"])
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


# ── shared-tree watchers (#14885) ────────────────────────────────────────────
#
# `verify-generated-types` is a required context whose real work self-skipped on
# an autobot_shared-only change, while both generated api.ts files depend on
# that tree. It keeps a per-product filter split the canonical set would erase,
# so it is policed by SHARED_TREE_WATCHERS rather than by the superset check --
# and a second table is a second thing that can go quietly vacuous.

SHARED = "autobot_shared/**/*.py"


@pytest.mark.parametrize("marker", ["types", "slm_types"])
def test_dropping_the_shared_tree_from_a_filter_key_fails(tmp_path: Path, marker: str) -> None:
    """Each per-product filter is reached individually, not as a pair."""
    root = _sandbox(tmp_path)
    text = (root / GATE_PATHS).read_text(encoding="utf-8")
    head, _, tail = text.partition(f"\n{marker}:\n")
    assert f"  - '{SHARED}'\n" in tail
    (root / GATE_PATHS).write_text(head + f"\n{marker}:\n" + tail.replace(f"  - '{SHARED}'\n", "", 1), encoding="utf-8")
    result = _run(root)
    assert result.returncode == 1, result.stdout
    assert f"filter '{marker}' is missing" in result.stdout
    assert SHARED in result.stdout


def test_a_renamed_filter_key_fails_rather_than_exempting_silently(tmp_path: Path) -> None:
    """A restructure must strand the declaration loudly, not skip past it."""
    root = _sandbox(tmp_path)
    _edit(root / GATE_PATHS, "\nslm_types:\n", "\nslm_types_v2:\n")
    result = _run(root)
    assert result.returncode == 1, result.stdout
    assert "the table is stale" in result.stdout


def test_a_canonical_set_naming_no_shared_tree_is_fatal_not_a_pass(tmp_path: Path) -> None:
    """The derivation must die rather than assert nothing.

    Removing the shared tree from the canonical set leaves every inline copy a
    superset, so the check above stays green -- and every shared-tree assertion
    would pass over an empty list. That is the exact "empty result reads as a
    clean result" shape, one table over.
    """
    root = _sandbox(tmp_path)
    _edit(root / CANONICAL, f"  - '{SHARED}'\n", "")
    result = _run(root)
    assert result.returncode != 0
    assert "would assert nothing" in (result.stdout + result.stderr)


def test_a_watcher_entry_with_no_keys_fails(tmp_path: Path) -> None:
    """An entry that validates nothing must not ride on the other entries' totals.

    The global "zero checked" fallback only fires when the whole table is inert.
    A single entry declared with no keys contributes nothing while the others keep
    the totals non-zero, so the run would report success over a file this table
    claims to police. Nothing a `.github/` mutation can produce reaches that
    state, so the table itself is patched in a copy of the guard.
    """
    root = _sandbox(tmp_path)
    src = GUARD.read_text(encoding="utf-8")
    old = '"gate-paths.yml": ("types", "slm_types"),'
    assert old in src, "SHARED_TREE_WATCHERS entry not found -- the patch target moved"
    # A SECOND, valid entry is essential: with only the inert one, the global
    # "zero checked" fallback fires and the mutation would look killed for the
    # wrong reason. The copy is byte-identical, so its keys really do pass.
    shutil.copy(root / GATE_PATHS, root / ".github/filters/zz-gate-copy.yml")
    patched = root / "patched_guard.py"
    patched.write_text(
        src.replace(old, '"gate-paths.yml": (),\n    "zz-gate-copy.yml": ("types", "slm_types"),'),
        encoding="utf-8",
    )
    result = subprocess.run([sys.executable, str(patched)], cwd=root, capture_output=True, text=True)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "would assert nothing about this file" in result.stdout
