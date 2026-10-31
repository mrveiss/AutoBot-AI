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

#: Where the `migrations` globs live since #18208 -- one key in one filter file, loaded by ci.yml's
#: `changes` job. They used to be an inline `filters:` block AND a copy in `on.push.paths`.
_FILTER_FILE = Path(".github/filters/gate-paths.yml")
_WORKFLOW = Path(".github/workflows/_gate-migration.yml")
_CI = Path(".github/workflows/ci.yml")
_TEST_DIR = Path("autobot-backend/tests/migrations")
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
    floor=42,  # #15907: mid-window, population 39, window (33, 39)
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


def _filter_globs(source: str) -> list[str]:
    """The ``migrations`` globs in the filter file the ``changes`` job loads."""
    return list(yaml.safe_load(source)[_FILTER_KEY])


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
    globs = _filter_globs((root / _FILTER_FILE).read_text(encoding="utf-8"))
    uncovered, covered = [], []
    for module in sorted(_imported_modules(root)):
        rel = _module_to_path(module, root)
        if rel is None:
            continue  # a namespace package or a module that moved; not this guard's subject
        (covered if any(_matches(rel.as_posix(), g) for g in globs) else uncovered).append(module)
    return covered, uncovered, len(globs)


def test_the_filter_has_one_home_and_no_trigger_copy() -> None:
    """Two copies of one list was the old bug; since #18208 there is one.

    The list is a key of ``gate-paths.yml``, loaded by ci.yml's ``changes`` job. The reusable body
    has no ``push``/``pull_request`` trigger, so there is no ``on.paths`` copy left to drift.
    """
    root = repo_root()
    ci = yaml.safe_load((root / _CI).read_text(encoding="utf-8"))
    loaded = [s["with"]["filters"] for s in ci["jobs"]["changes"]["steps"] if "paths-filter" in str(s.get("uses", ""))]
    assert str(_FILTER_FILE) in loaded, "ci.yml's `changes` job no longer loads the filter file holding `migrations`"
    body = yaml.safe_load((root / _WORKFLOW).read_text(encoding="utf-8"))
    triggers = body.get(True) or body.get("on") or {}
    assert set(triggers) == {
        "workflow_call"
    }, f"{_WORKFLOW.name} grew triggers {sorted(triggers)}: a path copy can return"
    assert _filter_globs((root / _FILTER_FILE).read_text(encoding="utf-8")), "the `migrations` key is empty"


def test_every_module_the_migration_tests_import_is_covered_by_the_filter() -> None:
    covered, uncovered, _ = _covered_modules()
    assert not uncovered, (
        "the Migration Gate will NOT run when these change, yet its tests import them:\n  "
        + "\n  ".join(uncovered)
        + "\n\nAdd a matching glob to the `migrations` key of .github/filters/gate-paths.yml. "
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
    assert glob_count >= 20, f"only {glob_count} globs read from the filter file"


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
