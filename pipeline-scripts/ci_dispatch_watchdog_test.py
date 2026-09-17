# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A queued hosted job is never reported as a self-hosted outage (#16309).

On 2026-09-11 the watchdog published *"2 self-hosted run(s) queued over 45m with
no runner available"* while both queued jobs carried ``labels=ubuntu-latest``.
The stall was real; the stated cause was not. **Every** workflow in this
repository declares ``runs-on: ubuntu-latest``, so the self-hosted pool serves no
job at all — an operator sent to look at it finds one runner offline, which looks
like the answer and is not.

`run_requires_self_hosted` is the filter that keeps the outage verdict honest.
These tests pin it from both directions, because a filter that suppressed
everything would pass a one-sided test while hiding a genuine outage.
"""

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "ci_dispatch_watchdog",
    Path(__file__).resolve().parents[0] / "ci_dispatch_watchdog.py",
)
watchdog = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(watchdog)

NOW = datetime(2026, 9, 11, 8, 45, tzinfo=timezone.utc)
LONG_AGO = "2026-09-11T07:55:00Z"


def _run(name: str, path: str, status: str = "queued", created: str = LONG_AGO) -> dict:
    return {"name": name, "path": path, "status": status, "created_at": created, "event": "pull_request"}


def test_a_queued_hosted_run_is_not_a_self_hosted_outage():
    """The #16309 defect: hosted saturation published as `no runner available`."""
    state, description = watchdog.classify_dispatch(
        runs=[_run("Frontend Testing Suite", ".github/workflows/frontend-test.yml")],
        head_pushed_at=LONG_AGO,
        now=NOW,
        grace_minutes=5,
        stall_minutes=45,
        pool_serving=False,
        self_hosted_paths=set(),
    )
    assert "no runner available" not in description, description
    assert "self-hosted" not in description, description
    assert state == "pending", state


def test_a_queued_self_hosted_run_is_still_reported_as_an_outage():
    """The control. Without it, a filter that suppressed everything would pass above."""
    path = ".github/workflows/heavy.yml"
    state, description = watchdog.classify_dispatch(
        runs=[_run("Heavy Suite", path)],
        head_pushed_at=LONG_AGO,
        now=NOW,
        grace_minutes=5,
        stall_minutes=45,
        pool_serving=False,
        self_hosted_paths={path},
    )
    assert state == "failure", state
    assert "no runner available" in description, description


def test_the_hosted_finding_names_the_counts():
    """#16309 AC2: an operator needs the limit named, not 'behind a busy queue'."""
    runs = [_run(f"Job {i}", ".github/workflows/frontend-test.yml") for i in range(3)]
    runs.append(_run("Running One", ".github/workflows/ci.yml", status="in_progress"))
    _, description = watchdog.classify_dispatch(
        runs=runs,
        head_pushed_at=LONG_AGO,
        now=NOW,
        grace_minutes=5,
        stall_minutes=45,
        pool_serving=False,
        self_hosted_paths=set(),
    )
    assert "hosted-runner concurrency saturated" in description, description
    assert "3 queued" in description, description
    assert "1 running" in description, description


@pytest.mark.parametrize("paths", [None])
def test_an_unattributable_run_stays_reportable(paths):
    """Unknown resolves to reportable: suppressing a real outage is the worse error."""
    state, description = watchdog.classify_dispatch(
        runs=[_run("Mystery", ".github/workflows/unknown.yml")],
        head_pushed_at=LONG_AGO,
        now=NOW,
        grace_minutes=5,
        stall_minutes=45,
        pool_serving=False,
        self_hosted_paths=paths,
    )
    assert state == "failure", state
    assert "no runner available" in description, description
