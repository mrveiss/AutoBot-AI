# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A job that approves its own push's parked runs must not be cancelled by them (#16360).

``auto-fix-generated-types.yml`` pushes regenerated types to the PR branch; every
run at the new head is parked (the push is github-actions[bot]'s), and its own
``approve-parked-runs`` job releases them. The released Auto-fix run joined the
same concurrency group -- ``${{ github.workflow }}-${{ github.head_ref }}`` with
``cancel-in-progress: true`` -- and cancelled the run the approver lives in. On
#16351 the released run started at 15:23:12Z and the approver was cancelled at
15:23:15Z; whether everything was approved first is a race.

The fix separates group MEMBERSHIP for runs the bot's own push caused, so it holds
whichever run's ``cancel-in-progress`` GitHub applies (undocumented). A cancelled
approver cannot report from inside its sweep, so the job also hands an
interrupted sweep to the watchdog.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from repo_tests._paths import repo_root

yaml = pytest.importorskip("yaml", reason="PyYAML needed to parse the workflows")

WORKFLOW_DIR = repo_root() / ".github" / "workflows"
APPROVER_COMMAND = "ci_dispatch_watchdog.py --check dispatch"
BOT_DISCRIMINATOR = "github.actor == 'github-actions[bot]'"
AUTOFIX = WORKFLOW_DIR / "auto-fix-generated-types.yml"


def _triggers(doc: dict) -> set[str]:
    # PyYAML reads the bare key `on:` as the boolean True.
    raw = doc.get("on", doc.get(True, {})) or {}
    if isinstance(raw, str):
        return {raw}
    return set(raw)


def _approver_workflows() -> list[Path]:
    return [
        path for path in sorted(WORKFLOW_DIR.glob("*.y*ml")) if APPROVER_COMMAND in path.read_text(encoding="utf-8")
    ]


def _cancels_its_group_on_pull_request(doc: dict) -> bool:
    """A pull_request-triggered workflow whose group cancels the run already in progress."""
    if "pull_request" not in _triggers(doc):
        return False
    concurrency = doc.get("concurrency")
    if not isinstance(concurrency, dict):
        return False  # the string form never cancels an in-progress run
    return concurrency.get("cancel-in-progress") not in (False, None, "false")


def _separates_bot_caused_runs(doc: dict) -> bool:
    concurrency = doc.get("concurrency")
    group = concurrency.get("group", "") if isinstance(concurrency, dict) else str(concurrency or "")
    return BOT_DISCRIMINATOR in group


def test_the_scan_finds_the_approver_this_issue_is_about():
    names = {path.name for path in _approver_workflows()}
    assert "auto-fix-generated-types.yml" in names, f"approver scan found only {sorted(names)}"


def test_the_predicate_flags_the_pre_fix_shape():
    """Known positive: the exact group #16351 hit must read as unsafe."""
    pre_fix = {
        "on": {"pull_request": {}},
        "concurrency": {"group": "${{ github.workflow }}-${{ github.head_ref }}", "cancel-in-progress": True},
    }
    assert _cancels_its_group_on_pull_request(pre_fix)
    assert not _separates_bot_caused_runs(pre_fix)


@pytest.mark.parametrize("path", _approver_workflows(), ids=lambda path: path.name)
def test_an_approver_that_cancels_in_its_group_puts_bot_caused_runs_in_their_own(path: Path):
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if _cancels_its_group_on_pull_request(doc):
        assert _separates_bot_caused_runs(doc), (
            f"{path.name} approves parked runs from a pull_request run whose concurrency group cancels the run in "
            f"progress. A run its own push parks would, once approved, join that group and cancel the approver "
            f"(#16360). Put runs caused by the bot in a group of their own: include `{BOT_DISCRIMINATOR}` in "
            f"`concurrency.group`."
        )


def test_the_watchdog_never_cancels_a_sweep_in_flight():
    """Why only auto-fix needs the discriminator: the watchdog's own group never cancels."""
    doc = yaml.safe_load((WORKFLOW_DIR / "ci-dispatch-watchdog.yml").read_text(encoding="utf-8"))
    assert doc["concurrency"]["cancel-in-progress"] is False


def _approver_steps() -> list[dict]:
    doc = yaml.safe_load(AUTOFIX.read_text(encoding="utf-8"))
    return doc["jobs"]["approve-parked-runs"]["steps"]


def test_an_interrupted_approval_is_handed_to_the_watchdog():
    """A cancelled approver cannot report from inside the sweep; a cancelled() step still runs."""
    handoff = [step for step in _approver_steps() if str(step.get("if", "")).strip() == "cancelled()"]
    assert len(handoff) == 1, "approve-parked-runs needs exactly one `if: cancelled()` step (#16360)"
    assert "gh workflow run ci-dispatch-watchdog.yml" in handoff[0]["run"]
    assert "::error" in handoff[0]["run"]


def test_the_approval_result_reaches_the_job_summary_and_keeps_its_exit_code():
    steps = _approver_steps()
    sweep = next(step for step in steps if APPROVER_COMMAND in str(step.get("run", "")))
    assert "set -o pipefail" in sweep["run"] and "| tee" in sweep["run"], "the tee must not discard the exit code"
    summary = [step for step in steps if str(step.get("if", "")).strip() == "always()"]
    assert summary and "GITHUB_STEP_SUMMARY" in summary[0]["run"]
