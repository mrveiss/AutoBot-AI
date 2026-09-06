# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The update log must survive the restart the update performs (#15881).

`_stage_log` appends to `stage.log_lines`, an in-memory list on a job object
held by the SLM process -- and the self-update restarts that process. Every
line the operator was watching died with it, and the resumed job wrote
"completed before restart" placeholders *over* the real history. A clean update
was then indistinguishable from a wedged one: on the day this was filed the play
finished `ok=282 changed=57 failed=0` while the GUI log still ended at
"Firing Ansible self-update (fire-and-forget)".

Both directions are asserted. A restore path that silently no-ops looks exactly
like the defect, so "logs are carried" and "a plan without logs still resumes"
have to be separate tests -- the second is what a v1 plan written by an older
SLM will hit.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_CODE_SYNC = Path(__file__).resolve().parents[1] / "api" / "code_sync.py"


@pytest.fixture(scope="module")
def source() -> str:
    assert _CODE_SYNC.is_file(), f"file under test is missing: {_CODE_SYNC}"
    return _CODE_SYNC.read_text(encoding="utf-8")


def test_the_plan_WRITES_stage_logs(source: str) -> None:
    """The write side, asserted separately from the read side on purpose.

    `"stage_logs"` appears twice -- once where the plan is built and once where
    the resume reads it back. A single `in source` check is satisfied by either,
    so deleting the write leaves the test green while every log line still dies
    at the restart. Caught by mutation while writing this file; it is the same
    conflation the rest of this work has been about.
    """
    assert re.search(r'"stage_logs"\s*:', source), (
        "the resume plan no longer BUILDS stage_logs, so every log line dies with "
        "the process the self-update restarts (#15881)"
    )


def test_the_resume_READS_stage_logs(source: str) -> None:
    """The read side. A plan that stores logs nothing restores is no better."""
    assert re.search(r'\.get\(\s*"stage_logs"', source), (
        "nothing reads stage_logs back out of the plan, so the resumed job still "
        "shows placeholders over the real history (#15881)"
    )


def test_the_persisted_slice_is_bounded(source: str) -> None:
    """It lives in a Settings row, not a process."""
    match = re.search(r"_RESUME_PLAN_LOG_LINES\s*=\s*(\d+)", source)
    assert match, "the persisted log slice is unbounded -- it is written to a Settings row"
    assert 0 < int(match.group(1)) <= 200, (
        f"_RESUME_PLAN_LOG_LINES is {match.group(1)}; a stage caps at 200 in memory and "
        "the persisted slice must not exceed that"
    )


def test_an_older_plan_is_still_accepted(source: str) -> None:
    """The compatibility that keeps this fix from being an outage.

    A straight version bump rejects the plan written by the update that deploys
    this change: the SLM restarts, finds its own plan unreadable, and wedges.
    The validator must accept the previous version, which simply carries no logs.
    """
    assert "_SUPPORTED_RESUME_PLAN_VERSIONS" in source, (
        "the plan validator compares against a single version. A bump then discards "
        "the in-flight plan belonging to the update deploying it (#15881)."
    )
    match = re.search(r"_SUPPORTED_RESUME_PLAN_VERSIONS\s*=\s*frozenset\(\{([^}]*)\}\)", source)
    assert match, "could not read the supported-version set"
    versions = {int(v) for v in re.findall(r"\d+", match.group(1))}
    assert len(versions) >= 2, (
        f"only version(s) {sorted(versions)} accepted; the previous plan version must "
        "remain readable or the deploying update wedges itself"
    )
    assert "not in _SUPPORTED_RESUME_PLAN_VERSIONS" in source, (
        "the set is declared but the validator does not use it -- an unwired " "compatibility check is the same as none"
    )


def test_the_restart_is_marked_rather_than_hidden(source: str) -> None:
    """A reader must be able to tell which lines predate the restart."""
    assert "SLM restarted here" in source, (
        "restored lines are spliced in with no boundary marker, so pre- and "
        "post-restart output read as one continuous run (#15881)"
    )
