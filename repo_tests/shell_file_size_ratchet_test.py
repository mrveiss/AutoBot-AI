# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The shell size gate's ratchet only turns down (#17353).

Shell had no size gate at all before this. These tests hold the three things
that make the gate real rather than decorative:

1. the two copies of the ceilings agree, so a shrink cannot be un-shrunk;
2. the ratchet's three-way verdict is enforced, including the branch that looks
   wrong -- a file UNDER its ceiling is a failure until the ceiling is lowered;
3. the walk actually reaches the tree, so a clean run means "looked and found
   nothing" rather than "did not look".
"""

from __future__ import annotations

import importlib.util

import pytest
import yaml
from repo_tests._paths import repo_root
from repo_tests.shell_file_size_ratchet_baseline import RATCHET_BASELINE

#: Asks git first, so a worktree resolves to its own tree (#15925). Deriving it
#: from __file__ here would answer confidently and wrongly under a nested
#: checkout, and a guard that resolves the wrong root reports on the wrong tree.
REPO_ROOT = repo_root()
HOOK_PATH = REPO_ROOT / "scripts" / "check_shell_file_size.py"
PRE_COMMIT_CONFIG = REPO_ROOT / ".pre-commit-config.yaml"


def _prefixes_from_exclude(pattern: str) -> set[str]:
    """The literal prefixes a pre-commit `exclude:` regex names.

    Handles the two shapes this repo uses: a bare `^\\.worktrees/` and an
    alternation `^(\\.worktrees/|autobot-infrastructure/)`.
    """
    body = pattern.lstrip("^")
    if body.startswith("(") and body.endswith(")"):
        body = body[1:-1]
    return {alt.replace("\\", "") for alt in body.split("|") if alt}


@pytest.fixture(scope="module")
def hook():
    """Load the hook by path — scripts/ is not an importable package."""
    spec = importlib.util.spec_from_file_location("_check_shell_file_size", HOOK_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_two_copies_of_the_ceilings_agree(hook):
    """A ceiling lowered in one file alone leaves the other licensing the gap."""
    assert hook.KNOWN_LARGE == RATCHET_BASELINE, (
        "KNOWN_LARGE in scripts/check_shell_file_size.py and RATCHET_BASELINE in "
        "repo_tests/shell_file_size_ratchet_baseline.py disagree. Lower a ceiling "
        "in BOTH in the same commit: the gap between them is exactly the lines "
        "just cut, and it is spendable."
    )


def test_no_ceiling_exceeds_its_recorded_baseline(hook):
    """The ratchet turns one way. This is the direction check, stated separately."""
    raised = {
        rel: (ceiling, RATCHET_BASELINE[rel])
        for rel, ceiling in hook.KNOWN_LARGE.items()
        if rel in RATCHET_BASELINE and ceiling > RATCHET_BASELINE[rel]
    }
    assert not raised, f"ceilings raised above their baseline (never allowed): {raised}"


def test_every_grandfathered_file_is_at_its_ceiling(hook):
    """Each entry names a real file whose measured size equals its ceiling."""
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


def test_no_unlisted_shell_file_is_oversized(hook):
    """The whole point: a new oversized .sh must not be able to land."""
    root = hook.repo_root()
    offenders = {}
    for rel in hook.tracked_shell_files(root):
        if hook.normalise(rel) in hook.KNOWN_LARGE:
            continue
        measured = hook.count_lines(root / rel)
        if measured is not None and measured > hook.MAX_LINES:
            offenders[rel] = measured
    assert not offenders, (
        f"shell files over {hook.MAX_LINES} lines with no entry: {offenders}. "
        "Split them — adding a KNOWN_LARGE entry is for what already existed."
    )


def test_the_walk_reaches_the_tree(hook):
    """A walk that stopped covering the tree would pass having asserted nothing."""
    reached, _ = hook.audit_ceilings()
    assert reached >= hook.MIN_TRACKED_SH_FILES, (
        f"the walk reached only {reached} tracked .sh file(s), below the floor of "
        f"{hook.MIN_TRACKED_SH_FILES}. A clean result from a walk this narrow is "
        "'did not look', not 'nothing found'."
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
        if "check_shell_file_size.py" in str(entry.get("entry", ""))
    ]
    assert len(entries) == 1, f"expected exactly one shell-size hook entry, found {len(entries)}"
    assert _prefixes_from_exclude(entries[0].get("exclude", "")) == set(hook.EXCLUDED_PREFIXES), (
        f"the hook's `exclude:` in {PRE_COMMIT_CONFIG.name} and EXCLUDED_PREFIXES in "
        "scripts/check_shell_file_size.py describe different sets. The tree walk and "
        "the staged-file path would then disagree about what is in scope.\n"
        "Checked as SET EQUALITY, not containment: a one-way `prefix in exclude` test "
        "passes when the yaml is WIDENED, because '.worktrees/' is a substring of "
        "'^(\\.worktrees/|autobot-infrastructure/)'. That widening is precisely the "
        "'align it with the Python gate' mistake this file exists to refuse, and it "
        "would have silently stopped pre-commit gating infrastructure shell files."
    )


def test_the_infrastructure_tree_is_in_scope(hook):
    """The deliberate divergence from the Python gate, pinned as a test.

    `check_python_file_size.py` excludes `autobot-infrastructure/`. Inheriting
    that here would drop 6 of the 10 oversized shell files and the gate would
    report green having checked almost nothing. If someone later "aligns" the
    two gates, this fails and says why.
    """
    assert not any("autobot-infrastructure" in prefix for prefix in hook.EXCLUDED_PREFIXES), (
        "autobot-infrastructure/ must stay IN scope for the shell gate: it is where "
        "shell lives, and excluding it makes this gate vacuous. See the module "
        "docstring in scripts/check_shell_file_size.py and ARCHITECTURE_EXCEPTIONS.md."
    )
    root = hook.repo_root()
    infra = [rel for rel in hook.tracked_shell_files(root) if rel.startswith("autobot-infrastructure/")]
    assert infra, "the walk found no autobot-infrastructure/ shell files at all — scope has regressed"


#: install.sh's ceiling, read from the baseline rather than written as a
#: literal. A literal here is how the first version of this test came to assert
#: that 900 lines was ABOVE a ceiling of 1265 -- the parametrisation has to move
#: when the ceiling is lowered, and only a derived value does that.
_CEILING = RATCHET_BASELINE["install.sh"]


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
    message = hook.verdict("install.sh", measured)
    assert message is not None, f"{measured} lines against a ceiling of {_CEILING} must not pass silently"
    assert expect in message, f"expected {expect!r} in: {message}"


def test_a_file_at_its_exact_ceiling_passes(hook):
    """The ratchet freezes a size; it does not demand a shrink on every commit."""
    assert hook.verdict("install.sh", RATCHET_BASELINE["install.sh"]) is None


def test_an_unlisted_compliant_file_passes(hook):
    assert hook.verdict("scripts/some_small_script.sh", 40) is None


def test_an_unlisted_file_at_exactly_max_lines_passes(hook):
    """600 is the limit, not the first violation -- `> MAX_LINES` is strict.

    Pinned because the off-by-one is invisible either way in review: a gate that
    fails at exactly the limit and one that fails one past it read identically.
    """
    assert hook.verdict("scripts/some_script.sh", hook.MAX_LINES) is None
    assert hook.verdict("scripts/some_script.sh", hook.MAX_LINES + 1) is not None


def test_an_unlisted_oversized_file_is_told_to_split(hook):
    message = hook.verdict("scripts/some_new_script.sh", 601)
    assert message is not None
    assert "Split it" in message, f"a new oversized file must be told to split, not to add an entry: {message}"


def test_an_unreadable_file_is_a_violation_not_a_skip(hook):
    """`None` from count_lines means 'never measured', which exit 0 may not claim."""
    message = hook.unmeasured("scripts/gone.sh")
    assert "never measured" in message
    assert "not a passing one" in message
