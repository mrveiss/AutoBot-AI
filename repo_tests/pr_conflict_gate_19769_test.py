# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#19769 -- a conflicting PR fails CI at once: runs cancelled, ``no-merge-conflicts`` failure.

Pins the pure decisions in ``pr_conflict_gate_core`` and drives ``pr_conflict_gate``
through a recorded REST client.
"""

from __future__ import annotations

import importlib.util
import sys
from typing import Any, Dict, List, Optional, Tuple

import yaml
from repo_tests._paths import repo_root

_SCRIPTS = repo_root() / "pipeline-scripts"
REPO = "owner/repo"
SHA = "b" * 40
OWN_RUN = 500


def _load(name: str):
    sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


core = _load("pr_conflict_gate_core")
gate = _load("pr_conflict_gate")


class FakeApi:
    """Answers GETs of one PR from a queue of bodies; records every mutation."""

    repository = REPO

    def __init__(self, pulls: List[Dict[str, Any]], runs: Optional[List[Dict[str, Any]]] = None) -> None:
        self.pulls, self.runs, self.posts, self.statuses, self.gets = list(pulls), runs or [], [], [], 0

    def request(self, method: str, path: str, payload: Any = None) -> Tuple[int, Any]:
        if method == "GET" and "/pulls/" in path:
            self.gets += 1
            return 200, self.pulls[min(self.gets - 1, len(self.pulls) - 1)]
        if method == "POST" and path.endswith("/cancel"):
            self.posts.append(path)
            return 202, {}
        raise AssertionError(f"unexpected {method} {path}")

    def runs_for_sha(self, sha: str) -> List[Dict[str, Any]]:
        return self.runs

    def set_status(self, sha: str, state: str, context: str, description: str, target_url: str) -> int:
        self.statuses.append((sha, state, context, description))
        return 201


def _pull(mergeable: Optional[bool], state: str) -> Dict[str, Any]:
    return {"head": {"sha": SHA, "repo": {"full_name": REPO}}, "mergeable": mergeable, "mergeable_state": state}


def test_conflicting_cancels_runs_and_fails_status_excluding_own_run() -> None:
    runs = [
        {"id": 1, "status": "in_progress"},
        {"id": 2, "status": "queued"},
        {"id": 3, "status": "completed"},
        {"id": OWN_RUN, "status": "in_progress"},
    ]
    api = FakeApi([_pull(False, "dirty")], runs)
    verdict = gate.check_pull(api, 7, OWN_RUN, "", sleep=lambda _s: None)
    assert verdict.kind == core.CONFLICTING
    assert api.posts == [f"/repos/{REPO}/actions/runs/1/cancel", f"/repos/{REPO}/actions/runs/2/cancel"]
    assert api.statuses == [(SHA, "failure", "no-merge-conflicts", "merge conflict with main: merge main and push")]


def test_mergeable_is_success_and_cancels_nothing() -> None:
    api = FakeApi([_pull(True, "clean")], [{"id": 1, "status": "in_progress"}])
    verdict = gate.check_pull(api, 7, OWN_RUN, "", sleep=lambda _s: None)
    assert verdict.kind == core.MERGEABLE
    assert api.posts == []
    assert api.statuses[0][1] == "success"


def test_unknown_after_retries_is_pending_never_success() -> None:
    api = FakeApi([_pull(None, "unknown")], [{"id": 1, "status": "in_progress"}])
    sleeps: List[float] = []
    verdict = gate.check_pull(api, 7, OWN_RUN, "", sleep=sleeps.append)
    assert verdict.kind == core.UNKNOWN
    assert api.gets == gate.UNKNOWN_MAX_ATTEMPTS
    assert len(sleeps) == gate.UNKNOWN_MAX_ATTEMPTS - 1
    assert max(sleeps) <= gate.UNKNOWN_BACKOFF_CAP_SECONDS
    assert api.posts == []
    assert api.statuses[0][1] == "pending"
    assert "unknown" in api.statuses[0][3]


def test_unknown_then_resolved_stops_retrying() -> None:
    api = FakeApi([_pull(None, "unknown"), _pull(False, "dirty")])
    verdict = gate.check_pull(api, 7, OWN_RUN, "", sleep=lambda _s: None)
    assert verdict.kind == core.CONFLICTING
    assert api.gets == 2


def test_classify_malformed_body_is_unknown() -> None:
    assert core.classify({}) == core.UNKNOWN
    assert core.classify({"mergeable": None, "mergeable_state": "clean"}) == core.UNKNOWN
    assert core.classify({"mergeable": True, "mergeable_state": "dirty"}) == core.CONFLICTING


def test_runs_to_cancel_skips_own_and_finished() -> None:
    runs = [{"id": 1, "status": "queued"}, {"id": 2, "status": "completed"}, {"id": 9, "status": "queued"}]
    assert core.runs_to_cancel(runs, 9) == [1]
    assert core.runs_to_cancel(runs, None) == [1, 9]


def test_fork_prs_are_not_checkable() -> None:
    assert core.is_checkable({"head": {"repo": {"full_name": REPO}}}, REPO)
    assert not core.is_checkable({"head": {"repo": {"full_name": "x/y"}}}, REPO)
    assert not core.is_checkable({"head": {"repo": None}}, REPO)


def test_workflow_triggers_permissions_and_no_pat() -> None:
    path = repo_root() / ".github/workflows/pr-merge-conflict-gate.yml"
    text = path.read_text(encoding="utf-8")
    spec = yaml.safe_load(text)
    triggers = spec.get("on", spec.get(True))
    assert triggers["push"]["branches"] == ["main"]
    assert triggers["schedule"] == [{"cron": "*/10 * * * *"}]
    assert "workflow_dispatch" in triggers
    assert triggers["pull_request"]["types"] == ["opened", "reopened", "synchronize", "ready_for_review"]
    assert spec["jobs"]["gate"]["permissions"] == {
        "contents": "read",
        "statuses": "write",
        "actions": "write",
        "pull-requests": "read",
    }
    assert "AUTOBOT_PUSH_TOKEN" not in text and "AUTOBOT_PROJECT_TOKEN" not in text


class _SweepApi(FakeApi):
    """Two PRs; listing runs raises for the first, cancel fails for the second."""

    def __init__(self, fail_runs: bool, fail_cancel: bool) -> None:
        super().__init__([])
        self.fail_runs, self.fail_cancel = fail_runs, fail_cancel

    def request(self, method: str, path: str, payload: Any = None) -> Tuple[int, Any]:
        if method == "GET" and "state=open" in path:
            repo = {"full_name": REPO}
            return 200, [{"number": 1, "head": {"repo": repo}}, {"number": 2, "head": {"repo": repo}}]
        if method == "GET" and "/pulls/" in path:
            number = int(path.rsplit("/", 1)[1])
            return 200, {
                "head": {"sha": f"{number}" * 40, "repo": {"full_name": REPO}},
                "mergeable": False,
                "mergeable_state": "dirty",
            }
        if method == "POST" and path.endswith("/cancel"):
            return (500, {}) if self.fail_cancel else (202, {})
        raise AssertionError(f"unexpected {method} {path}")

    def runs_for_sha(self, sha: str) -> List[Dict[str, Any]]:
        if self.fail_runs and sha.startswith("1"):
            raise gate.WatchdogError("boom")
        return [{"id": 1, "status": "queued"}]


def test_one_prs_api_error_does_not_stop_the_next_pr_and_exits_nonzero() -> None:
    api = _SweepApi(fail_runs=True, fail_cancel=False)
    code = gate.run(api, "schedule", "", "main", OWN_RUN, "")
    assert code == 1
    assert [s[0][0] for s in api.statuses] == ["1", "2"]
    assert all(s[1] == "failure" for s in api.statuses)


def test_status_is_set_even_when_cancel_fails() -> None:
    api = _SweepApi(fail_runs=False, fail_cancel=True)
    assert gate.run(api, "push", "", "main", OWN_RUN, "") == 0
    assert len(api.statuses) == 2


def test_fork_pr_on_the_pull_request_path_gets_no_status() -> None:
    pull = _pull(False, "dirty")
    pull["head"]["repo"] = {"full_name": "fork/repo"}
    api = FakeApi([pull], [{"id": 1, "status": "queued"}])
    assert gate.check_pull(api, 7, OWN_RUN, "", sleep=lambda _s: None) is None
    assert api.statuses == [] and api.posts == []


def test_scheduled_sweeps_are_not_cancelled_by_the_next_tick() -> None:
    spec = yaml.safe_load((repo_root() / ".github/workflows/pr-merge-conflict-gate.yml").read_text(encoding="utf-8"))
    assert spec["concurrency"]["cancel-in-progress"] == "${{ github.event_name != 'schedule' }}"
