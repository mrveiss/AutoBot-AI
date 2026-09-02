# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Python embedded in a shell script must import things that exist (#14876).

Seven issues (#14518, #14867, #14870, #14871, #14872, #14875, #14876) are all
one defect: the code says it needs X and X is not there. They differ only in how
the absence hides — an undeclared dependency that happened to be installed
transitively, a symbol that was deleted, a package that never existed, or an
import buried in a shell heredoc where no linter looks.

Two guards already cover parts of this:

* ``first_party_imports_resolve_test.py`` (#14839) — first-party imports under
  ``autobot-backend/``;
* ``deployment_script_imports_resolve_test.py`` (#14866) — inline imports under
  ``autobot-infrastructure/shared/scripts/``, but ONLY first-party ones: it
  skips anything in its ``_EXTERNAL_PREFIXES`` set without ever asking whether
  that package is declared. ``websockify`` sat in that set, and
  ``pytest_json_report`` was not matched at all.

Neither reaches the two gaps this file closes:

1. **Third-party names go unchecked.** ``run_benchmarks.sh`` imported
   ``pytest_json_report`` — declared in no requirements file anywhere — and
   answered its absence with a placeholder JSON that a downstream reader could
   not tell from a real benchmark report (#14876).
2. **Only one shell tree was swept.** ``bootstrap-slm.sh`` lives under
   ``autobot-infrastructure/autobot-slm-backend/scripts/``, outside the other
   guard's root, and its inline block imported ``database.db`` and
   ``models.user`` — neither of which exists in ``autobot-slm-backend/`` — under
   ``2>/dev/null || warn``. It had never been swept by anything.

So this sweeps EVERY tracked shell script in the repository and asks one
question of every non-stdlib import inside embedded Python: does it resolve
against a first-party root, or is its distribution declared in a requirements
file? An import that answers neither is the defect.

Scope note: like its siblings this resolves the **module**, never the imported
name. Resolving names means importing, and a static check has no business
executing package ``__init__`` side effects.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404  # fixed argv, no shell, no caller input
import sys
from pathlib import Path

import pytest

from repo_tests.declared_distributions import SKIP_PARTS, declared_distributions

from autobot_shared.paths import scrubbed_git_env

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Roots a shell script's inline python may resolve an import against. Each
# script also gets its own directory, because several export ${SCRIPT_DIR} on
# PYTHONPATH and import a sibling module.
_ROOTS = (
    _REPO_ROOT,
    _REPO_ROOT / "autobot-backend",
    _REPO_ROOT / "autobot-slm-backend",
    _REPO_ROOT / "autobot-infrastructure" / "shared" / "scripts",
)

# Top-level trees that must each contribute at least one swept script. Flooring
# the UNION is what let a sibling guard pass for years while one of its two
# pathspecs matched nothing: the other half satisfied the total. A floor has to
# measure the input that can go to zero, so each of these is asserted alone.
_REQUIRED_TREES = ("autobot-infrastructure", "autobot-slm-backend", "scripts")

# Import name -> distribution name, where the two differ. An unknown alias
# produces a finding, never a silent pass.
_DIST_ALIASES = {
    "yaml": "pyyaml",
    "dotenv": "python_dotenv",
    "PIL": "pillow",
    "cv2": "opencv_python",
    "sklearn": "scikit_learn",
    "psycopg2": "psycopg2_binary",
    "jwt": "pyjwt",
    "bs4": "beautifulsoup4",
    "pkg_resources": "setuptools",
}

_SKIP_PARTS = SKIP_PARTS

# Both spellings, and both block shapes. A single-line `python3 -c "import x"`
# hides mid-line behind the shell quoting, so a line-anchored pattern slides
# past it; a heredoc's imports are lines in their own right.
_IMPORT = re.compile(r"^[ \t]*(?:from[ \t]+([a-zA-Z_][\w.]*)[ \t]+import[ \t]|import[ \t]+([a-zA-Z_][\w.]*))", re.M)
_PY_INLINE = re.compile(r'python3? -c ["\']([^"\'\n]+)["\']')

_STDLIB = set(sys.stdlib_module_names) | {"__future__"}


def _tracked_shell_scripts() -> list[Path]:
    """Every tracked ``*.sh``, from git rather than a walk.

    ``git ls-files`` and not ``rglob``: a walk picks up the ~160 agent worktrees
    under ``.worktrees/``, whose requirements files belong to other branches and
    whose scripts are not this branch's problem.
    """
    out = subprocess.run(  # nosec B603  # fixed argv
        ["git", "-C", str(_REPO_ROOT), "ls-files", "*.sh"],
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_git_env(),
    ).stdout
    return [_REPO_ROOT / line for line in out.splitlines() if line]


_DECLARED, _REQUIREMENTS_FILES = declared_distributions(_REPO_ROOT)


def _is_declared(top: str) -> bool:
    """Is this top-level import name covered by a declared distribution?"""
    normalised = top.lower().replace("-", "_")
    if normalised in _DECLARED:
        return True
    alias = _DIST_ALIASES.get(top)
    if alias is not None and alias in _DECLARED:
        return True
    # Namespace distributions publish under a longer name than they import:
    # `opentelemetry` arrives as `opentelemetry-api`, `google` as
    # `google-generativeai`. Requiring an alias entry for each would mean a
    # guard that has to be taught every name, and one eventually taught to
    # ignore a first-party one.
    return any(declared.startswith(normalised + "_") for declared in _DECLARED)


def _resolves(module: str, own_dir: Path) -> bool:
    """Does this dotted module exist under a first-party root or beside its importer?"""
    parts = module.split(".")
    for root in (*_ROOTS, own_dir):
        base = root.joinpath(*parts)
        if base.with_suffix(".py").exists() or (base / "__init__.py").exists():
            return True
    return False


def _embedded_imports(text: str) -> list[tuple[str, int]]:
    """(module, line) for every import in ``text``, deduplicated by module.

    Two passes. The raw text catches heredoc blocks, whose imports are lines in
    their own right. A single-line ``python3 -c "import x.y"`` is not a line of
    its own, so it needs the second pass — and that is exactly the shape
    ``test_desktop_setup.sh`` and ``run_benchmarks.sh`` used.
    """
    found: dict[str, int] = {}
    for match in _IMPORT.finditer(text):
        module = match.group(1) or match.group(2)
        found.setdefault(module, text[: match.start()].count("\n") + 1)
    for block in _PY_INLINE.finditer(text):
        base = text[: block.start()].count("\n") + 1
        for match in _IMPORT.finditer(block.group(1)):
            module = match.group(1) or match.group(2)
            found.setdefault(module, base)
    return sorted(found.items())


def _undeclared_in_text(text: str, own_dir: Path) -> list[tuple[str, int]]:
    """(module, line) for imports resolving to nothing and declared nowhere.

    Split out from the sweep so the detector can be driven against a synthetic
    sample. With no offender left in the tree, "the sweep found something" can
    no longer prove the matcher works.
    """
    offenders: list[tuple[str, int]] = []
    for module, line in _embedded_imports(text):
        top = module.split(".")[0]
        if top in _STDLIB:
            continue
        if _resolves(module, own_dir) or _is_declared(top):
            continue
        offenders.append((module, line))
    return offenders


def _sweep() -> tuple[list[str], dict[str, int], int]:
    """(offenders, scripts scanned per tree, non-stdlib imports seen)."""
    offenders: list[str] = []
    per_tree: dict[str, int] = {}
    seen = 0
    for script in _tracked_shell_scripts():
        rel = script.relative_to(_REPO_ROOT)
        per_tree[rel.parts[0]] = per_tree.get(rel.parts[0], 0) + 1
        try:
            text = script.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        seen += sum(1 for module, _ in _embedded_imports(text) if module.split(".")[0] not in _STDLIB)
        offenders.extend(f"{rel}:{line}  {module}" for module, line in _undeclared_in_text(text, script.parent))
    return offenders, per_tree, seen


@pytest.mark.parametrize("tree", _REQUIRED_TREES)
def test_each_shell_tree_was_actually_swept(tree: str) -> None:
    """Per-tree floor, deliberately NOT a total across the repository.

    A recently-found guard passed for years while one of its two ``git
    ls-files`` pathspecs matched zero files: the union's floor was satisfied by
    the other half, so nothing said half the sweep had gone blind. Flooring each
    tree separately is what makes a tree that stops contributing fail here
    rather than pass quietly.

    ``autobot-slm-backend`` is the one that matters most: the defect that
    prompted this file (``bootstrap-slm.sh``) sat in a tree no guard reached.
    """
    _, per_tree, _ = _sweep()
    assert per_tree.get(tree, 0) > 0, (
        f"no tracked shell script was swept under {tree}/ — that tree has "
        "dropped out of this guard's reach and every assertion about it below "
        "now passes over nothing"
    )


def test_the_sweep_reached_the_repository() -> None:
    """The remaining discovery floors, each guarding a different way to go blind."""
    _, per_tree, seen = _sweep()

    assert sum(per_tree.values()) > 150, (
        f"only walked {sum(per_tree.values())} shell scripts — git ls-files is not " "returning the tree"
    )
    assert seen > 10, (
        "no shell script embeds a non-stdlib import any more, or the import "
        "pattern stopped matching — both make the check below vacuous"
    )
    assert _REQUIREMENTS_FILES >= 30, (
        f"only read {_REQUIREMENTS_FILES} requirements/pyproject files, floor 30 "
        f"(37 measured after the #15518 widening) — the declaration oracle has "
        "gone blind and would report false findings"
    )
    assert len(_DECLARED) > 100, f"only {len(_DECLARED)} declared distributions found"
    for root in _ROOTS:
        assert root.is_dir(), f"first-party root {root} no longer exists — resolution is wrong"


@pytest.mark.parametrize(
    "source,expected",
    [
        ('python3 -c "import autobot_nonexistent_pkg_14876"\n', "autobot_nonexistent_pkg_14876"),
        ("python3 <<'PY'\nfrom autobot_nonexistent_pkg_14876 import thing\nPY\n", "autobot_nonexistent_pkg_14876"),
        ("python3 <<'PY'\nfrom database.db import init_db\nPY\n", "database.db"),
    ],
)
def test_the_detector_still_fires(source: str, expected: str) -> None:
    """Positive control. The sweep is clean, so it proves nothing on its own.

    Three shapes, because each is a way this guard has already been blind:
    the single-line ``python3 -c`` form that a line-anchored pattern misses, the
    heredoc form, and the real ``bootstrap-slm.sh`` import that no guard reached
    at all.
    """
    hits = _undeclared_in_text(source, _REPO_ROOT)
    assert hits, f"the detector no longer flags {source.strip()!r}"
    assert hits[0][0] == expected


@pytest.mark.parametrize(
    "source",
    [
        'python3 -c "import json"\n',
        'python3 -c "import redis"\n',
        "python3 <<'PY'\nfrom autobot_shared.logging_manager import get_logger\nPY\n",
        "python3 <<'PY'\nimport opentelemetry\nPY\n",
    ],
)
def test_the_detector_does_not_fire_on_a_legitimate_import(source: str) -> None:
    """Negative control: stdlib, declared third-party, first-party, namespace distribution.

    Without this a detector that flagged everything would satisfy the positive
    control above, and the pressure would be to switch this guard off rather
    than repair it. The ``opentelemetry`` case pins the prefix rule in
    ``_is_declared``: the distribution is ``opentelemetry-api``, so an exact
    name match alone reports a false finding.
    """
    assert not _undeclared_in_text(source, _REPO_ROOT), f"{source.strip()!r} is legitimate and must not be flagged"


def test_every_embedded_import_resolves_or_is_declared() -> None:
    """The defect: a shell-embedded import naming something that is not there.

    No allowlist, on purpose. #14518 asked for the resolution check "with no
    allowlist, once the count is zero", and the count is zero — so an entry
    added here would be a new live bug, not an accepted exception.
    """
    offenders, _, _ = _sweep()

    assert not offenders, (
        "these shell scripts embed Python importing a module that resolves "
        "against no first-party root AND names no distribution declared in any "
        "requirements file. The block raises ModuleNotFoundError on every run — "
        "and these scripts routinely discard the failure, so the check reports "
        "without ever running (#14876):\n  " + "\n  ".join(offenders)
    )
