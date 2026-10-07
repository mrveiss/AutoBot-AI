# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The frontend size gate's ratchet only turns down, and it measures what it claims (#17885).

`.ts` and `.vue` had no length measurement of any kind before this gate. These
tests hold the four things that make it real rather than decorative:

1. the two copies of the ceilings agree, so a shrink cannot be un-shrunk
   (equality itself is owned by ``ceiling_record_parity_17872_test.py``, which
   asserts it both ways for all three gates; the direction check is here);
2. the ratchet's three-way verdict is enforced, including the branch that looks
   wrong -- a file UNDER its ceiling is a failure until the ceiling is lowered;
3. the walk actually reaches the tree, so a clean run means "looked and found
   nothing" rather than "did not look";
4. **the gate measures its SUBJECT, not a spelling.** A reach floor proves the
   walk ran; it says nothing about whether the walk covered the thing the
   gate's name claims. ``test_a_long_frontend_file_outside_the_two_suffixes_is_not_measured``
   is the control for that: it holds a file with the property the name
   describes (a long frontend source file) while lacking the spelling the code
   checks (``.ts``/``.vue``), and it PASSES the gate -- which is the honest
   statement that this gate measures two suffixes, not "the frontend".
"""

from __future__ import annotations

import importlib.util

import pytest
import yaml
from repo_tests._paths import repo_root
from repo_tests.frontend_file_size_ratchet_baseline import RATCHET_BASELINE

from tools.lint._scan_helpers import tracked_paths

#: Asks git first, so a worktree resolves to its own tree (#15925). Deriving it
#: from __file__ here would answer confidently and wrongly under a nested
#: checkout, and a guard that resolves the wrong root reports on the wrong tree.
REPO_ROOT = repo_root()
HOOK_PATH = REPO_ROOT / "scripts" / "check_frontend_file_size.py"
PRE_COMMIT_CONFIG = REPO_ROOT / ".pre-commit-config.yaml"

#: Frontend source files this gate does NOT measure, over MAX_LINES, recorded
#: so the gap is a stated finding rather than an unstated one. The gate covers
#: ``.ts`` and ``.vue``; the frontends also carry 15 ``.js`` files under
#: ``src/``, and this is the only one over the limit today. Widening the gate
#: to ``*.js`` repo-wide is a different change with a different exclusion
#: problem -- tracked at #17936, not done silently here.
#:
#: This mapping is the instrument for the gap. Without it "the gate found
#: nothing outside .ts/.vue" and "the gate never looked outside .ts/.vue" are
#: the same observation (MEASUREMENT_DISCIPLINE.md).
_UNCOVERED_OVERSIZED: dict[str, int] = {
    "autobot-frontend/src/config/AppConfig.js": 616,
}

#: Suffixes the uncovered-population sweep enumerates. Everything a frontend
#: tree can hold that is source and is not already gated by this hook or by
#: ``check_python_file_size.py``.
_UNCOVERED_SUFFIXES = (".js", ".mjs", ".cjs", ".jsx", ".tsx", ".mts", ".cts")

_FRONTEND_TREES = ("autobot-frontend/", "autobot-slm-frontend/")


def _prefixes_from_exclude(pattern: str) -> set[str]:
    """The literal prefixes a pre-commit `exclude:` regex names.

    Handles the two shapes this repo uses: a bare `^\\.worktrees/` and an
    alternation `^(\\.worktrees/|autobot-frontend/src/types/generated/)`.
    """
    body = pattern.lstrip("^")
    if body.startswith("(") and body.endswith(")"):
        body = body[1:-1]
    return {alt.replace("\\", "") for alt in body.split("|") if alt}


@pytest.fixture(scope="module")
def hook():
    """Load the hook by path — scripts/ is not an importable package."""
    spec = importlib.util.spec_from_file_location("_check_frontend_file_size", HOOK_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_no_ceiling_exceeds_its_recorded_baseline(hook):
    """The ratchet turns one way. This is the direction check, stated separately."""
    raised = {
        rel: (ceiling, RATCHET_BASELINE[rel])
        for rel, ceiling in hook.KNOWN_LARGE.items()
        if rel in RATCHET_BASELINE and ceiling > RATCHET_BASELINE[rel]
    }
    assert not raised, f"ceilings raised above their baseline (never allowed): {raised}"


def test_every_grandfathered_file_is_at_its_ceiling(hook):
    """Each entry names a real file whose measured size equals its ceiling.

    This is the tree-anchored direction: it is what stops both records drifting
    together away from the files they describe.
    """
    wrong: dict[str, str] = {}
    for rel, ceiling in hook.KNOWN_LARGE.items():
        path = REPO_ROOT / rel
        if not path.is_file():
            wrong[rel] = "no such file — remove the entry from both copies"
            continue
        measured = hook.count_lines(path)
        if measured is None:
            wrong[rel] = "could not be read, so it was never measured"
        elif measured != ceiling:
            wrong[rel] = f"measured {measured}, ceiling {ceiling}"
    assert not wrong, f"grandfathered entries out of step with the files: {wrong}"


def test_no_unlisted_frontend_file_is_oversized(hook):
    """The whole point: a new oversized .ts/.vue must not be able to land."""
    root = hook.repo_root()
    offenders = {}
    for rel in hook.tracked_frontend_files(root):
        if hook.normalise(rel) in hook.KNOWN_LARGE:
            continue
        measured = hook.count_lines(root / rel)
        if measured is not None and measured > hook.MAX_LINES:
            offenders[rel] = measured
    assert not offenders, (
        f"frontend files over {hook.MAX_LINES} lines with no entry: {offenders}. "
        "Split them — adding a KNOWN_LARGE entry is for what already existed."
    )


def test_the_walk_reaches_the_tree(hook):
    """A walk that stopped covering the tree would pass having asserted nothing."""
    reached, _ = hook.audit_ceilings()
    assert reached >= hook.MIN_TRACKED_FRONTEND_FILES, (
        f"the walk reached only {reached} tracked .ts/.vue file(s), below the floor of "
        f"{hook.MIN_TRACKED_FRONTEND_FILES}. A clean result from a walk this narrow is "
        "'did not look', not 'nothing found'."
    )


def test_the_reach_floor_fires_when_the_walk_finds_nothing(hook, monkeypatch, caplog):
    """The floor's own control: prove it REPORTS, rather than trusting it exists.

    A floor nobody has ever seen fire is an untested branch, and this one is the
    difference between "found nothing" and "did not look". Driven through
    ``run_audit`` rather than through ``_reach_breach_problem`` directly, because
    the branch under test is the decision to emit it, not the sentence.
    """
    monkeypatch.setattr(hook, "tracked_frontend_files", lambda root: [])
    with caplog.at_level("ERROR"):
        assert hook.run_audit() == 1, "a walk that reached nothing must not report success"
    assert "stopped covering the tree" in caplog.text
    assert str(hook.MIN_TRACKED_FRONTEND_FILES) in caplog.text


def test_both_measured_suffixes_are_actually_reached(hook):
    """A `.ts`-only walk would clear the floor while missing 152 of 184 offenders.

    The reach floor is a count, so it cannot tell a walk covering both suffixes
    from one covering the larger suffix twice. `.vue` is where frontend length
    actually accumulates, so losing it is the failure that would look fine.
    """
    reached = hook.tracked_frontend_files(hook.repo_root())
    by_suffix = {suffix: sum(1 for rel in reached if rel.endswith(suffix)) for suffix in (".ts", ".vue")}
    assert all(by_suffix.values()), f"a measured suffix vanished from the walk: {by_suffix}"
    recorded = {suffix: sum(1 for rel in hook.KNOWN_LARGE if rel.endswith(suffix)) for suffix in (".ts", ".vue")}
    assert all(recorded.values()), f"a measured suffix has no grandfathered entry at all: {recorded}"


def test_a_long_frontend_file_outside_the_two_suffixes_is_not_measured(hook):
    """THE SUBJECT CONTROL. It passes, and that is the finding, not the pass.

    The file below has the property this gate's name describes — a hand-written
    frontend source file over the limit — while lacking the spelling the code
    checks. The gate says nothing about it. So this gate measures `.ts` and
    `.vue`, not "frontend file length", and the docstring and #17936 say so
    rather than leaving a reader to infer coverage from a green run.

    If this ever starts FAILING, the gate was widened and this test should be
    deleted along with ``_UNCOVERED_OVERSIZED``.
    """
    for rel, size in _UNCOVERED_OVERSIZED.items():
        assert (REPO_ROOT / rel).is_file(), f"{rel} no longer exists — update _UNCOVERED_OVERSIZED"
        assert hook.count_lines(REPO_ROOT / rel) == size, f"{rel} changed size — re-record it in _UNCOVERED_OVERSIZED"
        assert size > hook.MAX_LINES, f"{rel} is no longer oversized — drop it from _UNCOVERED_OVERSIZED"
        assert rel not in hook.tracked_frontend_files(
            hook.repo_root()
        ), f"{rel} is now inside the walk — the gate was widened, so delete this control"


def test_the_uncovered_oversized_population_has_not_grown(hook):
    """The gap is measured, not assumed. A new oversized unmeasured file is visible.

    Without this, the sentence "the gate covers .ts and .vue" carries no
    information about how much it is leaving on the floor, and the floor can
    grow for ever without anything noticing.
    """
    root = hook.repo_root()
    found = {}
    # #15926: one enumeration helper, not a private `git ls-files`. The helper
    # also scrubs the git env and roots the pathspec, which this call spelled
    # out for itself -- a second spelling of one question is how the two drift.
    for rel in tracked_paths(root, *[f"{tree}**" for tree in _FRONTEND_TREES]):
        if not rel.endswith(_UNCOVERED_SUFFIXES) or rel.startswith(hook.EXCLUDED_PREFIXES):
            continue
        measured = hook.count_lines(root / rel)
        if measured is not None and measured > hook.MAX_LINES:
            found[rel] = measured
    assert found == _UNCOVERED_OVERSIZED, (
        "the frontend source files this gate does NOT measure have changed.\n"
        f"  recorded: {_UNCOVERED_OVERSIZED}\n"
        f"  found:    {found}\n"
        "This set may only shrink. A new entry means an unmeasured frontend file crossed "
        "the limit — split it, or widen the gate (#17936). Re-record only when one is fixed."
    )


def test_excluded_prefixes_mirror_the_pre_commit_config(hook):
    """The audit's scope and the staged-file scope must be the same set.

    Parsed from the YAML independently rather than compared to a copy of the
    string, so the two cannot drift without this failing.
    """
    config = yaml.safe_load(PRE_COMMIT_CONFIG.read_text(encoding="utf-8"))
    entries = [
        entry
        for repo in config.get("repos", [])
        for entry in repo.get("hooks", [])
        if "check_frontend_file_size.py" in str(entry.get("entry", ""))
    ]
    assert len(entries) == 1, f"expected exactly one frontend-size hook entry, found {len(entries)}"
    assert _prefixes_from_exclude(entries[0].get("exclude", "")) == set(hook.EXCLUDED_PREFIXES), (
        f"the hook's `exclude:` in {PRE_COMMIT_CONFIG.name} and EXCLUDED_PREFIXES in "
        "scripts/check_frontend_file_size.py describe different sets. The tree walk and "
        "the staged-file path would then disagree about what is in scope.\n"
        "Checked as SET EQUALITY, not containment: a one-way `prefix in exclude` test "
        "passes when the yaml is WIDENED, because '.worktrees/' is a substring of any "
        "alternation containing it — and a widened exclusion is how a gate quietly stops "
        "gating."
    )


def test_the_generated_clients_are_excluded_by_a_recorded_prefix(hook):
    """Generated output leaves by PREFIX, never by a special case in the walk.

    Both ``src/types/generated/api.ts`` files are OpenAPI-derived (178894 and
    26584 lines). They must be out of scope, they must be out of scope by a
    named prefix, and they must not appear in the ceilings — an entry for a
    generated file is a ceiling nobody can ever lower.
    """
    generated = [prefix for prefix in hook.EXCLUDED_PREFIXES if prefix.endswith("src/types/generated/")]
    assert len(generated) == 2, f"both generated client trees must be named as prefixes: {hook.EXCLUDED_PREFIXES}"
    for prefix in generated:
        assert (REPO_ROOT / prefix).is_dir(), f"{prefix} names no directory — a stranded exclusion gates nothing"
    walked = hook.tracked_frontend_files(hook.repo_root())
    assert not [rel for rel in walked if rel.startswith(tuple(generated))], "a generated client reached the walk"
    assert not [
        rel for rel in hook.KNOWN_LARGE if rel.startswith(tuple(generated))
    ], "a generated file carries a ceiling — remove it, the exclusion is the mechanism"


#: The largest ceiling, read from the baseline rather than written as a literal.
#: A literal is how a parametrisation comes to assert that 900 is above a ceiling
#: of 1265 -- the inputs have to move when the ceiling is lowered, and only a
#: derived value does that.
_SUBJECT = max(RATCHET_BASELINE, key=lambda rel: RATCHET_BASELINE[rel])
_CEILING = RATCHET_BASELINE[_SUBJECT]


@pytest.mark.parametrize(
    ("measured", "expect"),
    [
        (_CEILING + 1, "may not grow"),
        (_CEILING - 1, "Lower the ceiling"),
        (500, "within the"),
    ],
)
def test_the_three_way_verdict(hook, measured, expect):
    """Over, under and compliant are all failures, each with its own instruction."""
    message = hook.verdict(_SUBJECT, measured)
    assert message is not None, f"{measured} lines against a ceiling of {_CEILING} must not pass silently"
    assert expect in message, f"expected {expect!r} in: {message}"


def test_a_file_at_its_exact_ceiling_passes(hook):
    """The ratchet freezes a size; it does not demand a shrink on every commit."""
    assert hook.verdict(_SUBJECT, _CEILING) is None


def test_an_unlisted_compliant_file_passes(hook):
    assert hook.verdict("autobot-frontend/src/components/Tiny.vue", 40) is None


def test_an_unlisted_file_at_exactly_max_lines_passes(hook):
    """600 is the limit, not the first violation -- `> MAX_LINES` is strict.

    Pinned because the off-by-one is invisible either way in review: a gate that
    fails at exactly the limit and one that fails one past it read identically.
    """
    assert hook.verdict("autobot-frontend/src/x.ts", hook.MAX_LINES) is None
    assert hook.verdict("autobot-frontend/src/x.ts", hook.MAX_LINES + 1) is not None


def test_an_unlisted_oversized_file_is_told_to_split(hook):
    message = hook.verdict("autobot-frontend/src/views/BrandNew.vue", 601)
    assert message is not None
    assert "Split it" in message, f"a new oversized file must be told to split, not to add an entry: {message}"


def test_an_unreadable_file_is_a_violation_not_a_skip(hook):
    """`None` from count_lines means 'never measured', which exit 0 may not claim."""
    message = hook.unmeasured("autobot-frontend/src/gone.vue")
    assert "never measured" in message
    assert "not a passing one" in message


def test_the_commit_path_reports_an_unreadable_staged_file(hook, tmp_path, monkeypatch, caplog):
    """End to end on the path that blocks a push, not just on the message builder."""
    monkeypatch.setattr(hook, "repo_root", lambda: tmp_path)
    assert hook.check_paths(["autobot-frontend/src/never_written.vue"]) == 1


#: The sum of every recorded ceiling, which only ever moves DOWN.
#:
#: WHY A THIRD NUMBER (#17970). The two records are compared against each other
#: by `test_no_ceiling_exceeds_its_recorded_baseline`, so that check fires when
#: ONE anchor is raised and is blind when BOTH are. Moving both is the
#: documented way to grow a grandfathered file here --
#: `autobot-backend/api/schemas_system.py` went 4306 -> 4346 across five merged
#: commits exactly that way -- so "no ceiling may be raised" was a claim the
#: Python ratchet made and did not enforce.
#:
#: A mirrored pair detects a transcription error between the copies. It cannot
#: detect movement OF the pair, because both sides of the comparison move
#: together. Direction needs a figure that does not move with the edit, which
#: is what this is.
#:
#: The repo reached this conclusion once already and applied it to the other
#: half: `MAX_KNOWN_LARGE_ENTRIES` exists because a two-sided *addition* passes
#: the record-to-record check. This is the same argument one step over, for
#: ceiling VALUES rather than entry COUNT.
#:
#: Re-pin DOWN when files shrink. Raising it is the thing being prevented, so a
#: raise needs a recorded reason in the pull request, not a quiet edit.
#:
#: WHAT THIS NUMBER CANNOT SEE (#17989). It is a SUM, so it only reports the
#: NET. A ceiling raised here and an unrelated file shrinking there cancel, and
#: a total that moved DOWN reads as a clean shrink while individual ceilings
#: rose. That happened on this very re-pin: 184571 -> 184531 is -40 net, and
#: underneath it seven ceilings ROSE (+45) while two FELL (-85). Both tests
#: below pass on the net and see none of the seven. The argument that produced
#: this constant -- a comparison cannot police what moves with it -- applies to
#: the sum one step further out, so the per-entry direction check still has no
#: fixed reference. Do not read a falling total as "no ceiling was raised".
MAX_CEILING_TOTAL = 184521  # #18065: ChatMessages.vue 2122 -> 2119, ChatController.ts 1158 -> 1156


def test_the_ceiling_total_only_shrinks(hook):
    """A two-sided raise is invisible to the record-to-record check; this sees it.

    `test_no_ceiling_exceeds_its_recorded_baseline` compares KNOWN_LARGE against
    RATCHET_BASELINE. Raise an entry in both and they agree again, so it passes
    while a grandfathered file just grew. The total is pinned against a constant
    that does not move with either record, so the raise shows up here.
    """
    total = sum(hook.KNOWN_LARGE.values())

    assert total <= MAX_CEILING_TOTAL, (
        f"recorded ceilings now total {total}, over the pinned {MAX_CEILING_TOTAL} "
        f"(+{total - MAX_CEILING_TOTAL}). A grandfathered file grew. Raising both "
        "records agrees with itself and passes every other check here (#17970) -- "
        "this is the one that sees it. Split the file, or state in the PR why the "
        "ceiling must rise and move this number with it."
    )


def test_the_ceiling_total_is_not_stale(hook):
    """The contrast. Without it, the pin above could drift far above the real sum
    and silently license growth up to the gap -- a floor that permits anything is
    not a floor. Mirrors how `MAX_KNOWN_LARGE_ENTRIES` is kept honest.
    """
    total = sum(hook.KNOWN_LARGE.values())

    assert total == MAX_CEILING_TOTAL, (
        f"ceilings total {total} but the pin says {MAX_CEILING_TOTAL}. Files shrank "
        "and the pin was not lowered, which re-licenses the lines just cut. Set "
        f"MAX_CEILING_TOTAL = {total}."
    )
