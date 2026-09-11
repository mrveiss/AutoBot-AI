# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#16272 — the watchdog releases parked runs on the release-sync PR into main, and on no other PR there.

Without a push token, ``sync-main-to-dev.yml`` pushes ``release-sync-main`` and opens
its PR as the bot, so the runs park, and the watchdog only ever swept PRs into
``Dev_new_gui``. It now also sweeps that one PR, through its one approval path
(``collect_heads`` -> ``sweep_parked_runs`` -> ``_approve_head``) and under the same
rules: this repository, parked, triggered by the branch-update bot.

This lives in its own file rather than ``ci_dispatch_watchdog_test.py``, which sits
at its frozen size ceiling.
"""

from __future__ import annotations

import importlib.util
import inspect
from typing import Any, Dict, List

import pytest
import yaml
from repo_tests._paths import repo_root

_REPO_ROOT = repo_root()
_WATCHDOG = _REPO_ROOT / "pipeline-scripts" / "ci_dispatch_watchdog.py"
_SELECTOR = _REPO_ROOT / "pipeline-scripts" / "release_sync_pull.py"
_SYNC_WORKFLOW = _REPO_ROOT / ".github/workflows/sync-main-to-dev.yml"

REPO = "mrveiss/AutoBot-AI"
FORK = "someone/AutoBot-AI"
SWEEP = {"max_approvals": 50, "poll_attempts": 1, "poll_interval_seconds": 0}


def _load(name: str, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def wd():
    return _load("ci_dispatch_watchdog", _WATCHDOG)


@pytest.fixture(scope="module")
def sel():
    return _load("release_sync_pull", _SELECTOR)


def _pull(number: int, head: str, base: str = "main", repo: str = REPO) -> Dict[str, Any]:
    return {
        "number": number,
        "head": {"ref": head, "sha": f"{number:040x}", "repo": {"full_name": repo}},
        "base": {"ref": base},
        "updated_at": None,
        "html_url": "",
    }


def _parked(wd, number: int, repo: str = REPO) -> Dict[str, Any]:
    return {
        "id": number,
        "name": f"checks of #{number}",
        "status": "completed",
        "conclusion": "action_required",
        "head_repository": {"full_name": repo},
        "triggering_actor": {"login": wd.UPDATE_BOT_LOGIN},
    }


class _FakeApi:
    """Lists PRs per base, serves one parked bot run per head, and records every approval."""

    def __init__(self, wd, pulls: List[Dict[str, Any]]):
        self.repository = REPO
        self._pulls = pulls
        self.runs = {p["head"]["sha"]: [_parked(wd, p["number"], p["head"]["repo"]["full_name"])] for p in pulls}
        self.listed: List[str] = []
        self.approved: List[int] = []

    def open_pull_requests(self, base: str) -> List[Dict[str, Any]]:
        self.listed.append(base)
        return [pull for pull in self._pulls if pull["base"]["ref"] == base]

    def runs_for_sha(self, sha: str) -> List[Dict[str, Any]]:
        return self.runs[sha]

    def approve_run(self, run_id: int):
        self.approved.append(run_id)
        return 201, ""


def _main_prs() -> List[Dict[str, Any]]:
    return [
        _pull(1, "release-sync-main"),  # the release-sync PR
        _pull(2, "issue-7-x"),  # another PR into main, from this repository
        _pull(3, "release-sync-main", repo=FORK),  # a fork's branch of the same name
    ]


def _sweep(wd, sel, api: _FakeApi, swept_base: str = "Dev_new_gui") -> List[int]:
    """The composition check_dispatch performs, followed by its approval sweep."""
    pulls = api.open_pull_requests(swept_base)
    heads = wd.collect_heads(pulls + sel.release_sync_pulls(api, swept_base), api.repository)
    wd.sweep_parked_runs(api, heads, SWEEP, False)
    return sorted(api.approved)


def test_the_release_sync_pr_is_approved_and_no_other_pr_into_main(wd, sel):
    api = _FakeApi(wd, [*_main_prs(), _pull(4, "issue-8-y", base="Dev_new_gui")])
    assert _sweep(wd, sel, api) == [1, 4], "the sync PR and the trunk PR, never #2 or the fork's #3"


def test_the_selector_picks_only_this_repositorys_release_branch_into_main(wd, sel):
    api = _FakeApi(wd, _main_prs())
    assert [pull["number"] for pull in sel.release_sync_pulls(api, "Dev_new_gui")] == [1]


def test_the_same_rules_apply_a_sync_run_parked_for_a_person_stays_parked(wd, sel):
    api = _FakeApi(wd, [_pull(1, "release-sync-main")])
    api.runs[f"{1:040x}"][0]["triggering_actor"] = {"login": "mrveiss"}
    assert _sweep(wd, sel, api) == [], "only a run parked for the branch-update bot is released"


def test_a_sweep_of_main_itself_does_not_list_the_sync_pr_twice(wd, sel):
    api = _FakeApi(wd, [_pull(1, "release-sync-main")])
    assert sel.release_sync_pulls(api, "main") == [] and api.listed == []


def test_an_unreadable_listing_is_not_read_as_no_sync_pr(wd, sel):
    class _Broken(_FakeApi):
        def open_pull_requests(self, base: str) -> List[Dict[str, Any]]:
            raise wd.WatchdogApiError("HTTP 502")

    with pytest.raises(wd.WatchdogApiError):
        sel.release_sync_pulls(_Broken(wd, []), "Dev_new_gui")


def test_check_dispatch_feeds_the_sync_pr_into_the_one_approval_path(wd):
    source = inspect.getsource(wd.check_dispatch)
    assert 'collect_heads(pulls + release_sync_pulls(api, config["base_branch"]), api.repository)' in source
    assert _WATCHDOG.read_text(encoding="utf-8").count("def _approve_head(") == 1, "reuse it, never a second"
    assert "approve_run" not in _SELECTOR.read_text(encoding="utf-8"), "the selector selects; it approves nothing"


def test_the_watchdog_and_the_sync_workflow_name_the_same_branch(sel):
    spec = yaml.safe_load(_SYNC_WORKFLOW.read_text(encoding="utf-8"))
    assert spec["jobs"]["sync"]["env"]["SYNC_BRANCH"] == sel.RELEASE_SYNC_HEAD
    assert sel.RELEASE_SYNC_BASE == "main"
