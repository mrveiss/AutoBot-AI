# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The python-suite success message must name the real shard count (#14353).

``ci.yml`` printed "All 6 python-suite shards passed." while the matrix had run
twelve shards for some time. Nothing gated on ``python-suite``, so a wrong
number in a success message cost nothing -- but #14353 proposes making it a
required context, and then this is the line an operator reads when deciding
whether a red is real.

The number cannot come from ``strategy.job-total``: the aggregate job is not a
matrix job, so that context expands to empty there. So the literal stays, and
this test holds it to the matrix instead -- both numbers are read out of the
workflow, never restated here, so the test cannot drift from the thing it
guards (#14241).
"""

from __future__ import annotations

import re

from repo_tests._ci_shards import ci_document as _document
from repo_tests._ci_shards import python_shard_count as _shard_count
from repo_tests._paths import repo_root

_DURATIONS_WORKFLOW = repo_root() / ".github" / "workflows" / "test-durations.yml"


def _reported_count() -> int:
    """The number the `python-suite` gate's success detail claims (#18208: the gate, not an echo step)."""
    steps = _document()["jobs"]["python-suite"]["steps"]
    details = [
        s["with"]["work-detail"]
        for s in steps
        if "work-detail" in (s.get("with") or {}) and "shards passed" in s["with"]["work-detail"]
    ]
    assert len(details) == 1, f"expected exactly one success message, found {len(details)}"
    found = re.search(r"All (\d+) python-suite shards passed", details[0])
    assert found, f"success message does not name a count: {details[0]!r}"
    return int(found.group(1))


def test_the_success_message_names_the_real_shard_count():
    """#14353: the message said 6 while the matrix ran 12."""
    assert _reported_count() == _shard_count(), (
        f"python-suite reports {_reported_count()} shards but the matrix runs "
        f"{_shard_count()}. Update the `work-detail` of ci.yml's python-suite gate."
    )


def test_the_matrix_is_actually_read():
    """A vacuity floor: a matrix this test could not parse would pass silently."""
    assert _shard_count() >= 2, "FIX THE SWEEP: python-shard matrix parsed as fewer than 2 shards"


def test_the_durations_summary_describes_the_real_shard_count():
    """#19527: the weekly durations run summarises the split for a shard count.

    It is a literal in test-durations.yml because that workflow has no matrix to
    read; this holds it to ci.yml's, so a count change cannot leave the summary
    describing a split the PR gate no longer runs.
    """
    text = _DURATIONS_WORKFLOW.read_text(encoding="utf-8")
    found = re.findall(r"--splits (\d+)", text)
    assert found, "FIX THE SWEEP: test-durations.yml names no --splits count"
    assert {int(n) for n in found} == {
        _shard_count()
    }, f"test-durations.yml summarises --splits {found} but ci.yml runs {_shard_count()} shards"
