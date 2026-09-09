# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A tree-scanning guard must bind a floor to what it examined (#15826).

**A scan of nothing prints the same clean line as a clean tree.** Every guard
here enumerates the repository and asserts something about what it finds; a guard
whose enumeration silently returns empty reports the same green as one that
looked at everything and found no offenders. Nothing distinguishes them, and a
silent wrong answer outlives every loud one.

``repo_tests/_reach.py`` already answers this with :func:`declare`, and
``reach_declarations_test`` already proves declared floors fire — including
against a genuinely empty repository. What did not exist is the thing that makes
adoption non-optional: **a check that fails when a new tree-scanning guard
arrives with no floor at all.** This is that check.

WHAT THIS MEASURES, AND WHAT IT CANNOT SEE
------------------------------------------
Population: tracked ``repo_tests/*_test.py`` whose source contains an
enumerator — ``tracked_paths``, ``git ls-files``, ``rglob(``, ``os.walk(`` or
``.iterdir(``. Stated because a narrow scope is not the defect; an **undeclared**
one is.

Four boundaries a reader should not have to discover:

* **Only ``repo_tests/``.** 301 tracked ``.py`` files repo-wide carry an
  enumerator — 13 in ``scripts/``, 32 in ``tools/``, 8 in ``pipeline-scripts/``,
  32 under ``autobot-infrastructure/``. Those are out of scope here and are
  **not** covered by any equivalent check.
* **Only ``*_test.py``.** Helper modules in this directory (``*_scan.py``,
  ``*_flow.py``, ``*_guard.py``) enumerate on behalf of a caller that may hold
  the floor, so requiring one of the helper would be wrong. Six such modules
  currently have no floor of their own and are invisible to this check.
* **Floor detection is syntactic.** A floor expressed in a way this module's
  AST walk does not recognise reads as absent. That fails toward false
  positives, which is the safe direction: the remedy is a `GRANDFATHERED`
  entry, which is a decision someone writes down.
* **A floor's *value* is not judged here.** ``reach_declarations_test`` proves a
  declared floor is non-zero and cleared by the live tree; an ad-hoc floor of 1
  passes this check while being nearly worthless. Presence, not adequacy.

THE GRANDFATHERED LIST SHRINKS ONLY, AND FAILS IN BOTH DIRECTIONS
-----------------------------------------------------------------
An unrecorded *shrink* is as much a defect as growth: if a guard gains a floor
and nobody removes its entry, the list silently permits the next guard to lose
one. Same shape as an allowance the scanner has stopped reporting.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from repo_tests._paths import repo_root  # noqa: E402

from tools.lint._scan_helpers import tracked_paths  # noqa: E402

#: What counts as enumerating the tree.
_ENUMERATOR = re.compile(r"tracked_paths|ls-files|rglob\(|os\.walk\(|\.iterdir\(")

#: Bound to guards EXAMINED, never to guards found wanting. A `git ls-files`
#: returning nothing would otherwise pass this module having read zero guards --
#: the exact failure it exists to catch, inside itself.
MIN_GUARDS_EXAMINED = 60

#: Tree-scanning `*_test.py` guards with no floor of any kind, frozen so a NEW
#: one fails. May only shrink, and a shrink must be recorded here.
GRANDFATHERED = frozenset(
    {
        "repo_tests/background_task_retention_ratchet_test.py",
        "repo_tests/fixture_fixed_path_teardown_guard_gating_test.py",
        "repo_tests/workflow_planner_deprecation_test.py",
    }
)


def has_floor(source: str) -> bool:
    """Does this source bind an assertion to how much it examined?

    Two accepted forms. ``repo_tests._reach.declare`` is canonical and is what
    ``reach_declarations_test`` can prove. An ad-hoc ``assert len(found) >= N``
    is the older form the migration is moving away from, and counts: this check
    asks whether a floor exists, not whether it is the preferred one.
    """
    if re.search(r"\bdeclare\s*\(", source) and "_reach" in source:
        return True
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return True  # unparsed: not this check's finding to report
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            if isinstance(node.test, ast.Name):
                return True
            for inner in ast.walk(node.test):
                if isinstance(inner, ast.Call) and getattr(inner.func, "id", "") == "len":
                    return True
                if isinstance(inner, ast.Name) and re.match(r"_?(MIN|FLOOR)", inner.id):
                    return True
                if isinstance(inner, ast.Attribute) and re.match(r"_?(MIN|FLOOR)", inner.attr):
                    return True
    return False


def _tracked_guards() -> list[Path]:
    """Enumerated through the canonical helper (#15926), not a direct git call.

    `tracked_paths` lets **git** do the pathspec matching, so the filter and the
    returned paths cannot disagree -- which is what #15510 cost when an
    exclusion was tested against the absolute path.
    """
    root = repo_root()
    return [root / rel for rel in tracked_paths(root, "repo_tests/*_test.py")]


def _scanning_guards() -> dict[str, bool]:
    """Relative path -> whether it binds a floor, for guards that enumerate."""
    root = repo_root()
    found = {}
    for path in _tracked_guards():
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if _ENUMERATOR.search(source):
            found[path.relative_to(root).as_posix()] = has_floor(source)
    return found


def test_the_detector_finds_a_floor_it_is_shown() -> None:
    """Known positive, against a REAL guard rather than a synthetic string.

    `audio_extension_allowlist_test.py` declares `floor=5100` through
    `_reach.declare`. A detector that stops recognising it has silently stopped
    working, and every count below would then read as a catastrophe.
    """
    source = (repo_root() / "repo_tests" / "audio_extension_allowlist_test.py").read_text(encoding="utf-8")
    assert has_floor(source), "detector no longer recognises a declared reach floor"


def test_the_detector_fails_a_real_guard_with_its_floor_removed() -> None:
    """The contrast pair, and the criterion #15826 asks for by name.

    A meta-guard that cannot fail on the thing it exists for IS the defect it is
    checking for. So take a REAL guard, remove its floor, and require the
    detector to call it unfloored.

    The removal is done on the AST and unparsed back, rather than by deleting
    lines. Line-deletion leaves the source unparseable, and `has_floor` treats
    unparseable as floored -- so a text-stripped fixture passes this test for
    the wrong reason, which is precisely the failure mode of the thing being
    built. That is not a hypothetical: it is what the first version did.
    """
    source = (repo_root() / "repo_tests" / "audio_extension_allowlist_test.py").read_text(encoding="utf-8")
    assert has_floor(source), "precondition: the fixture must start with a floor"

    tree = ast.parse(source)

    class _RemoveFloors(ast.NodeTransformer):
        def visit_Assert(self, node: ast.Assert) -> ast.AST | None:
            return None

        def visit_Call(self, node: ast.Call) -> ast.AST:
            self.generic_visit(node)
            if getattr(node.func, "id", "") == "declare" or getattr(node.func, "attr", "") == "declare":
                return ast.Call(func=ast.Name(id="dict", ctx=ast.Load()), args=[], keywords=[])
            return node

    stripped = ast.unparse(ast.fix_missing_locations(_RemoveFloors().visit(tree)))
    ast.parse(stripped)  # the fixture must still be valid Python, or it passes for the wrong reason
    assert not has_floor(stripped), "detector reports a floor in a guard whose floor was removed"


def test_the_sweep_examined_enough_guards_to_mean_anything() -> None:
    """Non-vacuity, bound to guards EXAMINED rather than guards found wanting."""
    guards = _scanning_guards()
    assert len(guards) >= MIN_GUARDS_EXAMINED, (
        f"examined {len(guards)} tree-scanning guards, floor is {MIN_GUARDS_EXAMINED}. "
        "A sweep over an empty set reports the same clean result as a compliant tree."
    )


def test_no_new_tree_scanning_guard_lacks_a_floor() -> None:
    """The constraint."""
    unfloored = {name for name, floored in _scanning_guards().items() if not floored}
    new = sorted(unfloored - GRANDFATHERED)
    assert not new, (
        "tree-scanning guard(s) with no reach floor:\n  "
        + "\n  ".join(new)
        + "\n\nBind one with repo_tests._reach.declare(...), so an empty enumeration "
        "fails instead of reporting the same green as a clean tree."
    )


def test_the_grandfathered_list_has_not_gone_stale() -> None:
    """The other direction, and the one that is normally forgotten.

    An entry that no longer matches means a guard gained a floor and nobody
    recorded it -- and a list carrying dead entries silently permits the next
    guard to lose one. Same shape as an allowance the scanner has stopped
    reporting.
    """
    unfloored = {name for name, floored in _scanning_guards().items() if not floored}
    stale = sorted(GRANDFATHERED - unfloored)
    assert (
        not stale
    ), "GRANDFATHERED entries that now have a floor -- remove them, the list only shrinks:\n  " + "\n  ".join(stale)
