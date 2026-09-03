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
from pathlib import Path

import yaml

_CI = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"


def _document() -> dict:
    return yaml.safe_load(_CI.read_text(encoding="utf-8"))


def _shard_count() -> int:
    """How many shards the python-shard matrix actually runs."""
    jobs = _document()["jobs"]
    assert "python-shard" in jobs, "FIX THE SWEEP: no python-shard job in ci.yml"
    shards = jobs["python-shard"]["strategy"]["matrix"]["shard"]
    assert isinstance(shards, list) and shards, "python-shard matrix is not a non-empty list"
    return len(shards)


def _reported_count() -> int:
    """The number the aggregate job's success message claims."""
    steps = _document()["jobs"]["python-suite"]["steps"]
    bodies = [s["run"] for s in steps if "run" in s and "shards passed" in s["run"]]
    assert len(bodies) == 1, f"expected exactly one success message, found {len(bodies)}"
    found = re.search(r"All (\d+) python-suite shards passed", bodies[0])
    assert found, f"success message does not name a count: {bodies[0]!r}"
    return int(found.group(1))


def test_the_success_message_names_the_real_shard_count():
    """#14353: the message said 6 while the matrix ran 12."""
    assert _reported_count() == _shard_count(), (
        f"python-suite reports {_reported_count()} shards but the matrix runs "
        f"{_shard_count()}. Update the echo in ci.yml's python-suite job."
    )


def test_the_matrix_is_actually_read():
    """A vacuity floor: a matrix this test could not parse would pass silently."""
    assert _shard_count() >= 2, "FIX THE SWEEP: python-shard matrix parsed as fewer than 2 shards"
