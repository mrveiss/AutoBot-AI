# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#19548 — the branch sync merges main into every branch, and pushes only what GITHUB_TOKEN may push.

Drives ``pipeline-scripts/branch_sync.py`` through a recorded git runner and a
recorded REST client, so each path is pinned by what it RAN, not by what its
source looks like:

* a conflict is aborted and labelled with one comment, and nothing is pushed;
* a merge that would change ``.github/workflows/*`` is labelled, never pushed;
* the merge commit message is exact, and the push is a plain one;
* fork PRs are skipped, drafts are not, PRs into another base are left alone;
* the comment is found by its marker, so a second run never posts a second one;
* the sync labels clear once the branch is 0 behind;
* a merge that fails WITHOUT a conflict is an error that fails the job (#15938).
"""

from __future__ import annotations

import importlib.util
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pytest
from repo_tests._paths import repo_root

_SCRIPTS = repo_root() / "pipeline-scripts"
REPO = "mrveiss/AutoBot-AI"
HEAD_SHA = "a" * 40


def _load(name: str):
    sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    # Registered before exec: dataclasses resolve their module, and branch_sync's
    # own `import branch_sync_core` must get this instance, not a second copy.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


core = _load("branch_sync_core")
bs = _load("branch_sync")


class Runner:
    """A git stand-in: the first matching argv prefix answers; every call is recorded."""

    def __init__(self, answers: Sequence[Tuple[Tuple[str, ...], Tuple[int, str]]]) -> None:
        self.answers, self.calls = list(answers), []

    def __call__(self, args: Sequence[str]) -> Tuple[int, str]:
        args = tuple(args)
        self.calls.append(args)
        for prefix, answer in self.answers:
            if args[: len(prefix)] == prefix:
                return answer
        return 0, ""

    def ran(self, *prefix: str) -> bool:
        return any(call[: len(prefix)] == prefix for call in self.calls)


class Api:
    """A GitHubApi stand-in: routes by (method, path prefix); every request is recorded."""

    repository, api_root, token = REPO, "https://api.github.com", "t"

    def __init__(self, routes: Optional[List[Tuple[str, str, Tuple[int, Any]]]] = None) -> None:
        self.routes, self.calls, self.last_headers = list(routes or []), [], {}

    def request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Tuple[int, Any]:
        self.calls.append((method, path, payload))
        for verb, prefix, answer in self.routes:
            if verb == method and path.startswith(prefix):
                return answer
        if method == "POST" and "/issues/" in path and path.endswith("/labels"):
            return 200, []  # GitHub answers "add labels" with 200 and the label list
        return {"GET": 200, "POST": 201, "PATCH": 200, "DELETE": 200}[method], [] if method == "GET" else {}

    def writes(self) -> List[Tuple[str, str, Any]]:
        return [call for call in self.calls if call[0] != "GET"]

    def upsert(self, api_url: str, repo: str, number: int, token: str, marker: str, body: str) -> Tuple[str, int]:
        """Stands in for the canonical upsert_pr_comment.upsert; recorded as a comment write."""
        self.calls.append(("UPSERT", f"/repos/{repo}/issues/{number}/comments", {"marker": marker, "body": body}))
        return "created", 1


def _gh(api: Api, **kwargs: Any) -> Any:
    return bs.SyncApi(api, sleep=kwargs.pop("sleep", lambda _: None), upsert=api.upsert)


def _git(behind: str = "5", merge: Tuple[int, str] = (0, ""), unmerged: str = "", changed: str = "x.py", push=(0, "")):
    return Runner(
        [
            (("rev-parse",), (0, HEAD_SHA)),
            (("rev-list", "--count"), (0, behind)),
            (("merge", "--abort"), (0, "")),
            (("merge", "--no-edit"), merge),
            (("diff", "--name-only", "--diff-filter=U"), (0, unmerged)),
            (("diff", "--name-only"), (0, changed)),
            (("merge-base",), (0, "b" * 40)),
            (("log",), (0, "1234567\x1ffix(x): main side (#100)\n")),
            (("push",), push),
        ]
    )


def _target(labels: Tuple[str, ...] = (), pr: Optional[int] = 7) -> Any:
    return core.SyncTarget("issue-1-x", pr, HEAD_SHA, labels)


def _sync(runner: Runner, api: Api, target: Any, dry_run: bool = False) -> Tuple[str, str]:
    return bs.Syncer(bs.Git(runner), _gh(api), "main", dry_run).sync(target)


_CONFLICT = (1, "Auto-merging x.py\nCONFLICT (content): Merge conflict in x.py\nAutomatic merge failed")


# ---------------------------------------------------------------- the conflict path


def test_a_conflict_aborts_labels_and_comments_and_never_pushes() -> None:
    runner, api = _git(merge=_CONFLICT, unmerged="x.py"), Api([("GET", f"/repos/{REPO}/labels/", (200, {}))])
    outcome, _ = _sync(runner, api, _target())
    assert outcome == core.CONFLICT
    assert runner.ran("merge", "--abort"), "a conflicted merge must be aborted, never resolved"
    assert not runner.ran("push"), "a conflicted branch must never be pushed"
    assert not runner.ran("checkout", "--ours") and not runner.ran("add"), "never auto-resolve"
    (comment,) = [p["body"] for m, path, p in api.writes() if m == "UPSERT" and path.endswith("/issues/7/comments")]
    assert core.MARKER_CONFLICT in comment and "`x.py`" in comment and "`1234567`" in comment and "#100" in comment
    assert ("POST", f"/repos/{REPO}/issues/7/labels", {"labels": [core.LABEL_CONFLICT]}) in api.writes()


def test_a_conflicted_pr_less_branch_is_reported_only() -> None:
    runner, api = _git(merge=_CONFLICT, unmerged="x.py"), Api()
    assert _sync(runner, api, _target(pr=None))[0] == core.CONFLICT
    assert not runner.ran("push") and not api.writes(), "no PR exists to carry a label; summary only"


def test_the_conflict_comment_shows_both_sides_and_caps_counts_not_text() -> None:
    long_subject = "feat(y): " + "w" * 300 + " (#5, #6)"
    many = [(f"{n:07d}", long_subject) for n in range(core.MAX_COMMITS_PER_SIDE + 2)]
    files = [core.FileHistory(f"f{n}.py", many, []) for n in range(core.MAX_FILES_LISTED + 1)]
    body = core.conflict_comment("b", "main", "c" * 40, files)
    assert body.startswith(core.MARKER_CONFLICT) and long_subject in body, "a subject must never be truncated"
    assert "| #5, #6 |" in body and "2 more commit(s) not listed" in body and "1 more conflicted file(s)" in body
    assert "no commit touched this file since the merge base" in body, "the empty side is stated, not omitted"


# ------------------------------------------------------- the workflow-file path


def test_a_merge_that_changes_a_workflow_file_is_labelled_and_never_pushed() -> None:
    runner, api = _git(changed=".github/workflows/ci.yml\nsrc/a.py"), Api()
    outcome, detail = _sync(runner, api, _target())
    assert outcome == core.WORKFLOW and ".github/workflows/ci.yml" in detail
    assert runner.ran("diff", "--name-only", HEAD_SHA, "HEAD"), "the delta is head-vs-merge-result"
    assert not runner.ran("push"), "GitHub refuses this push with GITHUB_TOKEN; detect it, do not try it"
    (comment,) = [p["body"] for m, path, p in api.writes() if m == "UPSERT" and path.endswith("/issues/7/comments")]
    assert core.MARKER_WORKFLOW in comment and "`.github/workflows/ci.yml`" in comment
    assert ("POST", f"/repos/{REPO}/issues/7/labels", {"labels": [core.LABEL_WORKFLOW]}) in api.writes()


def test_a_refused_push_is_handled_as_a_workflow_skip() -> None:
    refusal = (1, "! [remote rejected] HEAD -> x (refusing to allow a GitHub App to create or update workflow)")
    runner, api = _git(push=refusal), Api()
    assert _sync(runner, api, _target())[0] == core.WORKFLOW
    assert any(path.endswith("/issues/7/labels") for _, path, _ in api.writes())


def test_workflow_changes_matches_the_directory_only() -> None:
    assert core.workflow_changes([".github/workflows/a.yml", ".github/filters/b.yml", "docs/.github/workflows/c"]) == [
        ".github/workflows/a.yml"
    ]


# ------------------------------------------------------- merge and push argv


def test_the_merge_message_and_argv_are_exact() -> None:
    runner = Runner([])
    bs.Git(runner).merge("issue-19548-x", "main")
    assert runner.calls == [("merge", "--no-edit", "-m", "Merge main into issue-19548-x (auto-sync)", "origin/main")]
    assert core.merge_message("b") == "Merge main into b (auto-sync)"


def test_a_clean_sync_is_one_plain_push_and_clears_the_labels() -> None:
    runner, api = _git(), Api()
    outcome, _ = _sync(runner, api, _target(labels=(core.LABEL_CONFLICT,)))
    assert outcome == core.SYNCED
    assert [c for c in runner.calls if c[0] == "push"] == [("push", "origin", "HEAD:refs/heads/issue-1-x")]
    assert [m for m, path, _ in api.writes()] == ["DELETE"], "only the stale label goes; nothing else is written"


def test_a_branch_that_moved_is_skipped_never_overwritten() -> None:
    rejected = (1, " ! [rejected]        HEAD -> x (fetch first)\nerror: failed to push some refs")
    runner, api = _git(push=rejected), Api()
    assert _sync(runner, api, _target())[0] == core.HEAD_MOVED and not api.writes()
    moved = core.SyncTarget("issue-1-x", 7, "f" * 40)
    runner = _git()
    assert _sync(runner, Api(), moved)[0] == core.HEAD_MOVED and not runner.ran("merge")


def test_a_dry_run_pushes_and_writes_nothing() -> None:
    for runner in (_git(), _git(merge=_CONFLICT, unmerged="x.py"), _git(changed=".github/workflows/a.yml")):
        api = Api()
        _sync(runner, api, _target(), dry_run=True)
        assert not runner.ran("push") and not api.writes()


# --------------------------------------------------------------- 0 behind


def test_labels_clear_when_the_branch_is_zero_behind() -> None:
    runner, api = _git(behind="0"), Api()
    outcome, _ = _sync(runner, api, _target(labels=(core.LABEL_CONFLICT, core.LABEL_WORKFLOW, "ci")))
    assert outcome == core.CURRENT and not runner.ran("checkout")
    deleted = sorted(path.rsplit("/", 1)[-1] for m, path, _ in api.writes() if m == "DELETE")
    assert deleted == sorted([core.LABEL_CONFLICT, core.LABEL_WORKFLOW])


def test_an_up_to_date_branch_without_sync_labels_costs_no_api_call() -> None:
    api = Api()
    assert _sync(_git(behind="0"), api, _target(labels=("ci",)))[0] == core.CURRENT and not api.calls


# --------------------------------------------------------------- dedupe


def test_the_comment_is_deduped_by_its_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    """The sync calls the ONE upsert (#12984); a bot comment carrying the marker is updated, not added."""
    upsert = bs.load_upsert()
    module = sys.modules[upsert.__module__]
    ours = {"id": 99, "user": {"type": "Bot"}, "body": f"{core.MARKER_CONFLICT}\nolder", "created_at": "2"}
    quoted = {"id": 5, "user": {"type": "User"}, "body": core.MARKER_CONFLICT, "created_at": "3"}
    calls: List[Tuple[str, str]] = []

    def fake_call(method: str, url: str, token: str, payload: Any = None) -> Tuple[Any, Optional[str]]:
        calls.append((method, url))
        return ([{"id": 1, "body": "hi"}, quoted, ours] if method == "GET" else {"id": 99}), None

    monkeypatch.setattr(module, "_call", fake_call)
    assert upsert("https://api.github.com", REPO, 7, "t", core.MARKER_CONFLICT, "new") == ("updated", 99)
    assert [m for m, _ in calls] == ["GET", "PATCH"] and calls[1][1].endswith("/issues/comments/99")


def test_the_sync_reuses_the_canonical_upsert() -> None:
    assert bs.load_upsert().__module__ == "upsert_pr_comment"
    assert bs.UPSERT_SCRIPT.is_file(), "the canonical upsert moved; the sync would fail at its first comment"


def test_an_already_labelled_pr_gets_no_second_comment() -> None:
    runner, api = _git(merge=_CONFLICT, unmerged="x.py"), Api()
    assert _sync(runner, api, _target(labels=(core.LABEL_CONFLICT,)))[0] == core.CONFLICT
    assert not api.calls, "the label is the record that the one comment exists"


# --------------------------------------------------------------- planning


def _pull(number: int, ref: str, *, repo: str = REPO, base: str = "main", draft: bool = False) -> Dict[str, Any]:
    head = {"ref": ref, "sha": HEAD_SHA, "repo": {"full_name": repo} if repo else None}
    return {"number": number, "head": head, "base": {"ref": base}, "labels": [], "draft": draft}


def test_the_plan_skips_forks_includes_drafts_and_leaves_other_bases_alone() -> None:
    pulls = [
        _pull(1, "issue-1"),
        _pull(2, "issue-2", draft=True),
        _pull(3, "feature", repo="someone/fork"),
        _pull(4, "gone", repo=""),
        _pull(5, "stacked", base="issue-1"),
        _pull(6, "release"),
    ]
    branches = ["main", "issue-1", "issue-2", "stacked", "release", "parked-1", "rescued/stash-1", "HEAD", "-x"]
    plan = core.plan_run(pulls, branches, REPO)
    assert [(t.branch, t.pr) for t in plan.targets] == [("issue-1", 1), ("issue-2", 2), ("parked-1", None)]
    assert plan.skipped[core.FORK] == ["#3", "#4"]
    assert plan.skipped[core.OTHER_BASE] == ["#5 `stacked`"], "a PR into another base is neither synced nor parked"
    assert "#6 `release`" in plan.skipped[core.POLICY] and "`rescued/stash-1` (no PR)" in plan.skipped[core.POLICY]
    assert plan.skipped[core.UNREACHABLE] == ["`-x` (no PR)"]


def test_dependabot_and_automation_branches_are_never_synced_pr_or_not() -> None:
    """Dependabot rebases its own PRs; bot branches regenerate from main (#19568 review)."""
    pulls = [_pull(7, "dependabot/pip/x-1.2"), _pull(8, "automation/test-durations"), _pull(9, "issue-9")]
    branches = ["dependabot/npm_and_yarn/y", "automation/other", "parked-2"]
    plan = core.plan_run(pulls, branches, REPO)
    assert [(t.branch, t.pr) for t in plan.targets] == [("issue-9", 9), ("parked-2", None)]
    for skipped in (
        "#7 `dependabot/pip/x-1.2`",
        "#8 `automation/test-durations`",
        "`dependabot/npm_and_yarn/y` (no PR)",
        "`automation/other` (no PR)",
    ):
        assert skipped in plan.skipped[core.POLICY], skipped


@pytest.mark.parametrize(
    "name,rendered",
    [("issue-1", "`issue-1`"), ("we`ird", "`` we`ird ``"), ("a``b", "`` a` `b ``")],
)
def test_a_backtick_in_a_branch_name_cannot_break_the_comment(name: str, rendered: str) -> None:
    assert core.code(name) == rendered
    assert f"into {rendered} conflicts" in core.conflict_comment(name, "main", "0" * 40, [])


@pytest.mark.parametrize(
    "rc,output,unmerged,expected",
    [
        (0, "", [], core.SYNCED),
        (1, "CONFLICT (content): Merge conflict in a", [], core.CONFLICT),
        (1, "", ["a"], core.CONFLICT),
        (129, "error: unknown option `no-rebase'", [], core.ERROR),
    ],
)
def test_classify_merge(rc: int, output: str, unmerged: List[str], expected: str) -> None:
    """#15938: a merge that fails without a conflict is the job's defect, never the branch's."""
    assert core.classify_merge(rc, output, unmerged) == expected


def test_a_non_conflict_merge_failure_fails_the_job() -> None:
    runner = _git(merge=(129, "error: unknown option `no-rebase'"))
    outcome, detail = _sync(runner, Api(), _target())
    assert outcome == core.ERROR and "unknown option" in detail and runner.ran("merge", "--abort")
    assert bs.exit_code({core.ERROR: ["x"]}) == 1
    assert bs.exit_code({core.CONFLICT: ["x"], core.SYNCED: ["y"]}) == 0


# --------------------------------------------------------------- REST plumbing


def test_a_secondary_rate_limit_honours_retry_after() -> None:
    class Limited(Api):
        def request(self, method, path, payload=None):
            self.calls.append((method, path, payload))
            if len(self.calls) == 1:
                self.last_headers = {"retry-after": "7"}
                return 403, {"message": "You have exceeded a secondary rate limit."}
            self.last_headers = {}
            return 200, []

    slept: List[float] = []
    assert _gh(Limited(), sleep=slept.append).call("GET", "/x") == (200, [])
    assert slept == [7]


def test_open_pulls_paginates_and_fails_closed() -> None:
    page1 = [{"number": n} for n in range(bs.PAGE_SIZE)]
    api = Api([("GET", f"/repos/{REPO}/pulls?state=open&per_page=100&page=1", (200, page1))])
    api.routes.append(("GET", f"/repos/{REPO}/pulls?state=open&per_page=100&page=2", (200, [{"number": 999}])))
    assert len(_gh(api).open_pulls()) == bs.PAGE_SIZE + 1
    broken = Api([("GET", f"/repos/{REPO}/pulls", (502, {"message": "bad gateway"}))])
    with pytest.raises(bs.SyncApiError):
        bs.run(bs.Git(Runner([])), _gh(broken), "main", False)


def test_the_summary_names_every_outcome() -> None:
    summary = bs.render_summary({core.SYNCED: ["#1 `a`"], core.FORK: ["#3"]}, dry_run=False)
    for outcome in (core.SYNCED, core.CURRENT, core.CONFLICT, core.WORKFLOW, core.HEAD_MOVED, core.FORK):
        assert f"| {outcome} |" in summary
    assert "| synced | 1 |" in summary and "- #1 `a`" in summary
