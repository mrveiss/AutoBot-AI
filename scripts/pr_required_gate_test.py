# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for scripts/pr_required_gate.py (#15995).

Each case below is a state that produced a wrong merge decision on 2026-09-07, not
a hypothetical. The fetch layer is deliberately not exercised: the defects were all
in *interpretation*, so the logic is pure and the tests feed it the shapes the API
actually returns.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from pr_required_gate import latest_per_name, verdict  # noqa: E402


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
    assert result["failing_unrequired"] == [
        {"context": "python-suite shard 8/12", "state": "failure"}
    ]


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
    assert from_generator["failing_unrequired"] == [], (
        "a required check was reclassified as unrequired -- the iterator was exhausted"
    )
