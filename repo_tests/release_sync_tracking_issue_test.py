# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#16246, #15834 — when Actions may not open the sync PR, keep ONE tracking issue, never a silent green.

The owner ruled that this repository syncs by hand (#15834 Q2): no push token, and
"Allow GitHub Actions to create and approve pull requests" stays off. So the weekly
run can never open the sync PR here. It used to warn and exit 0: a green run that
opened nothing, every week. Now:

* a refused PR opens or updates exactly one tracking issue, found by exact title
  plus label and never by text search, so a rerun updates it in place;
* the issue is closed once a sync PR is open (a hand-opened one counts) or nothing
  is left to sync;
* a failure to read or write the issue fails the run.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import pytest
import yaml
from repo_tests._paths import repo_root
from repo_tests._release_sync_fakes import BASE, HEAD, REFUSAL, REPO, SCRIPT, SOURCE, _api, _pull, _run, load_script

_WORKFLOW = repo_root() / ".github/workflows/sync-main-to-release.yml"
CLOSED = {"state": "closed", "state_reason": "completed"}
FORBIDDEN = (403, {"message": "Resource not accessible by integration"})


@pytest.fixture(scope="module")
def rs():
    return load_script()


def _refused(api):
    """GitHub refuses the PR, as it does whenever Actions may not open pull requests."""
    api.routes[2] = ("POST", f"/repos/{REPO}/pulls", (403, REFUSAL))
    return api


def _issue(rs, number: int, body: str = "", title: str = "", is_pr: bool = False) -> Dict[str, Any]:
    issue = {"number": number, "title": title or rs.TRACKING_TITLE, "body": body}
    if is_pr:
        issue["pull_request"] = {"url": "https://example.invalid/pr"}
    return issue


def _issue_posts(api) -> List[Dict[str, Any]]:
    return [payload for path, payload in api.writes("POST") if path.endswith("/issues")]


def _issue_patches(api) -> List[Tuple[str, Dict[str, Any]]]:
    return [(path, payload) for path, payload in api.writes("PATCH") if "/issues/" in path]


def _closed(api) -> List[str]:
    return [path for path, payload in _issue_patches(api) if payload == CLOSED]


# --------------------------------------------------------------------------
# Refused: one tracking issue, created once, updated in place.
# --------------------------------------------------------------------------


def test_a_refused_pr_opens_one_tracking_issue_carrying_the_pr_body_link_and_command(rs, monkeypatch):
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://example.invalid")
    api = _refused(_api([], 310))
    assert _run(rs, api) == 0
    posts = _issue_posts(api)
    assert len(posts) == 1, "exactly one tracking issue"
    assert posts[0]["title"] == rs.TRACKING_TITLE and posts[0]["labels"] == [rs.TRACKING_LABEL]
    body = posts[0]["body"]
    assert body.startswith(rs.BODY_MARKER), "the body must be recognisably generated"
    assert "**310 commits**" in body and "gh pr merge --merge" in body and "Never `--squash`" in body
    assert f"https://example.invalid/{REPO}/compare/{BASE}...{HEAD}?expand=1" in body
    assert f"gh pr create --repo {REPO} --base {BASE} --head {HEAD}" in body


def test_a_rerun_updates_the_tracking_issue_in_place_and_never_duplicates_it(rs):
    api = _refused(_api([], 311, issues=[_issue(rs, 70, body="stale")]))
    assert _run(rs, api) == 0
    assert _issue_posts(api) == [], "a rerun must never open a second tracking issue"
    patches = _issue_patches(api)
    assert [path for path, _ in patches] == [f"/repos/{REPO}/issues/70"]
    assert "**311 commits**" in patches[0][1]["body"]


def test_a_current_tracking_issue_is_not_rewritten(rs):
    first = _refused(_api([], 310))
    _run(rs, first)
    api = _refused(_api([], 310, issues=[_issue(rs, 70, body=_issue_posts(first)[0]["body"])]))
    assert _run(rs, api) == 0
    assert _issue_posts(api) == [] and _issue_patches(api) == []


def test_a_duplicate_tracking_issue_is_closed_and_the_oldest_kept(rs):
    api = _refused(_api([], 310, issues=[_issue(rs, 81), _issue(rs, 70)]))
    assert _run(rs, api) == 0
    assert _issue_posts(api) == []
    assert _closed(api) == [f"/repos/{REPO}/issues/81"]


def test_only_the_exact_title_counts_and_a_pr_is_never_the_tracking_issue(rs):
    near = _issue(rs, 60, title=rs.TRACKING_TITLE + " (old)")
    pull = _issue(rs, 61, is_pr=True)
    api = _refused(_api([], 310, issues=[near, pull]))
    assert _run(rs, api) == 0
    assert len(_issue_posts(api)) == 1 and _issue_patches(api) == []


def test_the_tracking_issue_is_never_found_by_a_text_search():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "search/issues" not in source, "found by exact title plus label, never by text search"


# --------------------------------------------------------------------------
# Closed once it is no longer needed.
# --------------------------------------------------------------------------


def test_the_tracking_issue_is_closed_when_nothing_is_left_to_sync(rs):
    api = _api([], 0, issues=[_issue(rs, 70)])
    assert _run(rs, api) == 0
    assert _issue_patches(api) == [(f"/repos/{REPO}/issues/70", CLOSED)]


@pytest.mark.parametrize("head", [HEAD, SOURCE])
def test_the_tracking_issue_is_closed_when_a_sync_pr_is_open_hand_opened_included(rs, head):
    api = _api([_pull(12, head=head)], 310, issues=[_issue(rs, 70)])
    assert _run(rs, api) == 0
    assert _closed(api) == [f"/repos/{REPO}/issues/70"] and _issue_posts(api) == []


def test_the_tracking_issue_is_closed_once_the_pr_opens(rs):
    api = _api([], 310, issues=[_issue(rs, 70)])
    assert _run(rs, api) == 0
    assert len([path for path, _ in api.writes("POST") if path.endswith("/pulls")]) == 1
    assert _closed(api) == [f"/repos/{REPO}/issues/70"]


# --------------------------------------------------------------------------
# Never a silent green.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("existing", [False, True])
def test_a_failure_to_write_the_tracking_issue_fails_the_run(rs, monkeypatch, existing):
    api = _refused(_api([], 310, issues=[_issue(rs, 70, body="stale")] if existing else []))
    api.routes[5] = ("POST", f"/repos/{REPO}/issues", FORBIDDEN)
    api.routes[6] = ("PATCH", "/issues/", FORBIDDEN)
    with pytest.raises(rs.WatchdogApiError, match="tracking issue"):
        _run(rs, api)
    monkeypatch.setattr(rs, "build_api", lambda: api)
    assert rs.main([]) == 2, "a run that could not keep the tracking issue is never green"


def test_an_unreadable_issue_listing_fails_the_run_rather_than_opening_a_duplicate(rs):
    api = _refused(_api([], 310))
    api.routes[4] = ("GET", "/issues?", FORBIDDEN)
    with pytest.raises(rs.WatchdogApiError):
        _run(rs, api)
    assert _issue_posts(api) == []


# --------------------------------------------------------------------------
# The workflow grants what the issue needs, and runs when nothing is ahead.
# --------------------------------------------------------------------------


def _job() -> Dict[str, Any]:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))["jobs"]["sync"]


def test_the_workflow_grants_issues_write():
    assert _job()["permissions"].get("issues") == "write", "the default token is read-only here (#15834)"


def test_the_script_runs_even_when_nothing_is_ahead_so_it_can_close_the_issue():
    step = next(step for step in _job()["steps"] if "release_sync_main.py" in step.get("run", ""))
    assert "if" not in step, "a step skipped when nothing is ahead never closes the tracking issue"
    assert '[ "$AHEAD" != "0" ]' in step["run"], "the push stays conditional on commits to sync"
