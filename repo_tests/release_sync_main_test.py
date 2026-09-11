# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#16246 — one release-sync pull request into main, never merged by a bot.

``sync-main-to-dev.yml`` force-pushes Dev_new_gui to ``release-sync-main`` and
runs ``pipeline-scripts/release_sync_main.py``, weekly and on a confirmed manual
trigger. The properties pinned here are the ones a reviewer cannot see once the
files are long:

* **Exactly one.** A run opens a sync PR only when none is open, counting PRs
  into main from the release branch AND from the trunk. With two already open
  it updates the oldest and opens nothing — "fixing" duplicates by adding a
  third is the failure this guards.
* **Never merges.** The sync must land as a merge commit (``main`` holds
  #15326's merge commit, which Dev_new_gui lacks), and that call is the owner's.
  No request in any path reaches a merge endpoint, and neither the script nor
  the workflow names one.
* **The workflow list is complete.** It is read from both refs' directory
  listings, not the compare, whose file list stops at 300.

A listing or compare that cannot be read raises. Read as "no PR open" it would
open a duplicate; read as "0 commits" it would skip a sync. What happens when
GitHub refuses the PR (#15834) is pinned in ``release_sync_tracking_issue_test.py``.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

import pytest
import yaml
from repo_tests._paths import repo_root
from repo_tests._release_sync_fakes import BASE, HEAD, REPO, SCRIPT, SOURCE, _api, _pull, _run, load_script

_REPO_ROOT = repo_root()
_SCRIPT = SCRIPT
_WORKFLOW = _REPO_ROOT / ".github/workflows/sync-main-to-dev.yml"

PUSH_TOKEN = "${{ secrets.AUTOBOT_PUSH_TOKEN || secrets.GITHUB_TOKEN }}"

# A merge endpoint: `PUT .../pulls/{n}/merge` or `POST .../merges`.
_MERGE_ENDPOINT = re.compile(r"/merges?\b")

SCHEDULED = "on:\n  schedule:\n    - cron: '17 3 * * *'\n  workflow_dispatch:\njobs: {}\n"
SCHEDULED_V2 = "on:\n  schedule:\n    - cron: '18 3 * * *'\njobs: {}\n"
UNSCHEDULED = "on:\n  push:\n    branches: [main]\njobs: {}\n"
UNSCHEDULED_V2 = "on:\n  workflow_dispatch:\njobs: {}\n"


@pytest.fixture(scope="module")
def rs():
    return load_script()


# --------------------------------------------------------------------------
# The decision: create, update, or nothing — and never a second PR.
# --------------------------------------------------------------------------


def test_no_open_pr_with_commits_to_sync_creates_one(rs):
    decision = rs.decide([], 310)
    assert decision.action == rs.ACTION_CREATE
    assert decision.target is None and decision.extras == ()


def test_no_open_pr_and_nothing_to_sync_does_nothing(rs):
    decision = rs.decide([], 0)
    assert decision.action == rs.ACTION_NOTHING
    assert decision.target is None and decision.extras == ()


def test_one_open_pr_is_updated_not_duplicated(rs):
    decision = rs.decide([_pull(12)], 310)
    assert decision.action == rs.ACTION_UPDATE
    assert decision.target == 12 and decision.extras == ()


def test_an_open_pr_is_updated_even_with_nothing_left_to_sync(rs):
    """'Nothing' needs BOTH zero commits and no PR; an open PR's body is kept current."""
    decision = rs.decide([_pull(12)], 0)
    assert decision.action == rs.ACTION_UPDATE and decision.target == 12


@pytest.mark.parametrize("ahead", [0, 1, 310])
def test_two_open_sync_prs_never_create_a_third(rs, ahead):
    decision = rs.decide([_pull(12), _pull(21)], ahead)
    assert decision.action != rs.ACTION_CREATE
    assert decision.action == rs.ACTION_UPDATE
    assert decision.target == 12
    assert decision.extras == (21,)


def test_the_oldest_open_pr_is_updated_whatever_the_listing_order(rs):
    decision = rs.decide([_pull(30), _pull(12), _pull(21)], 5)
    assert decision.target == 12
    assert decision.extras == (21, 30)


def test_negative_commit_count_is_rejected(rs):
    with pytest.raises(ValueError):
        rs.decide([], -1)


def test_a_sync_pr_is_this_repositorys_release_branch_or_trunk_into_the_base(rs):
    heads = {HEAD, SOURCE}
    assert rs.is_sync_pull(_pull(1), REPO, heads, BASE)
    assert rs.is_sync_pull(_pull(2, head=SOURCE), REPO, heads, BASE)
    assert not rs.is_sync_pull(_pull(3, repo="someone/fork"), REPO, heads, BASE)
    assert not rs.is_sync_pull(_pull(4, head="issue-1-x"), REPO, heads, BASE)
    assert not rs.is_sync_pull(_pull(5, base=SOURCE), REPO, heads, BASE)


def test_title_is_the_agreed_one(rs):
    assert rs.SYNC_TITLE == "release: sync main from Dev_new_gui"


def test_the_default_head_is_the_workflows_release_branch(rs):
    assert rs.DEFAULT_HEAD == HEAD and rs.DEFAULT_SOURCE == SOURCE and rs.DEFAULT_BASE == BASE


# --------------------------------------------------------------------------
# One run, end to end, against a recorded fake: at most one write.
# --------------------------------------------------------------------------


def test_run_opens_exactly_one_pr_when_none_is_open(rs):
    api = _api([], 310)
    assert _run(rs, api) == 0
    posts = api.writes("POST")
    assert len(posts) == 1
    _, payload = posts[0]
    assert payload["title"] == rs.SYNC_TITLE
    assert (payload["head"], payload["base"]) == (HEAD, BASE)
    assert "310 commits" in payload["body"]
    assert api.writes("PATCH") == []


def test_run_with_two_open_prs_opens_none_and_updates_only_the_oldest(rs):
    api = _api([_pull(21, body=rs.BODY_MARKER), _pull(12, body=rs.BODY_MARKER)], 310)
    assert _run(rs, api) == 1, "duplicates must redden the run"
    assert api.writes("POST") == [], "a run with sync PRs open must never open another"
    patches = api.writes("PATCH")
    assert [path for path, _ in patches] == [f"/repos/{REPO}/pulls/12"]
    assert set(patches[0][1]) == {"body"}, "the update rewrites the body and nothing else"


def test_a_hand_opened_sync_from_the_trunk_is_counted_and_its_body_left_alone(rs):
    api = _api([_pull(9), _pull(5, head=SOURCE)], 310)
    assert _run(rs, api) == 1
    assert api.writes("POST") == []
    assert api.writes("PATCH") == [], "a hand-opened sync PR keeps the body its author wrote"


@pytest.mark.parametrize("generated", [True, False])
def test_only_a_body_this_tool_wrote_is_ever_rewritten(rs, generated):
    hand_written = f"Bootstrap sync, opened by hand. Adds `{rs.OPENED_BY}`."
    api = _api([_pull(12, body=rs.BODY_MARKER + "\nstale" if generated else hand_written)], 310)
    assert _run(rs, api) == 0
    assert bool(api.writes("PATCH")) is generated, "a hand-written body is never PATCHed, even one naming the workflow"
    assert api.writes("POST") == []


def test_other_prs_into_the_base_are_not_sync_prs(rs):
    api = _api([_pull(3, head="issue-1-x"), _pull(4, repo="someone/fork")], 310)
    assert _run(rs, api) == 0
    assert len(api.writes("POST")) == 1 and api.writes("PATCH") == []


def test_run_does_not_rewrite_a_body_that_is_already_current(rs):
    current = rs.build_body(310, [], SOURCE, BASE)
    api = _api([_pull(12, body=current)], 310)
    assert _run(rs, api) == 0
    assert api.writes("PATCH") == [] and api.writes("POST") == []


def test_dry_run_writes_nothing(rs):
    for pulls in ([], [_pull(12)]):
        api = _api(pulls, 310)
        _run(rs, api, dry_run=True)
        assert api.writes("POST") == [] and api.writes("PATCH") == []


def test_nothing_to_sync_reads_no_workflows_and_writes_nothing(rs):
    api = _api([], 0)
    assert _run(rs, api) == 0
    assert [verb for verb, _, _ in api.calls if verb != "GET"] == []
    assert not any("contents/" in path for _, path, _ in api.calls)


def test_the_count_is_read_from_the_trunk_not_the_release_branch(rs):
    """The release branch is deleted when the sync PR merges; a compare against it is a 404."""
    api = _api([], 0)
    _run(rs, api)
    compares = [path for _, path, _ in api.calls if "compare/" in path]
    assert compares and all(f"{BASE}...{SOURCE}" in path for path in compares)


def test_unreadable_pr_listing_never_reads_as_no_pr_open(rs):
    api = _api([], 310)
    api.routes[0] = ("GET", "/pulls?", (403, {"message": "rate limited"}))
    with pytest.raises(rs.WatchdogApiError):
        _run(rs, api)
    assert api.writes("POST") == []


def test_a_full_page_of_open_prs_is_not_read_as_the_whole_listing(rs):
    api = _api([_pull(n, head="issue-x") for n in range(1, 101)], 310)
    with pytest.raises(rs.WatchdogApiError):
        _run(rs, api)
    assert api.writes("POST") == []


def test_unusable_compare_never_reads_as_nothing_to_sync(rs):
    api = _api([], 310)
    api.routes[1] = ("GET", f"compare/{BASE}...{SOURCE}", (200, {"message": "no ahead_by"}))
    with pytest.raises(rs.WatchdogApiError):
        _run(rs, api)


def test_refusal_hint_links_the_compare_page_or_names_the_branch(rs):
    linked = rs.refusal_hint("https://example.invalid/", REPO, BASE, HEAD)
    assert linked.endswith(f"https://example.invalid/{REPO}/compare/{BASE}...{HEAD}?expand=1")
    unlinked = rs.refusal_hint("", REPO, BASE, HEAD)
    assert HEAD in unlinked and BASE in unlinked and "http" not in unlinked


def test_any_other_create_failure_is_an_error(rs):
    api = _api([], 310)
    api.routes[2] = ("POST", f"/repos/{REPO}/pulls", (422, {"message": "Validation Failed"}))
    with pytest.raises(rs.WatchdogApiError):
        _run(rs, api)


# --------------------------------------------------------------------------
# It never merges.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("pulls, ahead", [([], 310), ([_pull(12)], 310), ([_pull(12), _pull(21)], 3)])
def test_no_request_ever_reaches_a_merge_endpoint(rs, pulls, ahead):
    api = _api(pulls, ahead, {".github/workflows/a.yml": SCHEDULED})
    _run(rs, api)
    assert api.calls, "the fake recorded nothing, so this test inspected nothing"
    for verb, path, _ in api.calls:
        assert verb != "PUT", f"{verb} {path}: the only PUT on a pull request is the merge"
        assert not _MERGE_ENDPOINT.search(path.split("?", 1)[0]), f"{verb} {path} is a merge endpoint"


def test_script_source_names_no_merge_endpoint():
    source = _SCRIPT.read_text(encoding="utf-8")
    hit = _MERGE_ENDPOINT.search(source)
    assert hit is None, f"release_sync_main.py names a merge endpoint: {hit.group(0)!r} (#16246)"
    assert '"PUT"' not in source, "release_sync_main.py issues a PUT; merging a PR is a PUT"


# --------------------------------------------------------------------------
# The body.
# --------------------------------------------------------------------------


def test_body_states_the_commit_count(rs):
    assert "**310 commits**" in rs.build_body(310, [], SOURCE, BASE)


def test_body_instructs_a_merge_commit_and_never_a_squash(rs):
    body = rs.build_body(310, [], SOURCE, BASE)
    assert "gh pr merge --merge" in body
    assert "Never `--squash`" in body
    assert "#15326" in body, "the body must say WHY: main holds #15326's merge commit"
    assert "re-conflict" in body, "the body must say what a squash costs"


def test_body_lists_each_scheduled_workflow_with_its_transition(rs):
    changes = [
        rs.ScheduledChange(".github/workflows/new.yml", rs.STATE_ACTIVATES),
        rs.ScheduledChange(".github/workflows/moved.yml", rs.STATE_CHANGES),
        rs.ScheduledChange(".github/workflows/gone.yml", rs.STATE_STOPS),
    ]
    body = rs.build_body(310, changes, SOURCE, BASE)
    for change in changes:
        assert f"`{change.path}` ({change.state})" in body


def test_body_says_none_when_no_schedule_changes(rs):
    body = rs.build_body(310, [], SOURCE, BASE)
    section = body.split("## Scheduled workflows", 1)[1].split("\n## ", 1)[0]
    assert "None:" in section


def test_body_uses_the_pr_template_headings(rs):
    body = rs.build_body(310, [], SOURCE, BASE)
    for heading in ("## Thinking Path", "## Verification", "## Model Used", "## Issue Link"):
        assert heading in body, f"sync PR body lacks {heading!r}"


def test_body_names_the_workflow_that_opened_it_and_leads_with_the_marker(rs):
    body = rs.build_body(310, [], SOURCE, BASE)
    assert "sync-main-to-dev.yml" in body and body.startswith(rs.BODY_MARKER)


# --------------------------------------------------------------------------
# Which scheduled workflows the sync activates, changes or stops.
# --------------------------------------------------------------------------


def test_block_schedule_is_detected(rs):
    assert rs.declares_schedule(SCHEDULED)


def test_commented_out_schedule_is_not_live(rs):
    text = "on:\n  workflow_dispatch:\n  # schedule:\n  #   - cron: '20 3 * * *'\njobs: {}\n"
    assert not rs.declares_schedule(text)


def test_workflow_without_schedule_is_not_scheduled(rs):
    assert not rs.declares_schedule(UNSCHEDULED)


def test_schedule_key_outside_the_on_block_is_ignored(rs):
    text = "on:\n  push:\njobs:\n  a:\n    schedule:\n      cron: '1 2 * * *'\n"
    assert not rs.declares_schedule(text)


def test_quoted_on_key_flow_form_and_trailing_comment_are_handled(rs):
    assert rs.declares_schedule("'on':\n  schedule:\n    - cron: '1 2 * * *'  # nightly\n")
    assert rs.declares_schedule("on: {schedule: [{cron: '1 2 * * *'}]}\njobs: {}\n")


def test_detector_reads_a_real_workflows_schedule(rs):
    """Reach: the synthetic cases above prove nothing if real workflow text defeats the parse."""
    assert rs.declares_schedule(_WORKFLOW.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "on_head, on_base, expected",
    [
        (True, None, "activates"),
        (True, False, "activates"),
        (True, True, "changes"),
        (False, True, "stops"),
        (None, True, "stops"),
        (False, False, None),
        (None, False, None),
        (False, None, None),
    ],
)
def test_schedule_transitions(rs, on_head, on_base, expected):
    assert rs.schedule_transition(on_head, on_base) == expected


def test_differing_workflows_covers_added_changed_and_deleted_but_not_identical(rs):
    head = {"a.yml": "1", "b.yml": "2", "same.yml": "s"}
    base = {"b.yml": "3", "same.yml": "s", "gone.yml": "4"}
    assert rs.differing_workflows(head, base) == ["a.yml", "b.yml", "gone.yml"]


def test_workflow_list_comes_from_both_directory_listings_not_the_compare(rs):
    head_files = {
        ".github/workflows/new.yml": SCHEDULED,
        ".github/workflows/moved.yml": SCHEDULED_V2,
        ".github/workflows/plain.yml": UNSCHEDULED,
        ".github/workflows/same.yml": SCHEDULED,
    }
    base_files = {
        ".github/workflows/moved.yml": SCHEDULED,
        ".github/workflows/plain.yml": UNSCHEDULED_V2,
        ".github/workflows/same.yml": SCHEDULED,
        ".github/workflows/gone.yml": SCHEDULED,
    }
    api = _api([], 310, head_files, base_files)
    changes = rs.scheduled_changes(api, SOURCE, BASE)
    assert [(c.path.rsplit("/", 1)[-1], c.state) for c in changes] == [
        ("gone.yml", "stops"),
        ("moved.yml", "changes"),
        ("new.yml", "activates"),
    ]
    paths = [path for _, path, _ in api.calls]
    assert not any("compare/" in path for path in paths), "the compare's file list stops at 300"
    assert not any("same.yml" in path for path in paths), "an identical blob needs no fetch"


# --------------------------------------------------------------------------
# The workflow: sync-main-to-dev.yml, the one release-sync mechanism.
# --------------------------------------------------------------------------


def _spec() -> Dict[str, Any]:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))


def _triggers() -> Dict[str, Any]:
    spec = _spec()
    # PyYAML parses a bare `on:` key as the boolean True.
    return spec.get("on", spec.get(True)) or {}


def _job() -> Dict[str, Any]:
    return _spec()["jobs"]["sync"]


def _step(predicate) -> Dict[str, Any]:
    matches = [step for step in _job()["steps"] if predicate(step)]
    assert len(matches) == 1, f"expected exactly one matching step, found {len(matches)}"
    return matches[0]


def _shell_bodies() -> List[str]:
    """Every `run:` script in the workflow, with shell comments removed."""
    bodies = []
    for job in _spec()["jobs"].values():
        for step in job.get("steps", []):
            if "run" in step:
                bodies.append("\n".join(line for line in step["run"].splitlines() if not line.lstrip().startswith("#")))
    return bodies


def test_workflow_and_script_exist():
    assert _WORKFLOW.is_file(), f"{_WORKFLOW.relative_to(_REPO_ROOT)} is missing (#16246)"
    assert _SCRIPT.is_file(), f"{_SCRIPT.relative_to(_REPO_ROOT)} is missing (#16246)"


def test_triggers_are_a_weekly_schedule_and_manual_dispatch_only():
    triggers = _triggers()
    assert set(triggers) == {"schedule", "workflow_dispatch"}, f"unexpected triggers: {sorted(triggers)}"
    crons = [entry["cron"] for entry in triggers["schedule"]]
    assert len(crons) == 1, f"expected one weekly cron, got {crons}"
    minute, hour, day_of_month, month, day_of_week = crons[0].split()
    assert minute.isdigit() and int(minute) != 0, "pick an off-peak minute, not the top of the hour"
    assert hour.isdigit(), f"a weekly run fires at one hour, got {hour!r}"
    assert (day_of_month, month) == ("*", "*") and day_of_week.isdigit(), f"not weekly: {crons[0]!r}"


def test_no_pull_request_or_push_trigger():
    triggers = _triggers()
    for event in ("pull_request", "pull_request_target", "push"):
        assert event not in triggers, f"sync-main-to-dev.yml must not trigger on `{event}`"


def test_manual_runs_still_need_the_release_confirmation_and_scheduled_runs_skip_it():
    confirm = _triggers()["workflow_dispatch"]["inputs"]["confirm"]
    assert confirm.get("required") is True
    gate = _step(lambda step: step.get("name") == "Validate confirmation")
    condition = str(gate.get("if", ""))
    assert "github.event_name == 'workflow_dispatch'" in condition, "a scheduled run has no input to confirm"
    assert "inputs.confirm != 'release'" in condition, "manual runs must still type 'release'"


def test_permissions_are_the_release_push_the_pr_and_the_tracking_issue_only():
    assert _spec().get("permissions") in (None, {}), "no workflow-level grant beyond the job's"
    expected = {"contents": "write", "pull-requests": "write", "issues": "write"}
    assert _job()["permissions"] == expected, "issues: write is explicit: the default token is read-only (#15834)"


def test_runs_one_at_a_time():
    concurrency = _spec().get("concurrency") or {}
    assert concurrency.get("group"), "two overlapping runs could each open a sync PR"
    assert concurrency.get("cancel-in-progress") is False, "a run mid-write must finish"


def test_workflow_runs_the_script_against_the_release_branch():
    joined = "\n".join(_shell_bodies())
    assert joined, "no `run:` scripts parsed out of the workflow; the guards below inspect nothing"
    assert "pipeline-scripts/release_sync_main.py" in joined
    assert '--head "$SYNC_BRANCH"' in joined, "the script must count PRs from the branch this workflow pushes"
    assert _job()["env"]["SYNC_BRANCH"] == HEAD


def test_the_pr_is_opened_by_the_script_alone():
    joined = "\n".join(_shell_bodies())
    for forbidden in ("gh pr create", "gh pr edit", "gh api"):
        assert forbidden not in joined, f"`{forbidden}` in the workflow is a second PR mechanism (#16246)"


def test_the_push_and_the_pr_prefer_the_push_token():
    runner = _step(lambda step: "release_sync_main.py" in step.get("run", ""))
    assert runner["env"]["GITHUB_TOKEN"] == PUSH_TOKEN
    checkout = _step(lambda step: str(step.get("uses", "")).startswith("actions/checkout@"))
    assert checkout["with"]["token"] == PUSH_TOKEN


def test_the_divergence_guard_is_kept():
    joined = "\n".join(_shell_bodies())
    assert "--no-merges" in joined, "#13974: DIVERGENT counts non-merge commits only on main"
    assert '"$DIVERGENT" != "0"' in joined, "#13974: work committed straight to main blocks the sync"


def test_workflow_never_merges():
    joined = "\n".join(_shell_bodies())
    for forbidden in ("gh pr merge", "git merge"):
        assert forbidden not in joined, f"sync-main-to-dev.yml runs `{forbidden}` (#16246)"
    assert not _MERGE_ENDPOINT.search(joined), "sync-main-to-dev.yml calls a merge endpoint"
    for step in _job()["steps"]:
        assert "merge" not in str(step.get("uses", "")).lower(), f"merge action: {step['uses']}"
    pushes = [line for line in joined.splitlines() if "git push" in line]
    assert pushes, "the release-branch push is gone; the PR head would never move"
    for line in pushes:
        assert "refs/heads/$SYNC_BRANCH" in line, f"push to something other than the release branch: {line!r}"


def test_exit_status_is_never_read_after_an_unguarded_command():
    """Steps run under `bash -e`: a bare `rc=$?` line is never reached on failure (#16237)."""
    for body in _shell_bodies():
        for line in body.splitlines():
            if "$?" in line:
                assert "|| rc=$?" in line or "set +e" in body, f"unguarded exit-status read: {line.strip()!r}"
