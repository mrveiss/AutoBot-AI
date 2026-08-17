# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#14236 — the file-size hook's grandfather list must only ever shrink.

``scripts/check_python_file_size.py`` caps Python files at 600 lines and exempts
three that were already over it. The exemption used to be a bare set of names
with a comment claiming the files were "under active decomposition". Nothing
checked the claim, so the three exempted modules grew to 1114, 4068 and 4063
lines — up to 6.8x the limit — while the hook reported them clean. A guard that
cannot lose its exemptions stops guarding without ever going red.

These tests pin the ratchet in **both** directions, because only one of them is
obvious:

* the list may not gain an entry, and no ceiling may be raised (the obvious one),
* an entry whose file has dropped to the limit must be *removed* — a list still
  naming a compliant file exempts nothing while looking authoritative.

The last test is the reach self-check. It runs the hook's own matcher over a
tracked-file enumeration produced by ``git ls-files`` rather than by anything in
the hook, so a matcher that has silently stopped matching cannot pass by
agreeing with a counter that shares its blind spot.
"""

from __future__ import annotations

import importlib.util
import subprocess  # nosec B404  # fixed argv, no shell, no caller input
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = REPO_ROOT / "scripts" / "check_python_file_size.py"

# Frozen snapshot of the exemption as it stood when the ratchet landed (#14236).
# It is deliberately a second copy: a ratchet needs a fixed reference point, and
# a list that is only ever compared against itself can drift anywhere. Lowering
# a ceiling in the hook is fine and needs no edit here. Raising one, or adding a
# fourth file, must fail — so DO NOT "sync" this dict to make a test pass.
RATCHET_BASELINE = {
    "autobot-backend/orchestrator.py": 1114,
    "autobot-backend/chat_workflow/manager.py": 4068,
    "autobot-backend/chat_workflow/tool_handler.py": 4063,
}

# Floor for the tracked-Python enumeration (4958 files at the time of writing).
# An enumeration that returns nothing must not read as "nothing to check".
_TRACKED_PY_FLOOR = 3000


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
    """The audit is clean on the tree as committed, or the numbers are fiction."""
    reached, problems = hook.audit_ceilings()
    assert problems == []
    assert reached == len(hook.KNOWN_LARGE)


# --------------------------------------------------------------------------
# Direction 1 — the list may not grow, and no ceiling may be raised
# --------------------------------------------------------------------------


def test_no_entry_may_be_added(hook):
    added = set(hook.KNOWN_LARGE) - set(RATCHET_BASELINE)
    assert added == set(), (
        f"new grandfathered files {sorted(added)} — the exemption list only "
        "shrinks (#14236). Split the file instead of exempting it."
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


def test_a_shrunk_file_must_lower_its_ceiling(hook):
    """Otherwise the ceiling re-licenses every line that was just removed."""
    for rel, ceiling in hook.KNOWN_LARGE.items():
        message = hook.verdict(rel, ceiling - 1)
        assert message is not None, f"{rel} keeps ceiling {ceiling} after shrinking"
        assert f"Lower the ceiling to {ceiling - 1}" in message


def test_the_audit_surfaces_a_ceiling_violation(hook, tmp_path, monkeypatch):
    """Reaching a file is not the same as reporting on it.

    Today's tree is at its ceilings, so a clean audit run cannot distinguish
    "no violations" from "violations discarded". This stages a real breach.
    """
    monkeypatch.setattr(hook, "repo_root", lambda: tmp_path)
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
