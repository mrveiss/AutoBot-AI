# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The Migration Gate must run when the code its tests exercise changes (#17822).

**The defect this exists to prevent, which already happened once.** The gate's
path filter listed ``autobot-backend/migrations/**`` and
``autobot-backend/tests/migrations/**`` -- the tests' own location. It did not
list the production modules those tests import. So #17772 changed
``services/secrets_coordinator.py``, the filter did not match, ``migration-tests``
was **skipped**, the run rolled up to ``success``, and it merged. Five tests had
been failing and nobody was told for a day.

A skip is the dangerous shape here precisely because it is not a failure. The
gate reported the truth -- it did not run -- in a form that reads as consent.

This guard closes the loop the other way round: rather than trusting a
hand-maintained list, it derives what the tests actually import and requires the
filter to cover each one. Adding a new import to a migration test without
widening the filter now fails here instead of silently shrinking coverage.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
import yaml
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_WORKFLOW = Path(".github/workflows/migration-gate.yml")
_TEST_DIR = Path("autobot-backend/tests/migrations")
#: The reusable job the caller hands its filter to (#15360). The push trigger lists it too, so
#: editing the detection logic reruns the gate; the filter itself does not.
_REUSABLE = ".github/workflows/_changes.yml"
_FILTER_KEY = "migrations"


def _migration_test_files(root: Path) -> list[str]:
    """Every tracked python file under the migration tests: the whole input of the import sweep."""
    try:
        tracked = tracked_paths(root, _TEST_DIR.as_posix())
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if rel.endswith(".py")]


REACH = declare(
    "migration-gate-test-import-sweep",
    discover=_migration_test_files,
    # Mid-window, from REACH.window(); the arithmetic is on the PR, not here.
    floor=45,  # #15907: mid-window, population 39, window (33, 39)
    what="tracked migration test modules",
    roots=(_TEST_DIR.as_posix(),),
    growth=6,
)

#: Import roots that resolve inside the repo, and the tree each lives under.
#: ``autobot-backend`` is on the path at runtime, so ``services.x`` means
#: ``autobot-backend/services/x.py``.
_ROOTS = {
    "services": "autobot-backend",
    "models": "autobot-backend",
    "api": "autobot-backend",
    "llc": "autobot-backend",
    "user_management": "autobot-backend",
    "autobot_shared": "",
}


def _caller_filter(source: str) -> list[str]:
    """The ``migrations`` globs in the ``with: filters`` of the ``changes`` job.

    Parsed, not matched textually: the filter is inline YAML inside a block scalar, and the job
    must be the one that calls the reusable workflow, or the list read is not the list in force.
    """
    job = yaml.safe_load(source)["jobs"]["changes"]
    assert job.get("uses") == "./" + _REUSABLE, "`changes` does not call the reusable job; wrong shape"
    return list(yaml.safe_load(job["with"]["filters"])[_FILTER_KEY])


def _push_paths(source: str) -> list[str]:
    """``on.push.paths`` (PyYAML reads the ``on`` key as the boolean ``True``)."""
    doc = yaml.safe_load(source)
    return list(doc[True if True in doc else "on"]["push"]["paths"])


def _imported_modules(root: Path) -> set[str]:
    """First-party dotted module names imported by the migration tests."""
    found: set[str] = set()
    for rel in sorted(REACH.examined(root)):
        module = ast.parse((root / rel).read_text(encoding="utf-8", errors="replace"))
        for node in ast.walk(module):
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                found.add(node.module)
            elif isinstance(node, ast.Import):
                found.update(alias.name for alias in node.names)
    return {m for m in found if m.split(".")[0] in _ROOTS}


def _module_to_path(module: str, root: Path) -> Path | None:
    """The repo-relative file a dotted module resolves to, if one exists."""
    head, *rest = module.split(".")
    base = Path(_ROOTS[head]) / head / Path(*rest) if rest else Path(_ROOTS[head]) / head
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if (root / candidate).is_file():
            return candidate
    return None


def _matches(rel: str, glob: str) -> bool:
    """dorny/paths-filter semantics: ``**`` spans directories, ``*`` does not."""
    parts = []
    for chunk in re.split(r"(\*\*/?|\*|\?)", glob):
        if chunk == "*":
            parts.append("[^/]*")
        elif chunk == "?":
            parts.append("[^/]")
        elif chunk in ("**", "**/"):
            parts.append(".*")
        else:
            parts.append(re.escape(chunk))
    return re.fullmatch("".join(parts), rel) is not None


def _covered_modules() -> tuple[list[str], list[str], int]:
    root = repo_root()
    globs = _caller_filter((root / _WORKFLOW).read_text(encoding="utf-8"))
    uncovered, covered = [], []
    for module in sorted(_imported_modules(root)):
        rel = _module_to_path(module, root)
        if rel is None:
            continue  # a namespace package or a module that moved; not this guard's subject
        (covered if any(_matches(rel.as_posix(), g) for g in globs) else uncovered).append(module)
    return covered, uncovered, len(globs)


def test_the_push_trigger_and_the_filter_list_the_same_paths() -> None:
    """Two copies of one list; a path added to one and not the other is the old bug.

    The push trigger carries exactly one extra entry, the reusable job (#15360); nothing else.
    """
    source = (repo_root() / _WORKFLOW).read_text(encoding="utf-8")
    on_paths, filter_paths = _push_paths(source), _caller_filter(source)
    assert on_paths and filter_paths, "neither list was found — the guard is reading the wrong shape"
    assert sorted(set(on_paths) - {_REUSABLE}) == sorted(filter_paths), (
        "the trigger list and the caller's filter disagree:\n"
        f"  only in on.push: {sorted(set(on_paths) - set(filter_paths) - {_REUSABLE})}\n"
        f"  only in the filter: {sorted(set(filter_paths) - set(on_paths))}"
    )
    assert _REUSABLE in on_paths, "editing the reusable job no longer reruns the gate on push"


def test_every_module_the_migration_tests_import_is_covered_by_the_filter() -> None:
    covered, uncovered, _ = _covered_modules()
    assert not uncovered, (
        "the Migration Gate will NOT run when these change, yet its tests import them:\n  "
        + "\n  ".join(uncovered)
        + "\n\nAdd a matching glob to BOTH lists in .github/workflows/migration-gate.yml (on.push.paths and the `changes` job filter). "
        "A gate that skips on the code under test reports success without running (#17822)."
    )
    assert covered, "no first-party import resolved at all — the resolver is broken, not the filter"


def test_the_coverage_check_is_not_vacuous() -> None:
    """Non-vacuity, bound to what was actually resolved rather than to a clean result."""
    covered, _, glob_count = _covered_modules()
    assert len(covered) >= 15, (
        f"only {len(covered)} imported module(s) resolved to a file; expected the secrets and "
        "credential surface. A resolver that finds nothing makes the check above always pass."
    )
    assert glob_count >= 20, f"only {glob_count} globs read from the workflow; the two lists total more"


#: Synthetic on purpose. Real repo globs here read to `glob_declared_reads_15900_test`
#: as trees THIS guard depends on, which would record a dependency that does not exist --
#: the matcher cases are data, not reads. Same shape as the prose-counting defects this
#: repo keeps finding, so the fix is to stop writing the literal, not to record it.
@pytest.mark.parametrize(
    ("rel", "glob", "expected"),
    [
        ("tree/services/secrets_coordinator.py", "tree/services/*secret*.py", True),
        ("tree/services/secrets_coordinator.py", "tree/elsewhere/**", False),
        ("tree/models/secret.py", "tree/models/**", True),
        ("tree/models/deep/nested/secret.py", "tree/models/**", True),
        # `*` must not cross a directory separator, or every glob matches everything
        # and the coverage check above passes by being broken.
        ("tree/services/sub/secret.py", "tree/services/*secret*.py", False),
        ("tree/services/secret.py", "tree/*/secret.py", True),
        ("tree/a/b/secret.py", "tree/*/secret.py", False),
    ],
)
def test_the_glob_matcher_itself(rel: str, glob: str, expected: bool) -> None:
    """The contrast pairs. A matcher that always returns True would pass the test above."""
    assert _matches(rel, glob) is expected
