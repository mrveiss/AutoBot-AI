# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every analyzer in this package must construct (#15914).

Five classes here carried ``self.config = config`` with no such name in scope,
so **every** construction raised ``NameError``. They were written with
``from src.config import config``; #142 (2025-11-18) dropped the import from
``architectural_pattern_analyzer.py`` and #926 (2026-02-18) dropped it from the
other four, each leaving the assignment behind. The classes had therefore been
dead for six to nine months, and ``CodeQualityDashboard`` -- which constructs
two of them inside its own ``__init__`` -- was never runnable in this repo.

A SECOND, INDEPENDENT DEADNESS, found by trying to construct them rather than
by reading. #394 converted ``architectural_pattern_analyzer.py`` to a relative
import (``from .architectural_analysis import ...``) while all 14 other sibling
imports in this package stayed bare and every consumer kept importing it as a
top-level name. No ``sys.path`` satisfies both forms, so the module was
unimportable by its own callers -- and ``code_quality_dashboard``, which imports
it, unimportable with it. Fixing only the ``NameError`` would have left both
still dead, and the test would have said so.

WHY A CONSTRUCTION TEST AND NOT AN IMPORT TEST. Importing every one of these
modules succeeds today and did so throughout, which is the whole reason nothing
noticed: the failure lives in ``__init__``, one call past where an import check
stops. A test that imports the module proves the file parses.

WHY NOT A COVERAGE OR INTEGRATION TEST EITHER. No execution-based signal reaches
this code, because nothing can execute it. Its duplicate dict key (#15908) and
its four consumers of the shadowed key sat in the same module undisturbed for
the same reason: a defect in unreachable code produces no symptom, so the
ordinary signal that brings someone to look never arrives.

`tools/lint/check_undefined_names.py --audit` is the general guard and would
fail on a sixth instance anywhere in the repo. This file is the specific one:
it fails if any of these five stops constructing for a reason flake8 cannot
see -- a missing argument, a raising dependency, a renamed collaborator.
"""

from __future__ import annotations

import importlib
import pathlib
import sys

import pytest

_SRC = pathlib.Path(__file__).resolve().parent
_BACKEND = _SRC.parents[1]
_REPO_ROOT = _BACKEND.parent

#: ``module stem -> class name``. Every constructor that carried the defect.
#: Not derived from a scan: the point is to name what must work, so deleting a
#: class fails this file rather than shrinking its population silently. The
#: entry for `patch_generator` is `AutomatedFixGenerator`, not the `PatchGenerator`
#: the module name suggests -- a guessed name here would have made the test pass
#: nothing, and it did until this assertion caught it.
ANALYZERS = {
    "architectural_pattern_analyzer": "ArchitecturalPatternAnalyzer",
    "code_quality_dashboard": "CodeQualityDashboard",
    "testing_coverage_analyzer": "TestingCoverageAnalyzer",
    "api_consistency_analyzer": "APIConsistencyAnalyzer",
    "patch_generator": "AutomatedFixGenerator",
}

#: Sibling modules of this package. A failure to import one of THESE is the
#: defect under test, never a reason to skip -- see :func:`_load`.
_SIBLINGS = frozenset(path.stem for path in _SRC.glob("*.py") if not path.stem.endswith("_test"))


def _ensure_importable() -> None:
    """Put the package's own directory on ``sys.path``, which is how it is used.

    Every consumer -- `scripts/analyze_*.py` and `code_quality_dashboard` alike --
    imports these as top-level names, so this reproduces the real import
    environment rather than inventing a package context they never get.
    """
    for entry in (str(_REPO_ROOT), str(_BACKEND), str(_SRC)):
        if entry not in sys.path:
            sys.path.insert(0, entry)


def _load(stem: str):
    """Import one analyzer module, skipping ONLY on a missing third-party package.

    The skip is deliberately narrow. An earlier version of this file loaded the
    modules with ``spec_from_file_location`` and skipped on any ``ImportError``;
    two of the five then skipped on *relative-import* failures from inside the
    package, and the file reported green while testing nothing -- the exact
    shape of vacuous pass this test exists to rule out. So a failure naming one
    of this package's own modules fails here instead of skipping.
    """
    _ensure_importable()
    try:
        return importlib.import_module(stem)
    except ModuleNotFoundError as exc:
        missing = (exc.name or "").split(".")[0]
        if missing in _SIBLINGS or missing == stem:
            pytest.fail(f"{stem} cannot import its own sibling {missing!r}: {exc}")
        pytest.skip(f"{stem} needs third-party package {missing!r}, absent here: {exc}")


@pytest.mark.parametrize("stem,class_name", sorted(ANALYZERS.items()))
def test_the_analyzer_constructs(stem: str, class_name: str) -> None:
    """#15914: constructing must not raise. `NameError` is the recorded failure."""
    module = _load(stem)
    cls = getattr(module, class_name, None)
    assert cls is not None, f"{stem}.py no longer defines {class_name} — this test would prove nothing"
    cls()


def test_the_dashboard_builds_its_two_collaborators() -> None:
    """The interesting case, and the reason this is not five independent checks.

    `CodeQualityDashboard.__init__` constructs `TestingCoverageAnalyzer` and
    `ArchitecturalPatternAnalyzer`, so their failure propagated to whatever
    built the dashboard rather than staying local to the analysis that used
    them. Three entry points construct the dashboard unconditionally:
    `scripts/analyze_code_quality.py`, `scripts/generate_patches.py`, and the
    module's own `main`.
    """
    dashboard = _load("code_quality_dashboard").CodeQualityDashboard()
    assert dashboard.testing_analyzer is not None
    assert dashboard.architecture_analyzer is not None


def test_no_analyzer_still_exposes_the_removed_attribute() -> None:
    """The contrast case: the assignment is gone, not merely made to work.

    Without this, re-adding `self.config = config` alongside a `config` import
    would satisfy every assertion above. Nothing in the repo reads `.config`
    off these objects, so its return would be dead weight reinstated -- the
    same call #6733 and #14634 made on the same defect in two other modules.
    """
    for stem, class_name in sorted(ANALYZERS.items()):
        instance = getattr(_load(stem), class_name)()
        assert not hasattr(instance, "config"), (
            f"{class_name} sets `.config` again. Nothing reads it; #15914 removed "
            "the assignment rather than importing a symbol to satisfy it."
        )
