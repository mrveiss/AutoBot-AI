# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for the check-run status helper (#16120).

Each test targets one of the four ways the raw endpoint has produced a wrong
verdict, and each is written so that REMOVING the behaviour makes it fail --
rather than asserting that the code does what it does.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_run_status import (  # noqa: E402
    all_pages,
    check_run_status,
    latest_per_name,
    rank,
    split_by_state,
)


def _run(name: str, started: str, conclusion: str | None, status: str = "completed") -> dict:
    return {"name": name, "started_at": started, "conclusion": conclusion, "status": status}


def test_a_superseded_failure_does_not_become_the_verdict() -> None:
    """#16120 defect 1: the response carries every run, not the latest per name.

    This is the real shape observed on one commit -- `code-quality` failing at
    07:54 and succeeding at 09:10. Reading the list without grouping reports the
    failure, and a phantom red costs the same investigation as a real one.

    Remove the `started_at` comparison in `_latest_within` and this fails.
    """
    runs = [
        _run("code-quality", "2026-09-09T07:54:14Z", "failure"),
        _run("code-quality", "2026-09-09T09:10:02Z", "success"),
    ]
    assert latest_per_name(runs) == {"code-quality": "success"}


def test_order_in_the_response_does_not_decide_the_verdict() -> None:
    """The API does not promise ordering, so the same runs reversed must agree.

    Taking the last element of an unordered response is the specific mistake;
    this fails if the implementation ever relies on position.
    """
    early = _run("python-suite", "2026-09-09T07:00:00Z", "failure")
    late = _run("python-suite", "2026-09-09T08:00:00Z", "success")
    assert latest_per_name([early, late]) == latest_per_name([late, early])


def test_a_later_skip_never_overrides_an_earlier_failure() -> None:
    """#16040: two publishers, one context name.

    A path-filtered shim can land `skipped` AFTER a real `failure` on the same
    commit. Newest-wins alone reports green while the merge button stays red --
    the tool disagreeing with the thing it exists to predict.

    Delete the INCONCLUSIVE guards and this fails while the test above passes,
    which is why both exist.
    """
    runs = [
        _run("docker-smoke", "2026-09-09T07:00:00Z", "failure"),
        _run("docker-smoke", "2026-09-09T08:00:00Z", "skipped"),
    ]
    assert latest_per_name(runs) == {"docker-smoke": "failure"}


def test_a_genuine_rerun_still_clears_an_earlier_failure() -> None:
    """The control for the test above, in the opposite direction.

    A guard that made skips lose could also make every later state lose. Among
    CONCLUSIVE observations newest must still win.
    """
    runs = [
        _run("actionlint", "2026-09-09T07:00:00Z", "failure"),
        _run("actionlint", "2026-09-09T08:00:00Z", "success"),
    ]
    assert latest_per_name(runs) == {"actionlint": "success"}


def test_a_failure_in_one_source_is_not_masked_by_a_pass_in_another() -> None:
    """GitHub evaluates check runs and legacy commit statuses separately.

    One dict keyed by name alone lets a passing observation of one kind hide a
    failing observation of the other. Worst-across-sources is what prevents it.
    """
    check_runs = [_run("ci", "2026-09-09T08:00:00Z", "success")]
    statuses = [{"context": "ci", "created_at": "2026-09-09T09:00:00Z", "state": "failure"}]
    assert latest_per_name(check_runs, statuses) == {"ci": "failure"}


def test_pagination_reaches_past_the_first_page(monkeypatch: pytest.MonkeyPatch) -> None:
    """#16120 defect 2: `per_page=100` without `--paginate` truncates silently.

    Measured on one real PR: 100 runs on a single page, 111 paginated, and the
    eleven dropped were hiding a not-green required context. The fixture puts
    the only failure on the SECOND page, so a single-page read reports green.

    Remove `--paginate` from `all_pages` and this fails.
    """
    page_one = {"check_runs": [_run(f"shard {i}", "2026-09-09T08:00:00Z", "success") for i in range(100)]}
    page_two = {"check_runs": [_run("startup-import-smoke", "2026-09-09T08:00:00Z", "cancelled")]}

    captured: dict[str, list[str]] = {}

    class _Result:
        stdout = json.dumps([page_one, page_two])

    def _fake_run(argv, **_kwargs):  # type: ignore[no-untyped-def]
        captured["argv"] = argv
        return _Result()

    monkeypatch.setattr("check_run_status.subprocess.run", _fake_run)

    observed = check_run_status("owner/repo", "deadbeef")

    assert "--paginate" in captured["argv"], "the helper must paginate, not read one page"
    assert len(observed) == 101, f"expected all 101 names, got {len(observed)}"
    assert observed["startup-import-smoke"] == "cancelled"


def test_slurp_is_used_because_paginate_alone_emits_one_document_per_page() -> None:
    """`--paginate` without `--slurp` concatenates JSON documents.

    `json.loads` rejects that outright, so the tool would die rather than
    degrade -- but only once a list exceeded one page. Pinning the flag keeps
    that failure from being reintroduced and then hidden by small fixtures.
    """
    captured: dict[str, list[str]] = {}

    class _Result:
        stdout = "[]"

    def _fake_run(argv, **_kwargs):  # type: ignore[no-untyped-def]
        captured["argv"] = argv
        return _Result()

    import check_run_status

    original = check_run_status.subprocess.run
    check_run_status.subprocess.run = _fake_run  # type: ignore[assignment]
    try:
        all_pages("/whatever")
    finally:
        check_run_status.subprocess.run = original  # type: ignore[assignment]

    assert "--slurp" in captured["argv"]


def test_never_reported_is_not_green_and_not_failing() -> None:
    """#16120 AC5: they are different states and only one of them is a red.

    A context nothing published has not passed. Collapsing it into `green` is a
    merge gate reporting a pass it did not earn; collapsing it into `failing`
    sends someone to debug a check that never ran.
    """
    observed = {"ci": "success", "code-quality": "failure"}
    buckets = split_by_state(observed, ["ci", "code-quality", "python-suite"])

    assert buckets["green"] == ["ci"]
    assert buckets["failing"] == ["code-quality"]
    assert buckets["never_reported"] == ["python-suite"]


def test_running_is_kept_apart_from_failing() -> None:
    """A PR that needs waiting and a PR that needs work are different problems."""
    observed = {"a": "in_progress", "b": "queued", "c": "failure"}
    buckets = split_by_state(observed, ["a", "b", "c"])

    assert buckets["running"] == ["a", "b"]
    assert buckets["failing"] == ["c"]


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("success", "acceptable"),
        ("skipped", "acceptable"),
        ("neutral", "acceptable"),
        ("in_progress", "running"),
        ("queued", "running"),
        ("failure", "failing"),
        ("cancelled", "failing"),
        ("timed_out", "failing"),
    ],
)
def test_rank_classifies_every_state_this_repo_sees(state: str, expected: str) -> None:
    """An unrecognised state must rank as failing, never as acceptable.

    `cancelled` and `timed_out` are the ones that matter -- they are not in any
    explicit set, so they reach `failing` by falling through, and a change that
    made the fallthrough acceptable would hide exactly the reds this helper
    exists to surface.
    """
    assert rank(state) == expected
