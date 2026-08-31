# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Exactly one ``with_error_handling`` may exist in the tracked tree (#14191).

Before this fix, ``autobot-backend/error_handler.py`` and
``autobot-backend/utils/error_boundaries/decorators.py`` each defined a
top-level function named ``with_error_handling`` with disjoint parameter sets
and opposite behaviour on ``HTTPException``. Nothing distinguished them at an
import site — ``grep -rn "def with_error_handling"`` returned two hits with no
indication which one any given ``from ... import with_error_handling`` call
resolved to, and getting it wrong produced a materially wrong analysis in PR
#14186.

The guard walks the AST (never a source-text grep for the string
``with_error_handling``, which would also match comments, docstrings, and the
now-renamed ``with_default_on_error``) looking for ``FunctionDef``/
``AsyncFunctionDef`` nodes whose name is exactly ``with_error_handling``. Only
the canonical decorator in ``decorators.py`` may define it; a second
definition anywhere else — under any name that happens to collide — fails
this test with the offending file:line, whether or not it is ever imported.

WHAT "THE TRACKED TREE" MEANS HERE (#15202 item 1)
--------------------------------------------------
It used to mean ``autobot-backend/`` alone, while this docstring and
``test_exactly_one_definition_exists_in_the_tracked_tree`` both said *tracked
tree*. A fork landing in ``autobot_shared/``, ``autobot-slm-backend/``,
``scripts/`` or ``tools/`` — all of which import from the backend and all of
which are places a decorator plausibly gets copied to — was outside the scan
while inside the claim. The scan was widened rather than the claim narrowed:
the name collision #14191 is about is a *repository* property, and a fork one
directory outside ``autobot-backend/`` is exactly as ambiguous at an import
site as one inside it.

"Tracked" is now literal. ``_tracked_sources`` walks from ``_REPO`` and then
keeps only paths ``git ls-files`` reports, for two measured reasons:

* The walk alone is checkout-dependent. In the mandated
  ``<main-tree>/.worktrees/<branch>/`` layout the main checkout carries 2,911
  untracked ``.py`` files under ``.claude/worktrees/`` and a fresh clone
  carries none, so the population — and worse, the offender set — would depend
  on which machine ran the guard. Someone's half-finished scratch fork of this
  very decorator is not a defect in the tracked tree.
* ``git ls-files`` alone would make most of ``_SKIP_PARTS`` unreachable and
  would give up the directory pruning, which is load-bearing: the main
  checkout holds 416,065 ``.py`` files under ``.worktrees/``.

Measured: 3,099 sources, identical in the main checkout and in a fresh
worktree.

A DIRECTORY NAMED `tests/` MAY HOLD NON-TEST FILES (#15258)
--------------------------------------------------------------
Pruning `tests` out of `_SKIP_PARTS` used to drop every file inside a
directory of that name, test or not -- so a fork of `with_error_handling`
placed in a non-test helper living there (`autobot-backend/llc/tests/_e2e_harness.py`, `autobot-infrastructure/shared/tests/mock_llm_interface.py`)
would never reach the scan. DECISION: narrow the exclusion to file name, not
directory name. `_production_sources` already drops any file matching
`test_*.py` / `*_test.py` regardless of which directory it sits in (see the
filename check below); removing `tests` from `_SKIP_PARTS` and relying on
that per-file check instead means a non-test helper under `tests/` is
scanned exactly like one anywhere else, while an actual test file inside it
stays excluded. Measured population moved from 3,099 to 3,199 sources with
the directory no longer pruned wholesale.

Swept the tree for other guards with the same directory-name blind spot
(AC4): one other, ``repo_tests/workflow_planner_deprecation_test.py``, also
prunes a literal ``"tests"`` entry from its own ``_SKIP_PARTS``. Left as-is
here -- a different file, tracked separately as #15350.

UNPARSEABLE IS AN UNKNOWN, NOT AN ABSENCE (#15202 item 3)
----------------------------------------------------------
``_defines_target`` used to catch ``SyntaxError``/``UnicodeDecodeError`` and
return ``[]``, so a file too broken to parse contributed no definitions and the
one-definition assertion passed straight over it. A half-committed fork is
precisely the kind of file that does not parse, which made the swallow blindest
where the guard most needed to see. #14975 settled the precedent the other way
(a file the size gate could not read became a violation, not a pass) and PR
#15249 applied it to a sibling repo guard.

So ``_defines_target`` raises, ``_scan_for_definitions`` records the file in a
second list, and ``test_no_tracked_source_is_unreadable_by_this_guard`` fails on
it. ``_KNOWN_UNPARSEABLE`` is the down-only hatch and is **deliberately empty** —
measured at 0 unreadable of 3,099 — so failing loudly costs nothing today, and
an entry there would be an admission that a tracked source does not parse,
which is its own defect.

THE POPULATION FLOOR (#15202 item 4)
-------------------------------------
The floor exists so a filter that has started eating the tree fails as a defect
in this file instead of reporting a clean codebase. It was ``> 100`` against
2,308 real files — 23x slack, which only catches total collapse, while #15121
was a filter eating the tree and a *partial* version of it would have sailed
through. ``_SOURCE_FLOOR`` now sits just under the measured population, and
``test_the_floor_has_not_decayed_into_slack`` caps how far the population may
outgrow it so the slack cannot silently return.
"""

from __future__ import annotations

import ast
import os
import subprocess
from pathlib import Path
from typing import Dict, FrozenSet, List, Set, Tuple

import pytest

_REPO = Path(__file__).resolve().parents[1]
_BACKEND = _REPO / "autobot-backend"

_TARGET_NAME = "with_error_handling"

# Directory names skipped, matched against parts of the path RELATIVE to the
# scan root -- never a substring of the absolute path (#15121). This repo's
# whole workflow runs from `<main-tree>/.worktrees/<branch>/` checkouts, so
# `"/.worktrees/" in path.as_posix()` is true of the repo root itself and skips
# every file in the tree; the guard then inspects nothing and fails its own
# non-vacuity assertion. Same form as `first_party_imports_resolve_test.py:33`
# and `shell_lib_sources_resolve_test.py:58`.
#
# #15202 item 2: `.worktrees` was an unreachable entry while the scan root was
# `autobot-backend/` -- no path relative to that root can carry it. Scanning
# from `_REPO` (as #15121's AC1 specified) makes it reachable and load-bearing:
# the main checkout keeps 85 worktrees holding 416,065 `.py` files directly
# under `<repo>/.worktrees/`, each a full copy of this tree with its own
# `decorators.py`. `test_a_worktrees_directory_under_the_scan_root_is_pruned`
# pins that, so the entry can never go back to doing nothing unnoticed.
#
# `tests` is deliberately NOT here (#15258): pruning it by directory name
# dropped non-test helpers living inside `tests/` right along with the actual
# tests. The filename check in `_production_sources` below excludes test files
# wherever they live, which is the narrower rule this guard actually needs.
_SKIP_PARTS = {"node_modules", ".worktrees", "__pycache__", "venv", ".venv"}

# The one file allowed to define it. Anything else defining a function or
# async function with this exact name is the fork this test exists to catch.
_CANONICAL_DEFINER = (_BACKEND / "utils" / "error_boundaries" / "decorators.py").resolve()

# Trees the widened scan must keep reaching. Narrowing the scan back to
# `autobot-backend/` -- the #15202 item 1 regression -- empties these without
# moving the floor much, so the floor alone would not catch it.
_TREES_THAT_MUST_BE_SCANNED = ("autobot_shared", "autobot-slm-backend", "scripts", "tools")

#: Population floor for the tracked scan. Measured at 3,199 sources after
#: #15258 narrowed the `tests` exclusion to file name (was 3,099 with the
#: directory pruned wholesale); the floor sits 149 below that, same margin as
#: before. For scale, the largest number of `.py` files deleted by any single
#: merge in the last 300 first-parent commits is 3, so ordinary churn has
#: ~50x headroom, while losing any one of the four trees above (217, 175, 55,
#: 22 files) or any comparable subtree fails. RATCHET: raise it when the
#: population genuinely grows; lower it only with a stated reason.
_SOURCE_FLOOR = 3050

#: How far the population may outgrow the floor before the floor is stale. The
#: floor started at 100 against 2,308 files -- 23x slack -- which is how it
#: stopped meaning anything. At 1.5x it can never decay that far again, while
#: still allowing 43% growth before anyone has to touch it.
_MAX_FLOOR_SLACK = 1.5

#: Tracked sources that do not parse, and are therefore inspected blind. Empty
#: on purpose: measured at 0 of 3,099. Down-only -- an entry here is a statement
#: that a tracked source is syntactically broken, which is a defect to fix, not
#: to waive. Same discipline as `KNOWN_UNPARSEABLE` in
#: `test_module_path_anchors_15181_test.py` (PR #15249).
_KNOWN_UNPARSEABLE: FrozenSet[str] = frozenset()


def _production_sources(root: Path = _BACKEND) -> List[Path]:
    """Non-test .py files under `root`, excluding `_SKIP_PARTS` directories.

    `root` is a parameter so the exclusion logic can be exercised against a
    fixture tree that itself lives under `.worktrees/` -- the arrangement this
    scan silently erased before #15121.

    Pruning `dirnames` in place is the same rule as testing the parts of the
    path relative to `root`, applied one level earlier: a directory whose name
    is in `_SKIP_PARTS` is never descended into. Names *above* `root` are never
    looked at, which is the prefix-invariance #15140 asked for, and the pruning
    is what keeps a scan rooted at `_REPO` affordable in a checkout that holds
    hundreds of thousands of worktree copies.
    """
    out: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in _SKIP_PARTS]
        for name in filenames:
            if not name.endswith(".py"):
                continue
            if name.endswith("_test.py") or name.startswith("test_"):
                continue
            out.append(Path(dirpath) / name)
    return out


def _tracked_paths(root: Path = _REPO) -> Set[Path]:
    """Absolute paths of every file git tracks under `root`."""
    listing = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return {root / relative for relative in listing.split("\0") if relative}


def _tracked_sources() -> List[Path]:
    """Every tracked, non-test .py file in the repository -- the guard's real scan.

    See "WHAT THE TRACKED TREE MEANS HERE" above for why both halves are here.
    """
    tracked = _tracked_paths()
    return [path for path in _production_sources(_REPO) if path in tracked]


def _defines_target(path: Path) -> List[int]:
    """Line numbers where `path` defines a (async) function named _TARGET_NAME.

    Raises rather than reporting an absence when the file cannot be read or
    parsed (#15202 item 3). Callers that sweep many files use
    `_scan_for_definitions`, which records the failure instead of dropping it.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))

    lines = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == _TARGET_NAME:
            lines.append(node.lineno)
    return lines


def _scan_for_definitions(sources: List[Path]) -> Tuple[Dict[Path, List[int]], List[Tuple[Path, str]]]:
    """(definers, unreadable). A source that cannot be parsed lands in the second list."""
    definers: Dict[Path, List[int]] = {}
    unreadable: List[Tuple[Path, str]] = []
    for path in sources:
        try:
            hits = _defines_target(path)
        except (SyntaxError, UnicodeDecodeError, ValueError, OSError) as failure:
            unreadable.append((path, f"{type(failure).__name__}: {failure}"))
            continue
        if hits:
            definers[path.resolve()] = hits
    return definers, unreadable


@pytest.fixture(scope="module")
def tracked_sources() -> List[Path]:
    return _tracked_sources()


@pytest.fixture(scope="module")
def scan_result(tracked_sources) -> Tuple[Dict[Path, List[int]], List[Tuple[Path, str]]]:
    return _scan_for_definitions(tracked_sources)


def test_the_scan_sees_the_tree_it_is_pointed_at(tracked_sources):
    """A guard that skipped every file would report clean, not report a skip.

    Split out from the assertion below so the two failures read differently:
    "the scan found nothing to inspect" is a defect in this file, while
    "with_error_handling vanished" is a defect in the code under guard. Before
    #15121 the first masqueraded as the second in every worktree checkout.
    """
    assert len(tracked_sources) >= _SOURCE_FLOOR, (
        f"only {len(tracked_sources)} tracked sources survived the exclusion filter, "
        f"below the recorded floor of {_SOURCE_FLOOR} — the filter is eating the tree, "
        "so every assertion below is vacuous"
    )
    assert _CANONICAL_DEFINER in {path.resolve() for path in tracked_sources}


def test_the_floor_has_not_decayed_into_slack(tracked_sources):
    """#15202 item 4: a floor far below the population stops catching anything.

    The floor is only proportional while someone raises it. This caps the drift
    at `_MAX_FLOOR_SLACK` so it cannot quietly return to the 23x it had.
    """
    ceiling = int(_SOURCE_FLOOR * _MAX_FLOOR_SLACK)
    assert len(tracked_sources) <= ceiling, (
        f"the tree has grown to {len(tracked_sources)} sources against a floor of "
        f"{_SOURCE_FLOOR} — raise `_SOURCE_FLOOR` to just under the new population. "
        "This is not a defect in the codebase; it is the floor going stale."
    )


@pytest.mark.parametrize("tree", _TREES_THAT_MUST_BE_SCANNED)
def test_the_scan_reaches_every_tree_the_docstring_claims(tracked_sources, tree):
    """#15202 item 1: the scan must cover what its name and docstring promise.

    Pinned per tree rather than by count: narrowing the scan back to
    `autobot-backend/` loses 787 of 3,099 sources, which the floor would catch,
    but losing `scripts/` alone (22 files) it would not.
    """
    scanned = {path.relative_to(_REPO).parts[0] for path in tracked_sources}
    assert tree in scanned, (
        f"no source under {tree}/ reached the scan — the guard is back to inspecting "
        "one tree while its name and docstring claim the tracked tree (#15202)"
    )


def _write_fixture_tree(root: Path) -> Path:
    """One canonical definer plus genuinely excluded files; returns the definer.

    Same fixture shape as `scripts/check_ansible_file_references_test.py:40-45`
    and `repo_tests/lint/canonical/test_context.py:76-78`.

    `tests/` holds a test-named file (excluded by filename, #15258) rather than
    the generic `vendored.py` the other excluded directories get: since #15258
    narrowed the `tests` exclusion to file name, a non-test file placed there
    would no longer be pruned, and this fixture needs to keep demonstrating
    what IS still excluded.
    """
    (root / "utils" / "error_boundaries").mkdir(parents=True)
    definer = root / "utils" / "error_boundaries" / "decorators.py"
    definer.write_text(f"def {_TARGET_NAME}():\n    pass\n", encoding="utf-8")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "vendored.py").write_text("x = 1\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_something.py").write_text("x = 1\n", encoding="utf-8")
    return definer


def _relative_scan(root: Path) -> Set[str]:
    """`_production_sources` as repo-relative posix strings, so two trees compare."""
    return {path.relative_to(root).as_posix() for path in _production_sources(root)}


def test_a_checkout_under_worktrees_is_still_scanned(tmp_path):
    """#15121: the filter must key on parts relative to the scan root.

    The fixture reproduces the mandated layout exactly — the scan root itself
    sits under `.worktrees/<branch>/`. Matching a substring of the absolute path
    skips every file here; matching relative parts finds the definer.
    """
    root = tmp_path / ".worktrees" / "issue-9999" / "autobot-backend"
    definer = _write_fixture_tree(root)

    scanned = _production_sources(root)

    assert definer in scanned, (
        "a scan rooted under .worktrees/ skipped its own tree — the exclusion "
        "is matching the absolute path instead of parts relative to the root"
    )
    assert {path.name for path in scanned} == {"decorators.py"}
    assert _defines_target(definer) == [1]


def test_a_worktrees_directory_under_the_scan_root_is_pruned(tmp_path):
    """#15202 item 2: the `.worktrees` entry must be able to match something.

    Rooted at the repository (as #15121's AC1 specified) the entry is reachable
    and load-bearing — the main checkout keeps whole copies of this tree under
    `<repo>/.worktrees/`, each with its own `with_error_handling`. Fixture-based
    rather than layout-dependent, so the entry stays pinned in a checkout that
    happens to have no worktrees of its own.
    """
    root = tmp_path / "checkout"
    definer = _write_fixture_tree(root / "autobot-backend")
    fork = root / ".worktrees" / "issue-9999" / "autobot-backend" / "utils" / "error_boundaries"
    fork.mkdir(parents=True)
    (fork / "decorators.py").write_text(f"def {_TARGET_NAME}():\n    pass\n", encoding="utf-8")

    scanned = _production_sources(root)

    assert scanned == [definer], (
        "a copy of the tree under .worktrees/ was scanned as if it were the tree — "
        "every worktree in the mandated layout would report itself as a fork"
    )


def test_a_non_test_helper_inside_a_tests_directory_is_still_scanned(tmp_path):
    """#15258 contrast mutation: a fork placed in a non-test file under `tests/`.

    Before this fix, pruning `tests` by directory name dropped everything under
    it, test or not — a real instance of exactly this shape sits at
    `autobot-backend/llc/tests/_e2e_harness.py` and
    `autobot-infrastructure/shared/tests/mock_llm_interface.py`. Narrowing the
    exclusion to file name means a fork placed in a helper like those is caught,
    while an actual test file in the same directory stays excluded.
    """
    root = tmp_path / "autobot-backend"
    (root / "utils" / "error_boundaries").mkdir(parents=True)
    (root / "utils" / "error_boundaries" / "decorators.py").write_text(
        f"def {_TARGET_NAME}():\n    pass\n", encoding="utf-8"
    )
    harness_dir = root / "llc" / "tests"
    harness_dir.mkdir(parents=True)
    fork = harness_dir / "_e2e_harness.py"
    fork.write_text(f"def {_TARGET_NAME}():\n    pass\n", encoding="utf-8")
    real_test = harness_dir / "test_something.py"
    real_test.write_text(f"def {_TARGET_NAME}():\n    pass\n", encoding="utf-8")

    scanned = _production_sources(root)

    assert fork in scanned, (
        "a non-test helper inside a tests/ directory was pruned by directory "
        "name alone — a with_error_handling fork placed there would go unseen (#15258)"
    )
    assert real_test not in scanned, "an actual test file inside tests/ must stay excluded by its filename"


@pytest.mark.parametrize("ancestor", sorted(_SKIP_PARTS))
def test_an_excluded_name_above_the_scan_root_changes_nothing(tmp_path, ancestor):
    """#15140: the filter must be prefix-invariant for *every* skipped name.

    The test above pins `.worktrees` alone, so reintroducing the absolute form
    for just one of the other names — `if "/tests/" in path.as_posix()` — keeps
    this file green while emptying the tree for any checkout under a directory
    of that name. Measured: that partial regression left the suite 5-green.
    Comparing the same tree at two prefixes pins the invariant instead of one
    case of it.
    """
    under = tmp_path / "under" / ancestor / "issue-9999" / "autobot-backend"
    plain = tmp_path / "plain" / "checkout" / "autobot-backend"
    _write_fixture_tree(under)
    _write_fixture_tree(plain)

    # Non-vacuity first: if the neutral tree scanned empty the comparison below
    # would pass by finding nothing at either prefix.
    assert _relative_scan(plain) == {"utils/error_boundaries/decorators.py"}
    assert _relative_scan(under) == _relative_scan(plain), (
        f"a scan root nested under a directory named {ancestor!r} enumerated a "
        "different set than the same tree elsewhere — the exclusion is matching "
        "the absolute path instead of parts relative to the root"
    )


def test_exactly_one_definition_exists_in_the_tracked_tree(scan_result):
    definers, _unreadable = scan_result

    assert definers, f"{_TARGET_NAME} vanished from its canonical module — this guard expects it to exist"

    offenders = {path: lines for path, lines in definers.items() if path != _CANONICAL_DEFINER}
    assert not offenders, (
        f"A second `{_TARGET_NAME}` definition reappeared outside "
        f"{_CANONICAL_DEFINER.relative_to(_REPO)}: {offenders}. "
        "Give it a distinct, descriptive name instead (see error_handler.py's "
        "with_default_on_error for the pattern) — #14191 exists because a "
        "shared name with different behaviour produced a wrong analysis in PR "
        "#14186."
    )


def test_no_tracked_source_is_unreadable_by_this_guard(scan_result):
    """#15202 item 3: an unparseable file is an unknown, not an absence."""
    _definers, unreadable = scan_result
    offenders = [
        f"{path.relative_to(_REPO)}  ->  {reason}"
        for path, reason in unreadable
        if str(path.relative_to(_REPO)) not in _KNOWN_UNPARSEABLE
    ]
    assert not offenders, (
        "These tracked sources could not be parsed, so this guard saw NONE of their "
        f"definitions and scored them clean without reading them. A half-committed "
        f"fork of {_TARGET_NAME} is exactly the kind of file that does not parse — "
        "fix it, or add it to _KNOWN_UNPARSEABLE with a reason:\n  " + "\n  ".join(offenders)
    )


def test_the_unparseable_hatch_is_down_only_and_still_earned(scan_result):
    _definers, unreadable = scan_result
    still_unreadable = {str(path.relative_to(_REPO)) for path, _reason in unreadable}
    stale = _KNOWN_UNPARSEABLE - still_unreadable
    assert not stale, f"these sources parse again and must leave _KNOWN_UNPARSEABLE: {sorted(stale)}"
    assert not _KNOWN_UNPARSEABLE, (
        "_KNOWN_UNPARSEABLE was empty when this guard was written and is down-only. "
        "A tracked source that does not parse is a defect to fix, not to list."
    )


def test_an_unparseable_source_is_recorded_rather_than_scored_clean(tmp_path):
    """The swallow this replaced would have reported this fixture as definition-free.

    The fixture carries a real definition *and* a syntax error, so it cannot
    reach the `unreadable` list for want of anything to find: strip the broken
    line and the same text yields exactly one definition.
    """
    broken = tmp_path / "fork.py"
    broken.write_text(f"def {_TARGET_NAME}():\n    pass\ndef (\n", encoding="utf-8")
    intact = tmp_path / "intact.py"
    intact.write_text(f"def {_TARGET_NAME}():\n    pass\n", encoding="utf-8")

    with pytest.raises(SyntaxError):
        _defines_target(broken)
    assert _defines_target(intact) == [1]

    definers, unreadable = _scan_for_definitions([broken, intact])
    assert list(definers) == [intact.resolve()]
    assert [path for path, _reason in unreadable] == [broken]
    assert unreadable[0][1].startswith("SyntaxError")


def test_the_canonical_definer_defines_it_exactly_once():
    """A guard this narrow is only as good as its own precision: catch the
    canonical file itself acquiring a second, shadowing definition."""
    hits = _defines_target(_CANONICAL_DEFINER)
    assert len(hits) == 1, f"expected exactly one {_TARGET_NAME} in {_CANONICAL_DEFINER}, found at lines {hits}"


def test_the_renamed_sibling_no_longer_shares_the_name():
    """error_handler.py's decorator must not silently regain the collision."""
    renamed_module = _BACKEND / "error_handler.py"
    assert _defines_target(renamed_module) == [], (
        f"{renamed_module.relative_to(_REPO)} defines {_TARGET_NAME} again — "
        "it was renamed to with_default_on_error in #14191 specifically to "
        "end the name collision; keep it renamed."
    )

    tree = ast.parse(renamed_module.read_text(encoding="utf-8"))
    defined = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert "with_default_on_error" in defined, (
        f"{renamed_module.relative_to(_REPO)} lost with_default_on_error — "
        "never-delete: it must be renamed, not removed."
    )
