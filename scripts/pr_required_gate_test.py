# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for scripts/pr_required_gate.py (#15995).

Each case below is a state that produced a wrong merge decision on 2026-09-07, not
a hypothetical. The fetch layer WAS deliberately not exercised, on the argument that the defects
were all in interpretation. Review found three that were not, and the argument was
the reason nobody looked: `--paginate` without `--slurp` emits one JSON document
per page, so `json.loads` would have raised the day a list exceeded a page -- and
the singular `/status` endpoint caps at 30 silently, reporting a required context
past the cap as never-run. **"The interesting failures are all in layer X" is a
claim about where to look, and it reads as a reason not to look anywhere else.**
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from pr_required_gate import (  # noqa: E402
    _all_pages,
    _report,
    _required_contexts,
    latest_per_name,
    verdict,
)


def test_a_superseded_cancelled_before_a_success_reads_green():
    """The bug that reported two clean merges as broken.

    Re-pushing leaves `cancelled` runs behind a later `success` for the same name.
    Taking the last element of an unordered response inverts the answer.
    """
    runs = [
        {"name": "code-quality", "started_at": "2026-09-07T16:17:39Z", "conclusion": "cancelled"},
        {"name": "code-quality", "started_at": "2026-09-07T17:35:44Z", "conclusion": "success"},
        {"name": "code-quality", "started_at": "2026-09-07T17:19:30Z", "conclusion": "cancelled"},
    ]
    assert latest_per_name(runs) == {"code-quality": "success"}
    assert verdict(["code-quality"], latest_per_name(runs))["verdict"] == "CONTEXTS-GREEN"


def test_the_newest_run_losing_is_reported_not_hidden():
    """Contrast: newest-wins must report a genuine regression, not only excuse a stale failure."""
    runs = [
        {"name": "code-quality", "started_at": "2026-09-07T16:00:00Z", "conclusion": "success"},
        {"name": "code-quality", "started_at": "2026-09-07T17:00:00Z", "conclusion": "failure"},
    ]
    result = verdict(["code-quality"], latest_per_name(runs))
    assert result["verdict"] == "BLOCKED"
    assert result["not_green"] == [{"context": "code-quality", "state": "failure"}]


def test_a_legacy_commit_status_counts_as_reported():
    """Some required contexts are the old kind; treating them as unreported is the mirror bug.

    Legacy statuses carry `context`/`state`, check-runs carry `name`/`conclusion`.
    """
    observed = latest_per_name(
        [
            {"name": "code-quality", "started_at": "2026-09-07T17:00:00Z", "conclusion": "success"},
            {"context": "smoke-test", "created_at": "2026-09-07T17:00:00Z", "state": "success"},
        ]
    )
    assert observed == {"code-quality": "success", "smoke-test": "success"}
    assert verdict(["code-quality", "smoke-test"], observed)["verdict"] == "CONTEXTS-GREEN"


def test_never_reported_is_not_the_same_output_as_not_green():
    """The distinction the exit code cannot carry: needs waiting vs needs work."""
    observed = {"code-quality": "failure"}
    result = verdict(["code-quality", "api-wiring"], observed)
    assert result["never_reported"] == ["api-wiring"]
    assert result["not_green"] == [{"context": "code-quality", "state": "failure"}]
    assert result["verdict"] == "BLOCKED"


def test_an_empty_observation_blocks_rather_than_passing():
    """A conflicted or un-started PR produces NO contexts and reads `pending=0 fail=0`.

    This is the state that motivated the tool: a histogram calls it green.

    It BLOCKS rather than pends because it is ambiguous between "has not started"
    and "will never start" -- a conflicted branch produces zero contexts and waits
    forever. Only looking tells them apart, so the verdict must send someone to
    look. (An earlier revision made this PENDING and this test caught it.)
    """
    result = verdict(["code-quality", "api-wiring", "smoke-test"], {})
    assert result["verdict"] == "BLOCKED"
    assert len(result["never_reported"]) == 3
    assert result["not_green"] == []


def test_skipped_is_acceptable_but_pending_is_not():
    """`skipped` is a real conclusion from path-filtered shims; `pending` is not a verdict."""
    assert verdict(["a"], {"a": "skipped"})["verdict"] == "CONTEXTS-GREEN"
    assert verdict(["a"], {"a": "pending"})["verdict"] != "CONTEXTS-GREEN"


def test_a_running_check_is_not_reported_as_a_failure():
    """The defect this tool's FIRST version had, caught by running it (#15995).

    `pending` in the `not_green` bucket merges "CI is still working" with "CI
    disagreed with you" -- the same conflation the tool exists to prevent between
    `never_reported` and `not_green`, one bucket over. A reader seeing
    `not_green=6` on a PR whose checks are simply still running goes looking for
    six broken things.
    """
    result = verdict(["a", "b"], {"a": "pending", "b": "in_progress"})
    assert result["verdict"] == "PENDING"
    assert result["not_green"] == []
    assert [e["context"] for e in result["running"]] == ["a", "b"]


def test_a_real_failure_still_blocks_even_while_others_run():
    """Contrast: PENDING must not swallow a genuine failure that has already landed."""
    result = verdict(["a", "b"], {"a": "pending", "b": "failure"})
    assert result["verdict"] == "BLOCKED"
    assert result["not_green"] == [{"context": "b", "state": "failure"}]
    assert [e["context"] for e in result["running"]] == ["a"]


def test_the_required_population_is_an_input_not_a_constant():
    """AC: the population is read from branch protection, never carried in the tool.

    Asserted structurally -- `verdict` cannot answer without being given the list,
    so no hardcoded set can drift out of date with the protection rules.
    """
    # With no required contexts the required set is vacuously satisfied -- and the
    # failing check is still surfaced, because "nothing is required" is not
    # "nothing is wrong".
    empty = verdict([], {"anything": "failure"})
    assert empty["not_green"] == []
    assert empty["failing_unrequired"] == [{"context": "anything", "state": "failure"}]
    # And the population genuinely comes from the argument: the same observation
    # with that context REQUIRED moves it from surfaced-aside to blocking.
    assert verdict(["anything"], {"anything": "failure"})["verdict"] == "BLOCKED"
    assert verdict(["x"], {})["never_reported"] == ["x"]


def test_a_failing_check_outside_the_required_list_is_surfaced():
    """The defect that nearly landed #15972 with three failing test shards.

    `python-suite` is not in branch protection's list, so GitHub merges past it --
    but a failing test is a failing test. Answering only "are the required
    contexts green" is a narrower question than "is this safe to merge", and a
    verdict a reader treats as a merge decision must not hide the difference.
    """
    observed = {"code-quality": "success", "python-suite shard 8/12": "failure"}
    result = verdict(["code-quality"], observed)
    assert result["verdict"] == "GREEN-BUT-OTHERS-FAILING"
    assert result["not_green"] == []
    assert result["failing_unrequired"] == [{"context": "python-suite shard 8/12", "state": "failure"}]


def test_a_running_unrequired_check_is_not_reported_as_failing():
    """Contrast: still-going must not be reported as failed.

    It does block the green verdict (see below) -- but it lands in
    `running_unrequired`, never in `failing_unrequired`. Confusing the two would
    send a reader hunting for a broken test that does not exist.
    """
    result = verdict(["code-quality"], {"code-quality": "success", "extra": "pending"})
    assert result["failing_unrequired"] == []
    assert result["verdict"] == "GREEN-BUT-OTHERS-RUNNING"


def test_a_running_unrequired_check_blocks_the_green_verdict():
    """The defect that nearly merged #15962 with eight test shards still running.

    An earlier revision surfaced *failing* unrequired checks and treated *pending*
    ones as absent -- so a PR read CONTEXTS-GREEN while eight `python-suite`
    shards were pending, including the shard that had turned base red an hour
    earlier. An unfinished check cannot have failed yet, which is precisely why it
    must not be read as having passed.
    """
    observed = {"code-quality": "success", "python-suite shard 6/12": "pending"}
    result = verdict(["code-quality"], observed)
    assert result["verdict"] == "GREEN-BUT-OTHERS-RUNNING"
    assert result["failing_unrequired"] == []
    assert [e["context"] for e in result["running_unrequired"]] == ["python-suite shard 6/12"]


def test_a_failing_unrequired_check_outranks_a_running_one():
    """Contrast: a known failure must not be softened by something else still going."""
    observed = {"a": "failure", "b": "pending"}
    result = verdict([], observed)
    assert result["verdict"] == "GREEN-BUT-OTHERS-FAILING"
    assert [e["context"] for e in result["failing_unrequired"]] == ["a"]
    assert [e["context"] for e in result["running_unrequired"]] == ["b"]


def test_a_generator_of_required_contexts_is_not_silently_empty():
    """`required` is typed Iterable and read twice; a generator must not vanish.

    An exhausted iterator answers "no required contexts", which reclassifies every
    failing required check as unrequired and reads as green -- the defect this
    tool was written to catch, occurring inside the tool. The contrast is the
    assertion: the same states passed as a list must give the same verdict.
    """
    required = ["smoke-test", "code-quality"]
    observed = {"smoke-test": "success", "code-quality": "failure"}
    from_list = verdict(list(required), observed)
    from_generator = verdict((name for name in required), observed)
    assert from_generator["verdict"] == from_list["verdict"] == "BLOCKED"
    assert from_generator["not_green"] == from_list["not_green"]
    assert (
        from_generator["failing_unrequired"] == []
    ), "a required check was reclassified as unrequired -- the iterator was exhausted"


def test_a_green_check_run_cannot_hide_a_red_commit_status():
    """GitHub evaluates the two kinds SEPARATELY; one dict keyed by name merged them.

    Keying only on the context name let a passing observation of one kind stand in
    for a failing observation of the other, and the tool printed CONTEXTS-GREEN
    while the merge button stayed red -- collapsing two independent verdicts into
    one key, which is the same error as a histogram collapsing three states into
    `pending=0, fail=0`.
    """
    runs = [{"name": "code-quality", "started_at": "2026-09-08T01:00:00Z", "conclusion": "success"}]
    statuses = [{"context": "code-quality", "created_at": "2026-09-08T02:00:00Z", "state": "failure"}]
    observed = latest_per_name(runs, statuses)
    assert observed["code-quality"] == "failure", "a passing check run masked a failing commit status of the same name"
    assert verdict(["code-quality"], observed)["verdict"] == "BLOCKED"


def test_the_worst_wins_across_sources_but_the_newest_wins_within_one():
    """The contrast. Two rules, and taking either one for both breaks the other.

    If `worst across` also applied *within* a source, a superseded `cancelled`
    would outrank the `success` that replaced it and every re-pushed PR would read
    as failing -- the bug this tool's first version had, in reverse.
    """
    runs = [
        {"name": "smoke-test", "started_at": "2026-09-08T01:00:00Z", "conclusion": "cancelled"},
        {"name": "smoke-test", "started_at": "2026-09-08T03:00:00Z", "conclusion": "success"},
    ]
    statuses = [{"context": "smoke-test", "created_at": "2026-09-08T02:00:00Z", "state": "success"}]
    assert latest_per_name(runs, statuses)["smoke-test"] == "success"


def test_a_requirement_declared_only_under_checks_is_still_required():
    """`contexts` is the deprecated mirror of `checks` and can lag behind it.

    A requirement invisible to the instrument reads as satisfied, which is the
    failure this whole tool exists to prevent -- so it must not be reachable
    through the tool's own reading of branch protection.
    """
    protection = {
        "required_status_checks": {
            "contexts": ["code-quality"],
            "checks": [
                {"context": "code-quality", "app_id": 15368},
                {"context": "migration-matrix", "app_id": None},
            ],
        }
    }
    required, app_pinned = _required_contexts(protection)
    assert required == ["code-quality", "migration-matrix"]
    assert app_pinned == ["code-quality"], (
        "a context pinned to a specific app was not reported as unverifiable; this "
        "tool matches on name alone and must say so rather than imply it checked"
    )


def test_multiple_pages_are_flattened_rather_than_rejected(monkeypatch):
    """`--paginate` alone concatenates one document per page and `json.loads` dies.

    The failure is a crash, not a wrong answer, which is why it never showed: every
    list so far fit in one page. A fixture with two pages is the only way to see it
    before the day the tree grows past 100 checks.
    """
    import pr_required_gate

    pages = '[{"check_runs": [{"name": "a"}]}, {"check_runs": [{"name": "b"}]}]'
    monkeypatch.setattr(pr_required_gate, "_gh", lambda *args: pages)
    assert _all_pages("ignored", "check_runs") == [{"name": "a"}, {"name": "b"}]


def test_no_running_context_is_dropped_from_the_text_report(capsys):
    """The `[:3]` this replaces was the tool's own defect in miniature.

    A display that silently drops rows reports fewer blockers than exist, which is
    exactly the reading error -- "nothing else is running" -- that this bucket was
    added to prevent. #16014 had thirteen.
    """
    result = {
        "head": "0123456789abcdef",
        "verdict": "GREEN-BUT-OTHERS-RUNNING",
        "never_reported": [],
        "running": [],
        "not_green": [],
        "failing_unrequired": [],
        "running_unrequired": [{"context": f"shard {n}/12", "state": "pending"} for n in range(1, 13)],
        "app_pinned": [],
    }
    _report(16014, result)
    printed = capsys.readouterr().out
    for n in range(1, 13):
        assert f"shard {n}/12" in printed, f"shard {n} was dropped from the report"
    assert printed.count("running (not required)") == 12


def test_a_skip_never_overrides_a_conclusive_result_whatever_the_order():
    """Two workflows, one context name — newest-wins reported the shim (#16040).

    A path-filtered shim can land `skipped` AFTER a real `failure` on the same
    commit. Newest-wins then reported green while the merge button stayed red,
    which is GitHub disagreeing with the tool built to predict it.

    A skip means "this publisher declined to run here". It cannot invalidate a
    failure that already happened on the same commit, and the ordering carries no
    information about which publisher is authoritative.
    """
    after = [
        {"name": "c", "started_at": "10:00", "conclusion": "failure"},
        {"name": "c", "started_at": "10:05", "conclusion": "skipped"},
    ]
    before = [
        {"name": "c", "started_at": "10:00", "conclusion": "skipped"},
        {"name": "c", "started_at": "10:05", "conclusion": "failure"},
    ]
    assert latest_per_name(after)["c"] == "failure"
    assert latest_per_name(before)["c"] == "failure"


def test_supersession_is_still_newest_wins():
    """The contrast, and the reason this could not be fixed with `worst wins`.

    A re-push leaves `cancelled` behind a later `success`, and a re-run leaves
    `failure` behind a later `success`. Both must report the newer result — so
    the rule cannot be "take the worst", only "a skip is not an answer when a
    real one exists".
    """
    superseded = [
        {"name": "c", "started_at": "10:00", "conclusion": "cancelled"},
        {"name": "c", "started_at": "10:05", "conclusion": "success"},
    ]
    rerun = [
        {"name": "c", "started_at": "10:00", "conclusion": "failure"},
        {"name": "c", "started_at": "10:05", "conclusion": "success"},
    ]
    assert latest_per_name(superseded)["c"] == "success"
    assert latest_per_name(rerun)["c"] == "success"


def test_a_skip_is_still_the_answer_when_nothing_else_reported():
    """A path-filtered context that only ever skips is legitimately green.

    Without this, "a skip is never authoritative" becomes "a skip is always
    ignored", and every path-filtered required context reads as never-reported.
    """
    assert latest_per_name([{"name": "c", "started_at": "10:00", "conclusion": "skipped"}])["c"] == "skipped"


def test_a_merged_pull_request_is_not_reported_as_mergeable(monkeypatch):
    """A merged PR's required contexts are all green — its checks finished first.

    So the verdict was true and useless, and read as clearance it says "ready to
    merge" about something already merged. I did exactly that and told another
    session to merge alongside three PRs that had landed hours earlier (#16040).

    Fourth state this tool could not see, and not a fourth bug: pending in no
    bucket, a conflicted PR with no runs, a superseded `cancelled`, a merged PR.
    One property — a check that enumerates conditions is blind to the ones it
    does not enumerate, and every blind spot reads as success.
    """
    import pr_required_gate as gate

    monkeypatch.setattr(
        gate,
        "_fetch",
        lambda pr, repo, base: {
            "required": ["smoke-test"],
            "app_pinned": [],
            "observed": {"smoke-test": "success"},
            "head": "0" * 40,
            "pr_state": "MERGED",
        },
    )
    emitted: list[str] = []
    monkeypatch.setattr(gate, "_emit", emitted.append)

    assert gate.main(["123"]) == 1, "a merged PR must not exit 0"
    assert any("NOT-OPEN (MERGED)" in line for line in emitted), emitted


def test_an_open_pull_request_with_green_contexts_is_still_green(monkeypatch):
    """The contrast. Without it, "check the state" is satisfied by failing everything."""
    import pr_required_gate as gate

    monkeypatch.setattr(
        gate,
        "_fetch",
        lambda pr, repo, base: {
            "required": ["smoke-test"],
            "app_pinned": [],
            "observed": {"smoke-test": "success"},
            "head": "0" * 40,
            "pr_state": "OPEN",
        },
    )
    emitted: list[str] = []
    monkeypatch.setattr(gate, "_emit", emitted.append)

    assert gate.main(["123"]) == 0
    assert any("CONTEXTS-GREEN" in line for line in emitted), emitted


def test_a_conclusive_result_wins_even_when_the_skip_is_seen_first():
    """The API returns runs UNORDERED, which is the only path to the promote branch.

    A newer `skipped` can arrive first in the list while the older `failure`
    arrives second. Without promotion the timestamp comparison keeps the skip —
    so the rule is not "prefer the newest" but "a real result outranks a
    declined one, whichever order they are seen in".

    Found because a mutation that ignored skips entirely passed every other test
    here: the cases I had written all put the conclusive run later in the list,
    so the branch that handles the opposite ordering was never exercised.
    """
    seen_skip_first = [
        {"name": "c", "started_at": "10:05", "conclusion": "skipped"},
        {"name": "c", "started_at": "10:00", "conclusion": "failure"},
    ]
    assert latest_per_name(seen_skip_first)["c"] == "failure"
