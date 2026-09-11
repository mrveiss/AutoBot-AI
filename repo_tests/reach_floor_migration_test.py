# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A hand-rolled reach-sized floor belongs in `_reach.declare`, not a bare constant (#15928).

#16048 pinned every floor already on `_reach` to its population; it left the
floors that had never adopted the mechanism at all. The 2026-09-10 worksheet on
this issue measured that population directly rather than trusting the original
census: 112 `_MIN_*`/`*_FLOOR`-shaped constants across 63 files, split into two
kinds that do not belong to the same guard.

* **1-99: shrink-guards.** `MIN_DECLARATIONS = 4` in `reach_declarations_test`
  is the archetype and says so in its own comment -- it asks "does this
  population exist at all", not "does the sweep still reach most of it", and
  migrating it to `declare()` would give it a mechanism that implies a coverage
  claim it does not make. `_MIN_ACCUSING_JOBS = 3` and `_MIN_GUARDED_EXITS = 30`
  are the same shape. These are OUT OF SCOPE here by design, at
  `_SHRINK_GUARD_CEILING`.
* **>=100, tree-enumerating: reach floors.** These are what this guard tracks.
  A floor this large binds a real sweep, and #15928's whole argument -- a
  number chosen by feel decays silently -- applies to it exactly as it applied
  to the floors #16048 already pinned.

WHAT THIS DOES NOT COVER, STATED RATHER THAN IMPLIED
------------------------------------------------------
* `repo_tests/guard_reach_meta_test.py`'s `MIN_GUARDS_EXAMINED` and
  `repo_tests/sys_modules_module_scope_restoration_test.py`'s
  `MIN_FILES_PARSED` are syntactically candidates -- both >=100, both in files
  with an enumerator. #16147 decided their exact form directly (a dated,
  re-measured bare constant, not `declare()`) in the same session that built
  this guard; converting them here would reopen that decision rather than
  honour it. Named in `_EXCLUDED_META_FLOORS` so the exclusion is a recorded
  decision, not a silent gap.
* `repo_tests/glob_declared_reads_15900_test.py` is untouched because an open
  PR touches that file (#15928's own collision-control rule) -- grandfathered
  like every other not-yet-migrated floor, not specially exempted.

Migrating one of these means giving its `discover` a `root: Path` parameter (so
`reach_declarations_test` can drive it against an empty directory), registering
it with `_reach.declare`, and re-measuring its population with a throwaway
script rather than carrying the old constant across -- never the last step
alone. `audio_extension_allowlist_test.py` and `env_var_bare_cast_test.py` are
the worked examples; `ansible_inventory_path_exists_test.py`,
`blanket_skips_carry_a_reason_test.py`,
`collected_modules_inert_on_import_test.py` and
`job_name_names_what_it_runs_test.py` are the four this same change converts.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root

from tools.lint._scan_helpers import tracked_paths

_REPO_ROOT = repo_root()

#: Bare `NAME = <int>` floor-shaped constants, syntactically -- matched before
#: any exclusion is applied. Mirrors the classifier from the 2026-09-10
#: worksheet on this issue, re-run rather than trusted: the tree moves.
_FLOOR = re.compile(r"^(_?[A-Z][A-Z0-9_]*(?:MIN|FLOOR|LEAST)[A-Z0-9_]*|_?MIN_[A-Z0-9_]+)\s*=\s*(\d[\d_]*)", re.M)

#: What counts as enumerating the tree. Mirrors `guard_reach_meta_test.py`'s
#: `_ENUMERATOR`, `.glob(` included (#16147).
_ENUMERATOR = re.compile(r"tracked_paths|ls-files|rglob\(|os\.walk\(|\.iterdir\(|\.glob\(")

#: Below this, a constant is a shrink-guard, not a reach floor -- see the
#: module docstring. Migrating those would claim a coverage guarantee they do
#: not make.
_SHRINK_GUARD_CEILING = 100

#: Floors this scan would otherwise catch, excluded for a recorded reason
#: rather than silently -- see the module docstring. Two are governed by
#: #16147's own decision; the third is this file's own `MIN_CANDIDATE_FILES_EXAMINED`
#: below, the same self-referential shape as `guard_reach_meta_test.MIN_GUARDS_EXAMINED`
#: -- a meta-guard's non-vacuity floor over how many FILES it read, not a reach
#: floor over a source tree, and excluding it here is that same ruling applied
#: to this module instead of just described for the other two.
_EXCLUDED_META_FLOORS = frozenset(
    {
        "repo_tests/guard_reach_meta_test.py",
        "repo_tests/sys_modules_module_scope_restoration_test.py",
        "repo_tests/reach_floor_migration_test.py",
    }
)

#: Bound to files EXAMINED, not files found wanting -- same reasoning as
#: `guard_reach_meta_test.MIN_GUARDS_EXAMINED`: a `git ls-files` returning
#: nothing would otherwise pass this module having read zero files. 283
#: tracked `repo_tests/*.py` on 2026-09-11; a shrink-guard in the sense the
#: module docstring names, not a reach floor of its own -- this module watches
#: OTHER files' adoption of the mechanism, it does not enumerate a source tree.
MIN_CANDIDATE_FILES_EXAMINED = 250

#: Hand-rolled reach-sized floors not yet migrated to `_reach.declare`,
#: MEASURED 2026-09-11 (see `_hand_rolled_floors` below, re-run against this
#: tree rather than trusted). SHRINKS ONLY: an entry leaves this set only when
#: its floor becomes a `declare()` call, verified with
#: `git show origin/Dev_new_gui:<path>` naming the `REACH = declare(...)` that
#: replaced it -- never a quiet drop.
GRANDFATHERED = frozenset(
    {
        "repo_tests/ansible_requirements_parity_test.py",
        "repo_tests/bare_default_route_dependency_guard_test.py",
        "repo_tests/collection_coverage_test.py",
        "repo_tests/comment_line_number_citations_test.py",
        "repo_tests/enum_union_guard_severity_literal_shapes_test.py",
        "repo_tests/enum_union_guard_test.py",
        "repo_tests/fixture_fixed_path_teardown_guard.py",
        "repo_tests/frontend_fragmentation_ratchet_test.py",
        "repo_tests/glob_declared_reads_15900_test.py",
        "repo_tests/man_page_indexer_path_resolves_15853_test.py",
        "repo_tests/no_duplicate_dict_keys_test.py",
        "repo_tests/no_repo_relative_phantom_path_test.py",
        "repo_tests/one_git_enumeration_15926_test.py",
        "repo_tests/one_repo_root_spelling_15925_test.py",
        "repo_tests/repo_root_walks_use_git_15955_test.py",
        "repo_tests/route_form_and_json_body_are_not_mixed_test.py",
        "repo_tests/sdk_docs_paths_test.py",
        "repo_tests/severity_literal_shape_guard_test.py",
        "repo_tests/slm_frontend_calls_reach_served_routes_test.py",
        "repo_tests/slm_frontend_publish_contract_test.py",
        "repo_tests/slm_frontend_shell_publish_test.py",
        "repo_tests/store_authority_test.py",
        "repo_tests/stranded_recorder_entries_test.py",
        "repo_tests/test_module_path_anchors_15181_test.py",
        "repo_tests/with_error_handling_single_definition_test.py",
    }
)

#: GRANDFATHERED as last recorded -- a mirrored second copy (same #16147 AC4
#: shape `guard_reach_meta_test.py` uses). Without this, ADDING an entry to
#: GRANDFATHERED silences a new unmigrated floor and no test fails.
_GRANDFATHERED_BASELINE = frozenset(GRANDFATHERED)


def _candidate_floor_names(source: str) -> list[str]:
    """Reach-sized floor constants in *source* not already fed to `declare()`.

    A constant named e.g. `MIN_FILES_SCANNED` that is itself passed as
    `declare(..., floor=MIN_FILES_SCANNED, ...)` is not a hand-rolled floor --
    it is the documented, already-migrated one, exactly the shape
    `env_var_bare_cast_test.py` uses. Excluding by reference rather than by
    file lets an already-migrated file keep OTHER named constants (`growth=`,
    `skips=`) without those constants being misread as further violations.
    """
    names = []
    for name, value in _FLOOR.findall(source):
        if int(value.replace("_", "")) < _SHRINK_GUARD_CEILING:
            continue
        if re.search(rf"floor\s*=\s*{re.escape(name)}\b", source):
            continue
        names.append(name)
    return names


def _tracked_candidate_files() -> list[Path]:
    """Enumerated through the canonical helper (#15926), not a direct git call."""
    return [_REPO_ROOT / rel for rel in tracked_paths(_REPO_ROOT, "repo_tests/*.py")]


def _hand_rolled_floors() -> dict[str, list[str]]:
    """relative path -> [constant names] for every un-migrated reach-sized floor."""
    found: dict[str, list[str]] = {}
    for path in _tracked_candidate_files():
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not _ENUMERATOR.search(source):
            continue
        names = _candidate_floor_names(source)
        if names:
            found[path.relative_to(_REPO_ROOT).as_posix()] = names
    return found


def test_the_detector_finds_a_floor_it_is_shown() -> None:
    """Known positive, against a REAL un-migrated guard.

    A detector that stops recognising this pattern would silently pass every
    hand-rolled floor as if it had already been converted.
    """
    source = (_REPO_ROOT / "repo_tests" / "store_authority_test.py").read_text(encoding="utf-8")
    assert "_MIN_MODULES_PARSED" in _candidate_floor_names(source), "detector no longer finds a known hand-rolled floor"


def test_the_detector_does_not_flag_an_already_migrated_floor() -> None:
    """Contrast pair: a floor already fed to `declare()` must not double-count.

    `env_var_bare_cast_test.py` names its floor `MIN_FILES_SCANNED` and passes
    it to `declare(floor=MIN_FILES_SCANNED, ...)` -- the documented pattern.
    """
    source = (_REPO_ROOT / "repo_tests" / "env_var_bare_cast_test.py").read_text(encoding="utf-8")
    assert "MIN_FILES_SCANNED" not in _candidate_floor_names(source), (
        "detector flagged a constant already passed to declare(floor=...) -- it double-counts "
        "a migrated floor as unmigrated"
    )


def test_the_detector_catches_a_planted_floor() -> None:
    """The planted positive #15928 asks this guard to prove.

    Assembled at runtime so this file does not trip its own sweep -- the exact
    trap `enum_union_guard_test.py`'s `_banned_shape` helper exists to avoid.
    """
    name = "_MIN_" + "PLANTED_FLOOR"
    planted = f'{name} = 500\n\ndef _scan():\n    return tracked_paths(".", "*.py")\n'
    assert _candidate_floor_names(planted) == [name], "detector missed a planted reach-sized floor"


def test_the_detector_ignores_a_shrink_guard_below_the_threshold() -> None:
    """The other contrast pair: population existence checks are not reach floors."""
    name = "_MIN_" + "PLANTED_SHRINK_GUARD"
    planted = f'{name} = 4\n\ndef _scan():\n    return tracked_paths(".", "*.py")\n'
    assert _candidate_floor_names(planted) == [], "detector flagged a shrink-guard below the reach-floor threshold"


def test_the_sweep_examined_enough_files_to_mean_anything() -> None:
    """Non-vacuity, bound to files EXAMINED rather than floors found wanting."""
    examined = _tracked_candidate_files()
    assert len(examined) >= MIN_CANDIDATE_FILES_EXAMINED, (
        f"examined {len(examined)} repo_tests/*.py files, floor is {MIN_CANDIDATE_FILES_EXAMINED}. "
        "A sweep over an empty set reports the same clean result as a fully-migrated tree."
    )


def test_no_new_hand_rolled_floor_remains_unmigrated() -> None:
    """The constraint: every reach-sized floor is either migrated or recorded."""
    found = {rel: names for rel, names in _hand_rolled_floors().items() if rel not in _EXCLUDED_META_FLOORS}
    new = sorted(set(found) - GRANDFATHERED)
    assert not new, (
        "hand-rolled reach-sized floor(s) not migrated to repo_tests._reach.declare and not "
        "recorded in GRANDFATHERED:\n  "
        + "\n  ".join(f"{rel}: {found[rel]}" for rel in new)
        + "\n\nMigrate with declare(...), re-measuring the population with a throwaway script "
        "-- never carry the old constant across (#15928). If an open PR touches the file, add "
        "it to GRANDFATHERED and _GRANDFATHERED_BASELINE instead, naming the collision."
    )


def test_the_grandfathered_list_has_not_gone_stale() -> None:
    """The other direction: an entry that migrated must be removed, not left behind.

    A stale entry silently permits the NEXT file to lose its floor unmigrated,
    the same shape as an allowance the scanner has stopped reporting.
    """
    found = {rel: names for rel, names in _hand_rolled_floors().items() if rel not in _EXCLUDED_META_FLOORS}
    stale = sorted(GRANDFATHERED - set(found))
    assert not stale, (
        "GRANDFATHERED entries that no longer carry a hand-rolled floor -- remove them, the "
        "list only shrinks:\n  " + "\n  ".join(stale)
    )


def _grown(current: frozenset[str]) -> list[str]:
    return sorted(current - _GRANDFATHERED_BASELINE)


def test_the_grandfathered_list_never_grows_silently() -> None:
    """Same #16147 AC4 shape as `guard_reach_meta_test.py`: shrinks only, compared as a SET."""
    grown = _grown(GRANDFATHERED)
    assert not grown, (
        "GRANDFATHERED gained entries missing from _GRANDFATHERED_BASELINE -- a newly "
        "un-migrated floor needs migrating, not exempting silently:\n  " + "\n  ".join(grown)
    )
    unmirrored = sorted(_GRANDFATHERED_BASELINE - GRANDFATHERED)
    assert not unmirrored, (
        "entries removed from GRANDFATHERED but not from _GRANDFATHERED_BASELINE -- mirror the "
        "shrink, or a migrated floor's exemption can quietly return:\n  " + "\n  ".join(unmirrored)
    )


def test_the_growth_check_finds_an_added_entry() -> None:
    """Known positive: the check must see an addition before its silence means anything."""
    assert _grown(GRANDFATHERED | {"repo_tests/planted_unmigrated_floor_test.py"}) == [
        "repo_tests/planted_unmigrated_floor_test.py"
    ]
