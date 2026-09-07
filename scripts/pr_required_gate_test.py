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
    """
    result = verdict(["code-quality", "api-wiring", "smoke-test"], {})
    assert result["verdict"] == "BLOCKED"
    assert len(result["never_reported"]) == 3
    assert result["not_green"] == []


def test_skipped_is_acceptable_but_pending_is_not():
    """`skipped` is a real conclusion from path-filtered shims; `pending` is not a verdict."""
    assert verdict(["a"], {"a": "skipped"})["verdict"] == "CONTEXTS-GREEN"
    assert verdict(["a"], {"a": "pending"})["verdict"] == "BLOCKED"


def test_the_required_population_is_an_input_not_a_constant():
    """AC: the population is read from branch protection, never carried in the tool.

    Asserted structurally -- `verdict` cannot answer without being given the list,
    so no hardcoded set can drift out of date with the protection rules.
    """
    assert verdict([], {"anything": "failure"})["verdict"] == "CONTEXTS-GREEN"
    assert verdict(["x"], {})["never_reported"] == ["x"]
