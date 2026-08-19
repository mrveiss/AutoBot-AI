# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#14236 — the file-size hook's grandfather list must only ever shrink.

``scripts/check_python_file_size.py`` caps Python files at 600 lines and exempts
those that were already over it. The exemption used to be a bare set of names
with a comment claiming the files were "under active decomposition". Nothing
checked the claim, so the first three exempted modules grew to 1114, 4068 and
4063 lines — up to 6.8x the limit — while the hook reported them clean. A guard
that cannot lose its exemptions stops guarding without ever going red.

These tests pin the ratchet in **both** directions, because only one of them is
obvious:

* the list may not gain an entry, and no ceiling may be raised (the obvious one),
* an entry whose file has dropped to the limit must be *removed* — a list still
  naming a compliant file exempts nothing while looking authoritative.

A shrink also has to be locked in, not merely recorded (#14498). ``RATCHET_BASELINE``
below is re-lowered with every shrink and pinned to the files themselves, so the
lines a decomposition removed cannot be spent back inside a stale tolerance.

#14547 found the second half of the same defect: ``audit_ceilings`` re-checked
every entry already in the dict, but had no way to discover a file that had
grown past the limit and was never added — ``reconciler.py`` reached 2000+
lines this way, invisible to every audit run that only ever iterated
``KNOWN_LARGE.items()``. The fix walks the tracked-file tree instead, which is
why ``RATCHET_BASELINE`` below grew from 3 entries to hundreds: the walk found
every other file already over the limit with no entry at all, and grandfathering
all of them at their measured size is what makes turning the walk on possible
without also triaging 505 files in the same change (that is #5060's campaign).

The last test is the reach self-check. It runs the hook's own matcher over a
tracked-file enumeration produced by ``git ls-files`` rather than by anything in
the hook, so a matcher that has silently stopped matching cannot pass by
agreeing with a counter that shares its blind spot.
"""

from __future__ import annotations

import ast
import importlib.util
import logging
import subprocess  # nosec B404  # fixed argv, no shell, no caller input
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = REPO_ROOT / "scripts" / "check_python_file_size.py"
_BASELINE_SCRIPT = REPO_ROOT / "repo_tests" / "python_file_size_ratchet_baseline.py"
_PRE_COMMIT_CONFIG = REPO_ROOT / ".pre-commit-config.yaml"


def _load_ratchet_baseline() -> dict[str, int]:
    """Load RATCHET_BASELINE from its sibling data module, by path.

    Split out (#14547) so this test file stays well under MAX_LINES: 505
    entries inline here would put the guard's own test over the limit it
    enforces on everything else. See that module's docstring for why the
    dict is deliberately a second copy, not read out of the hook.
    """
    spec = importlib.util.spec_from_file_location("python_file_size_ratchet_baseline", _BASELINE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.RATCHET_BASELINE


RATCHET_BASELINE = _load_ratchet_baseline()

# Cardinality ceiling on KNOWN_LARGE itself (#14547 review). The per-file
# ratchet stops any ONE entry from regrowing, but nothing stopped a NEW entry
# appearing in both KNOWN_LARGE and RATCHET_BASELINE together — a two-sided
# addition passes every other test here, which is how this PR added 502
# entries in one change. At 3 entries a 4th was visible in a code review
# diff; at 505 a 506th is not. Lower this by hand whenever KNOWN_LARGE loses
# an entry; never raise it to let a new one in without that being the point
# of the diff.
MAX_KNOWN_LARGE_ENTRIES = 505


# Floor for the tracked-Python enumeration (4958 files at the time of writing).
# An enumeration that returns nothing must not read as "nothing to check".
_TRACKED_PY_FLOOR = 3000


def _count_lines(rel: str) -> int | None:
    """Line count for a repo-relative path, or None when it cannot be read."""
    try:
        with (REPO_ROOT / rel).open(encoding="utf-8") as handle:
            return sum(1 for _ in handle)
    except OSError:
        return None


def _load():
    spec = importlib.util.spec_from_file_location("check_python_file_size", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def hook():
    return _load()


@pytest.fixture(scope="module")
def tracked_py_files() -> list[str]:
    """Every tracked ``*.py`` path, enumerated by git rather than by the hook."""
    out = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", "ls-files", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in out.stdout.splitlines() if line.strip()]


# --------------------------------------------------------------------------
# The exemption is a mapping with a ceiling, not a bare name
# --------------------------------------------------------------------------


def test_every_entry_carries_a_ceiling(hook):
    """A name with no number is the defect this issue exists for."""
    assert hook.KNOWN_LARGE, "the list is empty — drop the ratchet tests with it"
    for rel, ceiling in hook.KNOWN_LARGE.items():
        assert isinstance(ceiling, int), f"{rel} has no recorded ceiling"
        assert ceiling > hook.MAX_LINES, f"{rel}: ceiling {ceiling} is not an exemption"


def test_recorded_ceilings_match_the_files_today(hook):
    """The audit is clean on the tree as committed, or the numbers are fiction.

    ``reached`` now counts the whole tracked-file walk (#14547), not
    ``len(KNOWN_LARGE)`` — the walk is meant to cover the tree, so it is
    checked against the same floor ``run_audit`` uses rather than against the
    grandfather list's own size.
    """
    reached, problems = hook.audit_ceilings()
    assert problems == []
    assert reached >= hook.MIN_TRACKED_PY_FILES


# --------------------------------------------------------------------------
# Discovery — the walk finds files KNOWN_LARGE never named (#14547)
# --------------------------------------------------------------------------


def test_audit_discovers_an_unlisted_oversized_file(hook, tmp_path, monkeypatch):
    """The exact defect #14547 is for: a file over MAX_LINES with no entry.

    ``audit_ceilings`` used to iterate ``KNOWN_LARGE.items()``, so a file like
    this one — over the limit but never added because nobody noticed it grow
    — was invisible to every audit run forever. Walking the tracked-file list
    instead of the dict is what makes this fail.
    """
    monkeypatch.setattr(hook, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(hook, "KNOWN_LARGE", {})
    unlisted = "autobot-slm-backend/services/never_added.py"
    monkeypatch.setattr(hook, "tracked_python_files", lambda root: [unlisted])
    target = tmp_path / unlisted
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x\n" * (hook.MAX_LINES + 50), encoding="utf-8")

    reached, problems = hook.audit_ceilings()
    assert reached == 1
    assert len(problems) == 1
    assert unlisted in problems[0]
    assert hook.run_audit() == 1


def test_audit_is_clean_for_an_unlisted_compliant_file(hook, tmp_path, monkeypatch):
    """A file the walk reaches but that was never over the limit stays silent."""
    monkeypatch.setattr(hook, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(hook, "KNOWN_LARGE", {})
    compliant = "autobot-slm-backend/services/small.py"
    monkeypatch.setattr(hook, "tracked_python_files", lambda root: [compliant])
    target = tmp_path / compliant
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x\n" * 10, encoding="utf-8")

    reached, problems = hook.audit_ceilings()
    assert reached == 1
    assert problems == []


def _pre_commit_python_file_size_excludes() -> set[str]:
    """The ``python-file-size`` hook's own ``exclude:`` prefixes, from the YAML.

    Parsed independently of ``EXCLUDED_PREFIXES`` — building the expectation
    from the same constant the test is meant to check would be true by
    construction and catch nothing.
    """
    config = yaml.safe_load(_PRE_COMMIT_CONFIG.read_text(encoding="utf-8"))
    hooks = [
        hook_cfg
        for repo_cfg in config["repos"]
        for hook_cfg in repo_cfg.get("hooks", [])
        if hook_cfg.get("id") == "python-file-size"
    ]
    assert len(hooks) == 1, f"expected exactly one python-file-size hook, found {len(hooks)}"
    pattern = hooks[0]["exclude"]
    assert pattern.startswith("^(") and pattern.endswith(")"), f"unexpected exclude shape: {pattern}"
    return {prefix.replace("\\.", ".") for prefix in pattern[2:-1].split("|")}


def test_excluded_prefixes_mirror_the_pre_commit_config(hook):
    """The audit's scope matches pre-commit's own exclude (#14547).

    Without this, ``EXCLUDED_PREFIXES`` can drift from
    ``.pre-commit-config.yaml`` silently — three docstrings claiming they
    mirror each other is not a check. Widening or narrowing either without
    the other means the tree walk and the staged-file path stop covering the
    same set of files.
    """
    from_yaml = _pre_commit_python_file_size_excludes()
    assert from_yaml == set(hook.EXCLUDED_PREFIXES), (
        f".pre-commit-config.yaml excludes {sorted(from_yaml)}, "
        f"EXCLUDED_PREFIXES has {sorted(hook.EXCLUDED_PREFIXES)} — keep both in sync."
    )


def test_the_discovery_walk_respects_excluded_prefixes(hook):
    """Behavioural companion to the YAML cross-check above.

    The real walk is exercised too, not just the constant it is built from,
    so a filtering bug inside ``tracked_python_files`` (not just a drifted
    constant) would still be caught.
    """
    root = hook.repo_root()
    tracked = hook.tracked_python_files(root)
    assert tracked, "the real tree walk reached nothing"
    for rel in tracked:
        assert not rel.startswith(hook.EXCLUDED_PREFIXES), rel


# --------------------------------------------------------------------------
# Direction 1 — the list may not grow, and no ceiling may be raised
# --------------------------------------------------------------------------


def test_no_entry_may_be_added(hook):
    added = set(hook.KNOWN_LARGE) - set(RATCHET_BASELINE)
    assert added == set(), (
        f"new grandfathered files {sorted(added)} — the exemption list only "
        "shrinks (#14236). Split the file instead of exempting it."
    )


def test_known_large_entry_count_may_not_grow(hook):
    """Catches a two-sided addition ``test_no_entry_may_be_added`` cannot.

    That test only compares KNOWN_LARGE against RATCHET_BASELINE, so an entry
    added to both together — the actual shape of how this PR added 502 —
    passes it. This pins the count itself against a recorded ceiling that
    only ever moves down.
    """
    count = len(hook.KNOWN_LARGE)
    assert count <= MAX_KNOWN_LARGE_ENTRIES, (
        f"KNOWN_LARGE grew to {count} entries, over the recorded ceiling of "
        f"{MAX_KNOWN_LARGE_ENTRIES} — lower MAX_KNOWN_LARGE_ENTRIES when entries "
        "leave, never raise it to let a new one in."
    )


def test_no_ceiling_may_be_raised(hook):
    raised = {
        rel: (ceiling, RATCHET_BASELINE[rel])
        for rel, ceiling in hook.KNOWN_LARGE.items()
        if rel in RATCHET_BASELINE and ceiling > RATCHET_BASELINE[rel]
    }
    assert raised == {}, f"ceilings raised (now, baseline): {raised}"


def test_growing_past_the_ceiling_fails(hook):
    for rel, ceiling in hook.KNOWN_LARGE.items():
        message = hook.verdict(rel, ceiling + 1)
        assert message is not None, f"{rel} may grow past {ceiling} unchallenged"
        assert str(ceiling) in message


def test_a_file_at_its_ceiling_passes(hook):
    """The exemption still exempts; the ratchet is not a blanket ban."""
    for rel, ceiling in hook.KNOWN_LARGE.items():
        assert hook.verdict(rel, ceiling) is None


# --------------------------------------------------------------------------
# Direction 2 — the list must LOSE entries, which is the half people forget
# --------------------------------------------------------------------------


def test_an_entry_whose_file_is_now_compliant_fails(hook):
    """A list naming a compliant file exempts nothing while looking official."""
    for rel in hook.KNOWN_LARGE:
        message = hook.verdict(rel, hook.MAX_LINES)
        assert message is not None, f"{rel} could sit here compliant and exempt"
        assert "Delete its KNOWN_LARGE entry" in message


def test_the_baseline_is_relowered_by_every_shrink():
    """A shrink recorded only in the hook leaves the cut lines spendable.

    ``test_a_shrunk_file_must_lower_its_ceiling`` makes a shrink lower the
    hook's ceiling; without this, the baseline stays where it was and the gap
    between the two is regrowth every later raise can claim while staying
    "under the baseline" — the defect in #14498, worth 344 lines on
    ``tool_handler.py``. Sizes are counted here rather than read out of the
    hook: a second reference point derived from the thing it checks agrees with
    it by construction.
    """
    stale = {}
    for rel, baseline in RATCHET_BASELINE.items():
        actual = _count_lines(rel)
        assert actual is not None, (
            f"{rel}: the baseline names a file that moved or was deleted — "
            "drop the entry from RATCHET_BASELINE with the KNOWN_LARGE one."
        )
        if baseline > actual:
            stale[rel] = (baseline, actual)
    assert stale == {}, (
        f"baseline above the file it names (baseline, actual): {stale}. Lower "
        "RATCHET_BASELINE to the size achieved — a baseline left above the "
        "file re-licenses every line the shrink removed (#14498)."
    )


def test_a_shrunk_file_must_lower_its_ceiling(hook):
    """Otherwise the ceiling re-licenses every line that was just removed.

    A ceiling of MAX_LINES + 1 shrinking by one lands exactly on MAX_LINES —
    compliant, not merely lower — so that boundary gets the "delete the
    entry" message instead of "lower the ceiling"; every other entry keeps
    the original expectation.
    """
    for rel, ceiling in hook.KNOWN_LARGE.items():
        shrunk = ceiling - 1
        message = hook.verdict(rel, shrunk)
        assert message is not None, f"{rel} keeps ceiling {ceiling} after shrinking"
        if shrunk <= hook.MAX_LINES:
            assert "Delete its KNOWN_LARGE entry" in message
        else:
            assert f"Lower the ceiling to {shrunk}" in message


def test_the_audit_surfaces_a_ceiling_violation(hook, tmp_path, monkeypatch):
    """Reaching a file is not the same as reporting on it.

    Today's tree is at its ceilings, so a clean audit run cannot distinguish
    "no violations" from "violations discarded". This stages a real breach.
    """
    monkeypatch.setattr(hook, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(hook, "tracked_python_files", lambda root: list(hook.KNOWN_LARGE))
    for rel, ceiling in hook.KNOWN_LARGE.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x\n" * (ceiling + 5), encoding="utf-8")

    reached, problems = hook.audit_ceilings()
    assert reached == len(hook.KNOWN_LARGE)
    assert len(problems) == len(hook.KNOWN_LARGE)
    assert all("over its recorded ceiling" in problem for problem in problems)
    assert hook.run_audit() == 1


def test_run_audit_fails_when_the_scan_reached_nothing(hook, monkeypatch):
    """A scan of nothing must never read as a clean scan."""
    monkeypatch.setattr(hook, "audit_ceilings", lambda: (0, []))
    assert hook.run_audit() == 1


def test_the_audit_reports_a_vanished_entry(hook, tmp_path, monkeypatch):
    """A renamed or deleted file must be a hard error, not a silent no-op."""
    monkeypatch.setattr(hook, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(hook, "tracked_python_files", lambda root: [])
    reached, problems = hook.audit_ceilings()
    assert reached == 0
    assert len(problems) == len(hook.KNOWN_LARGE)
    assert all("moved or was deleted" in problem for problem in problems)
    assert hook.run_audit() == 1


# --------------------------------------------------------------------------
# The ungrandfathered majority still gets the plain 600-line rule
# --------------------------------------------------------------------------


def test_unlisted_files_keep_the_plain_limit(hook):
    unlisted = "autobot-backend/api/definitely_not_grandfathered.py"
    assert hook.verdict(unlisted, hook.MAX_LINES) is None
    assert hook.verdict(unlisted, hook.MAX_LINES + 1) == (
        f"{unlisted}: {hook.MAX_LINES + 1} lines (max {hook.MAX_LINES})"
    )


def test_windows_separators_still_match_an_entry(hook):
    for rel, ceiling in hook.KNOWN_LARGE.items():
        assert hook.verdict(rel.replace("/", "\\"), ceiling + 1) is not None


# --------------------------------------------------------------------------
# The findings have to reach a human (#1082)
#
# Writing findings to stdout is banned repo-wide (this comment says so without
# quoting the call, which would put the banned pattern in a file whose job is to
# forbid it). The hook emits through stdlib logging instead. A
# silent conversion is worse than the print it replaced: findings routed to
# logger.debug on a default configuration vanish, and the guard then passes and
# reports nothing while looking like it ran. These pin the output path.
# --------------------------------------------------------------------------


def _oversize(tmp_path: Path, lines: int) -> Path:
    target = tmp_path / "too_big.py"
    target.write_text("x\n" * lines, encoding="utf-8")
    return target


def test_a_violation_is_reported_to_the_developer(hook, tmp_path, caplog):
    """The whole point of the hook: run it on a bad file, see the finding."""
    target = _oversize(tmp_path, hook.MAX_LINES + 7)
    with caplog.at_level(logging.DEBUG, logger=hook.logger.name):
        assert hook.main([str(target)]) == 1
    emitted = "\n".join(record.getMessage() for record in caplog.records)
    assert str(target) in emitted
    assert f"{hook.MAX_LINES + 7} lines (max {hook.MAX_LINES})" in emitted


def test_findings_are_emitted_above_the_lastresort_threshold(hook, tmp_path, caplog):
    """Visible even if nothing ever configured logging.

    ``logging.lastResort`` prints WARNING and above when no handler is found.
    A finding below that level would be swallowed by a bare invocation.
    """
    target = _oversize(tmp_path, hook.MAX_LINES + 1)
    with caplog.at_level(logging.DEBUG, logger=hook.logger.name):
        hook.main([str(target)])
    levels = [record.levelno for record in caplog.records]
    assert levels and min(levels) >= logging.WARNING


def test_audit_problems_are_reported_to_the_developer(hook, tmp_path, caplog, monkeypatch):
    monkeypatch.setattr(hook, "audit_ceilings", lambda: (0, ["ceiling drifted"]))
    with caplog.at_level(logging.DEBUG, logger=hook.logger.name):
        assert hook.run_audit() == 1
    emitted = "\n".join(record.getMessage() for record in caplog.records)
    assert "ceiling drifted" in emitted
    assert min(record.levelno for record in caplog.records) >= logging.WARNING


def test_configure_logging_makes_the_clean_run_visible(hook):
    """The 'all live' line is INFO, so it needs a handler to exist at all."""
    hook.configure_logging()
    assert hook.logger.handlers, "no handler — INFO output would be discarded"
    assert hook.logger.isEnabledFor(logging.INFO)


def test_the_hook_has_no_stdout_calls_left(hook):
    """#1082 — every finding leaves through the logger, none through stdout.

    Structural, not textual: the banned name is assembled by implicit string
    concatenation so this fixture cannot trip the very lint it is checking, and
    the self-guard below fails if that assembly is ever fat-fingered into a
    needle that matches nothing.
    """
    banned = "pri" "nt"
    assert len(banned) == 5 and banned.endswith("nt"), "needle assembly broke"
    tree = ast.parse(_SCRIPT.read_text(encoding="utf-8"))
    calls = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == banned
    ]
    assert calls == [], f"stdout calls remain at lines {calls}"


# --------------------------------------------------------------------------
# Reach — did the matcher actually reach anything?
# --------------------------------------------------------------------------


def test_enumeration_reaches_the_repo(tracked_py_files):
    """Guards the reach check below: an empty list would agree with anything."""
    assert len(tracked_py_files) >= _TRACKED_PY_FLOOR


def test_matcher_reaches_every_entry_over_a_tracked_enumeration(hook, tracked_py_files):
    """Run the hook's matcher over paths git produced, not paths the hook knows.

    Counting the entries the hook thinks it has would share the matcher's blind
    spot exactly: if a future rewrite changes the key form, both the matcher and
    a dict-derived counter stop matching and agree that all is well. Driving the
    matcher from an independent enumeration cannot agree that way.
    """
    # A compliant line count is silent for every ordinary file and loud for a
    # grandfathered one ("delete the entry"), so the probe identifies membership
    # without depending on any ceiling value.
    matched = [
        rel for rel in tracked_py_files if hook.verdict(rel, hook.MAX_LINES) is not None
    ]
    assert sorted(matched) == sorted(hook.KNOWN_LARGE), (
        f"matcher reached {len(matched)} of {len(hook.KNOWN_LARGE)} entries over "
        f"{len(tracked_py_files)} tracked files: {sorted(matched)}"
    )
