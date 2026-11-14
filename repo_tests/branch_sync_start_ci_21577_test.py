# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21577 — the sync can start the suite for ONE pull request on its synced head.

A synced head ends `[skip ci]`, so GitHub runs no pull_request workflow on it. On request
(``--start-ci-for-pr N``, the workflow's ``start_ci_for_pr`` input) the sync pushes ONE empty commit WITHOUT the
marker onto that PR's branch, with the same push token, and the ordinary pipeline runs. Pinned here, each rule
with a control (the same case with only that rule satisfied is allowed):

* the number is untrusted text: digits only, passed through ``env:``, never interpolated into ``run:``;
* refusals: not open, a fork, a base other than main, a draft, main/release/train-*, behind main, a head that is
  not the commit the run fetched; every one is non-zero with ``::error::`` and writes nothing;
* idempotence: a head that already has a non-cancelled pull_request run of the suite is a notice and no commit;
* the commit: fixed subject + the PR number, no skip marker, no body or trailer, the verified head as its parent,
  pushed plainly (never forced), a rejected push is an error;
* the workflow: the input exists, `actions: read` is the only permission added.

Not provable here: that a push with the sync's token starts the pull_request pipeline (the workflow header says a
PAT push starts runs); that is shown by one real request after merge.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from typing import Any, Dict, List, Optional

import pytest
import yaml
from repo_tests._paths import repo_root
from repo_tests.branch_sync_19548_test import HEAD_SHA, REPO, Api, Runner, bs, core

PR = 21578
BRANCH = "issue-1-x"
_WORKFLOW = repo_root() / ".github" / "workflows" / "sync-branches-with-main.yml"


def pull(**over: Any) -> Dict[str, Any]:
    state: Dict[str, Any] = {
        "number": PR,
        "state": "open",
        "draft": False,
        "head": {"ref": BRANCH, "sha": HEAD_SHA, "repo": {"full_name": REPO}},
        "base": {"ref": "main"},
    }
    state.update(over)
    return state


def run(**over: Any) -> Dict[str, Any]:
    state: Dict[str, Any] = {"head_sha": HEAD_SHA, "event": "pull_request", "path": ".github/workflows/ci.yml"}
    state.update(over)
    return state


def git(*, local: str = HEAD_SHA, behind: str = "0", parent: str = HEAD_SHA, push=(0, "")) -> Runner:
    return Runner(
        [
            (("rev-parse", "HEAD^"), (0, parent)),
            (("rev-parse", "--verify", "--quiet", f"origin/{BRANCH}"), (0, local)),
            (("rev-list", "--count"), (0, behind)),
            (("push",), push),
        ]
    )


def listing(runs: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    return {"workflow_runs": runs or [], "total_count": len(runs or [])}


def runs_body_api(body: Any) -> Api:
    return Api(
        [("GET", f"/repos/{REPO}/pulls/{PR}", (200, pull())), ("GET", f"/repos/{REPO}/actions/runs", (200, body))]
    )


def api(pr: Dict[str, Any], runs: Optional[List[Dict[str, Any]]] = None) -> Api:
    return Api(
        [
            ("GET", f"/repos/{REPO}/pulls/{PR}", (200, pr)),
            ("GET", f"/repos/{REPO}/actions/runs", (200, listing(runs))),
        ]
    )


def start(runner: Runner, fake: Api, dry_run: bool = False):
    gh = bs.SyncApi(fake, sleep=lambda _: None, upsert=fake.upsert)
    return bs.start_suite(bs.Git(runner, auth=bs.push_auth("tok")), gh, PR, "main", dry_run)


def pushed(runner: Runner) -> bool:
    """A push, whatever precedes it on the argv (the token pair comes first)."""
    return any("push" in call for call in runner.calls)


def wrote_nothing(runner: Runner) -> bool:
    return not (pushed(runner) or runner.ran("checkout") or runner.ran("commit"))


# ------------------------------------------------------------------ the untrusted number


BAD_NUMBERS = ["", " 7", "7 ", "7\n", "0", "07", "-1", "7;rm -rf", "$(id)", "１２", "1" * 10, "0x1f"]


@pytest.mark.parametrize("text", BAD_NUMBERS)
def test_only_plain_digits_are_a_pull_request_number(text: str) -> None:
    assert core.parse_pr_number(text) is None


def test_control_plain_digits_are_accepted() -> None:
    assert core.parse_pr_number("21578") == PR and core.parse_pr_number("7") == 7


def test_a_bad_number_is_refused_before_any_api_or_git_call(capsys) -> None:
    fake, runner = Api(), git()
    args = argparse.Namespace(start_ci_for_pr="7;x", base="main", dry_run=False)
    assert bs.start_requested(bs.SyncApi(fake, sleep=lambda _: None, upsert=fake.upsert), "tok", args) == 1
    assert "::error::start_ci_for_pr must be a pull request number (digits only)" in capsys.readouterr().out
    assert fake.calls == [] and runner.calls == []


# ------------------------------------------------------------------ the refusals, each with its control


def reason(pull_changes: Optional[Dict[str, Any]] = None, behind: Optional[int] = 0, local: str = HEAD_SHA) -> str:
    return core.refuse_start_ci(pull(**(pull_changes or {})), REPO, "main", behind, local)


RULES = [
    ("not open", {"pull_changes": {"state": "closed"}}, "is not open"),
    ("a fork", {"pull_changes": {"head": {"ref": BRANCH, "sha": HEAD_SHA, "repo": {"full_name": "x/y"}}}}, "fork"),
    ("a deleted fork", {"pull_changes": {"head": {"ref": BRANCH, "sha": HEAD_SHA, "repo": None}}}, "fork"),
    ("another base", {"pull_changes": {"base": {"ref": "release"}}}, "does not target main"),
    ("a draft", {"pull_changes": {"draft": True}}, "draft"),
    ("main", {"pull_changes": {"head": {"ref": "main", "sha": HEAD_SHA, "repo": {"full_name": REPO}}}}, "never writes"),
    ("release", {"pull_changes": {"head": {"ref": "release", "sha": HEAD_SHA, "repo": {"full_name": REPO}}}}, "never"),
    ("a train", {"pull_changes": {"head": {"ref": "train-1", "sha": HEAD_SHA, "repo": {"full_name": REPO}}}}, "never"),
    ("behind main", {"behind": 3}, "3 commit(s) behind main: let the sync merge it first"),
    ("an unknown behind count", {"behind": None}, "unknown number of commit(s) behind"),
    ("a moved head", {"local": "c" * 40}, "the branch moved"),
    ("an unfetched head", {"local": ""}, "the branch moved"),
]


@pytest.mark.parametrize("rule, kwargs, message", RULES, ids=[r[0] for r in RULES])
def test_each_rule_refuses_with_its_reason(rule: str, kwargs: Dict[str, Any], message: str) -> None:
    assert message in reason(**kwargs), rule


def test_control_every_rule_is_the_only_thing_standing_between_the_case_and_a_start() -> None:
    assert reason() == "", "the baseline case must be allowed, or every refusal above proves nothing"
    assert reason({"base": {"ref": "main"}, "draft": False, "state": "open"}) == ""


# ------------------------------------------------------------------ idempotence


def test_a_head_with_a_suite_already_started_is_a_noop_in_progress_or_completed() -> None:
    for conclusion in (None, "success", "failure", "action_required"):
        assert core.suite_already_started([run(conclusion=conclusion)], HEAD_SHA), conclusion
    assert core.suite_already_started([run(path=".github/workflows/ci.yml@refs/pull/1/merge")], HEAD_SHA)


def test_control_nothing_that_ran_nothing_or_elsewhere_counts() -> None:
    nothing = [run(conclusion=c) for c in ("cancelled", "skipped", "startup_failure")]
    assert not core.suite_already_started(nothing, HEAD_SHA)
    assert not core.suite_already_started([run(head_sha="d" * 40)], HEAD_SHA)
    assert not core.suite_already_started([run(event="push")], HEAD_SHA)
    assert not core.suite_already_started([run(path=".github/workflows/other.yml")], HEAD_SHA)
    assert not core.suite_already_started([], HEAD_SHA)


def test_a_request_on_a_head_with_a_suite_commits_nothing_and_says_so() -> None:
    runner = git()
    code, message = start(runner, api(pull(), [run(conclusion=None)]))
    assert code == 0 and message.startswith("::notice::") and "nothing to start" in message
    assert wrote_nothing(runner)


# ------------------------------------------------------------------ the commit and the push


def test_a_start_pushes_one_empty_commit_whose_parent_is_the_verified_head() -> None:
    runner = git()
    code, message = start(runner, api(pull(), [run(conclusion="cancelled")]))
    assert code == 0 and message.startswith("started:")
    commits = [c for c in runner.calls if c[:1] == ("commit",)]
    assert commits == [("commit", "--allow-empty", "--quiet", "-m", core.start_ci_message(PR))]
    assert runner.ran("rev-parse", "HEAD^"), "the parent is read back before the push"
    assert [c for c in runner.calls if "push" in c][0][-3:] == ("push", "origin", f"HEAD:refs/heads/{BRANCH}")
    assert runner.calls.index(commits[0]) < runner.calls.index([c for c in runner.calls if "push" in c][0])


def test_the_push_is_plain_and_carries_the_token_only_on_its_own_argv() -> None:
    runner = git()
    start(runner, api(pull()))
    pushes = [c for c in runner.calls if "push" in c]
    assert len(pushes) == 1 and not {"--force", "-f", "--force-with-lease"} & set(pushes[0])
    assert pushes[0][:1] == ("-c",)
    others = [part for call in runner.calls if call is not pushes[0] for part in call]
    assert not any("AUTHORIZATION" in part for part in others), "the token reaches the push argv only"


def test_control_a_parent_that_is_not_the_verified_head_is_never_pushed() -> None:
    runner = git(parent="e" * 40)
    code, message = start(runner, api(pull()))
    assert code == 1 and "parent is not the verified head" in message
    assert not pushed(runner)


def test_a_branch_that_moved_is_rejected_by_the_remote_and_reported() -> None:
    rejected = (1, " ! [rejected]        HEAD -> issue-1-x (non-fast-forward)\nerror: failed to push some refs")
    code, message = start(git(push=rejected), api(pull()))
    assert code == 1 and message.startswith("::error::") and core.HEAD_MOVED in message


def test_a_refusal_is_nonzero_loud_and_writes_nothing_and_never_lists_runs() -> None:
    for case, runner in (
        (pull(draft=True), git()),
        (pull(base={"ref": "release"}), git()),
        (pull(), git(behind="2")),
        (pull(), git(local="c" * 40)),
    ):
        fake = api(case)
        code, message = start(runner, fake)
        assert code == 1 and message.startswith("::error::not starting the suite: "), message
        assert wrote_nothing(runner)
        assert not any("/actions/runs" in call[1] for call in fake.calls), "refuse before asking about runs"


def test_a_dry_run_reports_and_commits_nothing() -> None:
    runner = git()
    code, message = start(runner, api(pull()), dry_run=True)
    assert code == 0 and message.startswith("dry run") and wrote_nothing(runner)


def test_a_runs_list_that_is_not_an_object_is_an_error_not_an_empty_list() -> None:
    fake = Api([("GET", f"/repos/{REPO}/pulls/{PR}", (200, pull())), ("GET", f"/repos/{REPO}/actions/runs", (200, []))])
    with pytest.raises(bs.SyncApiError):
        start(git(), fake)


def test_an_api_failure_exits_one_with_an_annotation(capsys) -> None:
    fake = Api([("GET", f"/repos/{REPO}/pulls/{PR}", (404, {"message": "Not Found"}))])
    args = argparse.Namespace(start_ci_for_pr=str(PR), base="main", dry_run=False)
    assert bs.start_requested(bs.SyncApi(fake, sleep=lambda _: None, upsert=fake.upsert), "tok", args) == 1
    assert "::error::cannot start the suite" in capsys.readouterr().out


def test_a_branch_name_that_is_not_a_safe_ref_is_refused_and_nothing_is_run() -> None:
    for ref in ("-x", "a..b", "--upload-pack=x"):
        runner = git()
        head = {"ref": ref, "sha": HEAD_SHA, "repo": {"full_name": REPO}}
        code, message = start(runner, api(pull(head=head)))
        assert code == 1 and "never writes to" in message, ref
        assert wrote_nothing(runner) and not runner.ran("rev-parse") and not runner.ran("rev-list")


def test_a_runs_list_longer_than_what_was_read_or_with_no_total_cannot_tell_so_it_fails_closed() -> None:
    many = [run(head_sha="d" * 40)] * 100
    bodies = (
        {"workflow_runs": many, "total_count": 150},
        {"workflow_runs": [], "total_count": 3},
        {"workflow_runs": []},
    )
    for body in bodies:
        fake = runs_body_api(body)
        runner = git()
        with pytest.raises(bs.SyncApiError, match="cannot tell whether"):
            start(runner, fake)
        assert wrote_nothing(runner)


def test_control_a_complete_runs_list_is_read_as_it_is() -> None:
    runs = [run(head_sha="d" * 40)]
    fake = Api([("GET", f"/repos/{REPO}/actions/runs", (200, {"workflow_runs": runs, "total_count": 1}))])
    assert bs.SyncApi(fake, sleep=lambda _: None, upsert=fake.upsert).suite_runs(HEAD_SHA) == runs


# ------------------------------------------------------------------ the message


def test_the_message_has_no_skip_marker_no_trailer_and_is_one_line() -> None:
    message = core.start_ci_message(PR)
    assert core.SKIP_MARKER not in message and "\n" not in message
    assert not any(word in message.lower() for word in ("co-authored-by", "signed-off-by", "generated with"))
    assert message == f"chore(ci): start the suite on the synced head (#{PR})"


#: Every form GitHub honours to skip workflow runs: five bracketed phrases and the `skip-checks: true` trailer.
SKIP_FORMS = ["[skip ci]", "[ci skip]", "[no ci]", "[skip actions]", "[actions skip]"]
SKIP_FORMS += ["skip-checks: true", "skip-checks:true"]


@pytest.mark.parametrize("form", SKIP_FORMS)
def test_the_message_carries_no_form_of_skip_github_recognises(form: str) -> None:
    assert form not in core.start_ci_message(PR).lower()


def test_control_the_sync_merge_message_does_carry_a_skip_form_and_the_check_would_see_it() -> None:
    merged = core.merge_message("b").lower()
    assert core.merge_message("b").endswith(core.SKIP_MARKER)
    assert [form for form in SKIP_FORMS if form in merged] == ["[skip ci]"]


@pytest.mark.skipif(shutil.which("grep") is None, reason="grep -E is the rule's own matcher")
def test_the_message_passes_the_repo_commit_subject_rule() -> None:
    rule = [
        line
        for line in (repo_root() / "scripts" / "lib" / "commit-subject.ere").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert len(rule) == 1
    for pattern, text in ((rule[0], core.start_ci_message(PR)), ("#[0-9]{3,}", core.start_ci_message(PR))):
        assert subprocess.run(["grep", "-qE", pattern], input=text, text=True).returncode == 0, pattern
    assert subprocess.run(["grep", "-qE", rule[0]], input="start the suite", text=True).returncode != 0


# ------------------------------------------------------------------ the workflow


def group_for(start_ci_for_pr: Optional[str]) -> str:
    """The workflow's concurrency group for a run, evaluating its one expression by hand.

    Only the exact shape `PREFIX${{ I && format('-start-ci-{0}', I) || '' }}` with I the dispatch input is
    understood; anything else fails here, so a changed expression is looked at, not silently trusted.
    """
    raw = _workflow()["concurrency"]["group"]
    prefix, _, rest = raw.partition("${{")
    assert rest.strip() == "inputs.start_ci_for_pr && format('-start-ci-{0}', inputs.start_ci_for_pr) || '' }}", raw
    return prefix + (f"-start-ci-{start_ci_for_pr}" if start_ci_for_pr else "")


def _workflow() -> Dict[str, Any]:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))


def _sync_step(doc: Dict[str, Any]) -> Dict[str, Any]:
    name = "Merge main into every branch that is behind"
    return next(s for s in doc["jobs"]["sync"]["steps"] if s.get("name") == name)


def interpolates(run_text: str) -> bool:
    return "${{" in run_text


def test_the_dispatch_input_exists_and_reaches_the_script_only_through_env() -> None:
    doc = _workflow()
    inputs = (doc.get(True) or doc["on"])["workflow_dispatch"]["inputs"]
    assert inputs["start_ci_for_pr"]["type"] == "string" and inputs["start_ci_for_pr"]["default"] == ""
    step = _sync_step(doc)
    assert step["env"]["START_CI_FOR_PR"] == "${{ inputs.start_ci_for_pr }}"
    assert '--start-ci-for-pr "${START_CI_FOR_PR}"' in step["run"] and not interpolates(step["run"])


def test_control_an_interpolating_run_step_is_flagged() -> None:
    assert interpolates('python3 x.py --start-ci-for-pr "${{ inputs.start_ci_for_pr }}"')


def test_actions_read_is_the_only_permission_added_and_the_token_use_is_unchanged() -> None:
    doc = _workflow()
    assert doc["permissions"] == {}
    assert doc["jobs"]["sync"]["permissions"] == {
        "contents": "read",
        "pull-requests": "write",
        "issues": "write",
        "actions": "read",
    }
    assert _sync_step(doc)["env"]["AUTOBOT_PUSH_TOKEN"] == "${{ secrets.AUTOBOT_PUSH_TOKEN }}"


def test_the_group_is_untouched_for_every_trigger_without_the_input_and_per_pr_with_it() -> None:
    for without in (None, ""):  # push and schedule carry no input; a dispatch without it is empty
        assert group_for(without) == "sync-branches-with-main"
    assert group_for("21578") == "sync-branches-with-main-start-ci-21578"
    assert group_for("21578") != group_for("21579") != group_for(None)
    assert _workflow()["concurrency"]["cancel-in-progress"] is False


def test_control_main_s_literal_group_would_not_keep_a_request_apart() -> None:
    group = _workflow()["concurrency"]["group"]
    assert "start_ci_for_pr" in group, "a plain group lets a later run cancel a queued request"
