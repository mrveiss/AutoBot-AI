# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A floor that drifts into its bottom band is caught on main, not on an unrelated PR (#22110).

Two halves, one mechanism (the reach registry's own ``staleness`` rule, never a second one):

* B -- main's own CI run enforces it. ``ci.yml`` sets ``AUTOBOT_REACH_AUDIT=1`` on a push to main
  and on a merge group, so the merge that crossed the line is the one that goes red.
* A -- ``repin-reach-floors.yml`` runs ``scripts/repin_reach_floors.py`` on main and opens, or
  updates, ONE pull request.

The detector is proved by contrast: a floor in the band is refused, one just above it is not.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from repo_tests._paths import repo_root
from repo_tests._reach import REACH_AUDIT_ENV, Reach, ReachFloorError

_ROOT = Path("/nonexistent-root-never-read")
_WORKFLOWS = repo_root() / ".github" / "workflows"
# growth=200 -> the band is the bottom 20 of the window (ceil(200 * 0.10)).
_POPULATION, _GROWTH = 1000, 200
_BAND_EDGE = _POPULATION - _GROWTH + 20  # the lowest floor OUTSIDE the band


def _reach(floor: int) -> Reach:
    return Reach(
        name=f"drift-{floor}",
        discover=lambda _root: list(range(_POPULATION)),
        pinned_floor=floor,
        what="synthetic items",
        growth=_GROWTH,
    )


def test_a_floor_in_the_bottom_band_is_flagged_and_one_just_above_is_not() -> None:
    assert "bottom 20 of its window" in (_reach(_BAND_EDGE - 1).staleness(_ROOT) or "")
    assert _reach(_BAND_EDGE).staleness(_ROOT) is None


def test_on_main_the_flagged_floor_fails_and_the_one_above_it_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(REACH_AUDIT_ENV, "1")
    with pytest.raises(ReachFloorError):
        _reach(_BAND_EDGE - 1).verify_floor(_ROOT)
    _reach(_BAND_EDGE).verify_floor(_ROOT)


def test_off_main_the_same_floor_only_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    """The unrelated PR stays green: no audit, so the flagged floor warns instead of failing."""
    monkeypatch.delenv(REACH_AUDIT_ENV, raising=False)
    with pytest.warns(UserWarning):
        _reach(_BAND_EDGE - 1).verify_floor(_ROOT)


def _audit_step() -> dict:
    steps = yaml.safe_load((_WORKFLOWS / "ci.yml").read_text(encoding="utf-8"))["jobs"]["python-shard"]["steps"]
    found = [s for s in steps if f"{REACH_AUDIT_ENV}=1" in str(s.get("run", ""))]
    assert len(found) == 1, "exactly one step sets the reach audit"
    return found[0]


def test_ci_enforces_the_audit_on_a_push_to_main_and_a_merge_group() -> None:
    condition = str(_audit_step()["if"])
    assert "github.event_name == 'push' && github.ref == 'refs/heads/main'" in condition
    assert "github.event_name == 'merge_group'" in condition
    assert "startsWith(github.head_ref, 'train-')" in condition


def _repin() -> dict:
    return yaml.safe_load((_WORKFLOWS / "repin-reach-floors.yml").read_text(encoding="utf-8"))


def test_the_repin_workflow_runs_on_main_and_on_a_schedule() -> None:
    triggers = _repin()[True]  # YAML parses the bare key `on` as the boolean True
    assert triggers["push"]["branches"] == ["main"]
    assert triggers["schedule"] and "workflow_dispatch" in triggers


def test_the_repin_workflow_opens_one_pr_and_updates_it_in_place() -> None:
    text = (_WORKFLOWS / "repin-reach-floors.yml").read_text(encoding="utf-8")
    assert "scripts/repin_reach_floors.py" in text
    assert 'gh pr list --head "$BRANCH" --state open' in text, "gh pr view matches closed PRs too (#20057)"
    assert "gh pr view" not in text
    assert "secrets.AUTOBOT_PUSH_TOKEN" in text and "secrets.GITHUB_TOKEN" not in text
    assert "--force-with-lease" in text
    assert "git push" in text and "origin main" not in text
