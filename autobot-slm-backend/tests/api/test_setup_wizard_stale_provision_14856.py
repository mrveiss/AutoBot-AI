# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the stale-provision-state 409 override (#14856, AC4).

The defect: ``POST /setup/provision-fleet`` 409ed whenever
``_provision_state["status"] == "running"`` with no staleness bound. A run
that crashed, was killed, or simply never reported completion left the wizard
wedged forever -- there was no recovery short of restarting the process.

These tests assert the guard, not the happy path: a state frozen at
``running`` past the TTL must NOT 409 (the fix), and a state at ``running``
with recent progress MUST still 409 (the counterweight -- without it "always
override" would pass the first test too).
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api import setup_wizard as sw
from services.provision_progress import PROVISION_STALE_SECONDS, is_stale


def _reset_state(**overrides) -> None:
    """Reset ``sw._provision_state`` in place (it is a module-level global).

    ``provision_fleet`` REBINDS ``sw._provision_state`` to a brand new dict
    on every successful start (see its ``global _provision_state`` block) --
    so assertions after calling it must re-read ``sw._provision_state``
    itself, never a name captured before the call, or they would silently
    keep checking the old, now-orphaned dict.
    """
    sw._provision_state.clear()
    sw._provision_state.update(
        {
            "status": "idle",
            "started_at": None,
            "finished_at": None,
            "last_progress_at": None,
            "output_lines": [],
            "error": None,
        }
    )
    sw._provision_state.update(overrides)


# ---------------------------------------------------------------------------
# Unit level: services.provision_progress.is_stale
# ---------------------------------------------------------------------------


def test_a_run_that_stopped_advancing_is_stale() -> None:
    """The defect: this state used to 409 every future provision-fleet call forever."""
    long_ago = time.time() - PROVISION_STALE_SECONDS - 60
    state = {"status": "running", "started_at": long_ago, "last_progress_at": long_ago}
    assert is_stale(state) is True


def test_a_run_still_making_progress_is_not_stale() -> None:
    """The counterweight: reaping live work is worse than the lockout it cures."""
    just_now = time.time()
    state = {"status": "running", "started_at": just_now - 5000, "last_progress_at": just_now}
    assert is_stale(state) is False


def test_falls_back_to_started_at_when_nothing_stamped_yet() -> None:
    """A run that has not produced a single output line yet is judged on start time."""
    long_ago = time.time() - PROVISION_STALE_SECONDS - 60
    state = {"status": "running", "started_at": long_ago, "last_progress_at": None}
    assert is_stale(state) is True

    just_started = time.time()
    fresh_state = {"status": "running", "started_at": just_started, "last_progress_at": None}
    assert is_stale(fresh_state) is False


def test_a_state_with_no_markers_at_all_is_never_stale() -> None:
    """Missing timestamps must never read as abandonment of a genuinely running run."""
    assert is_stale({"status": "running", "started_at": None, "last_progress_at": None}) is False


# ---------------------------------------------------------------------------
# Endpoint level: POST /setup/provision-fleet's 409 branch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provision_fleet_overrides_a_stale_running_state() -> None:
    """AC4: a wedged run (running, no progress past the TTL) must not 409."""
    long_ago = time.time() - PROVISION_STALE_SECONDS - 60
    _reset_state(status="running", started_at=long_ago, last_progress_at=long_ago)

    with patch("api.setup_wizard._run_provisioning_task", new=AsyncMock()):
        result = await sw.provision_fleet(sw.ProvisionRequest(node_ids=None), _={})

    assert result["status"] == "started"
    # Re-read the module attribute: provision_fleet rebinds it to a fresh dict.
    assert sw._provision_state["status"] == "running"


@pytest.mark.asyncio
async def test_provision_fleet_still_409s_a_genuinely_running_run() -> None:
    """The counterweight: a run showing recent progress must still 409.

    Without this, "always override" would also pass the test above -- the
    whole value of the fix is distinguishing "in flight" from "abandoned".
    """
    just_now = time.time()
    _reset_state(status="running", started_at=just_now - 5, last_progress_at=just_now)

    with patch("api.setup_wizard._run_provisioning_task", new=AsyncMock()):
        with pytest.raises(HTTPException) as exc_info:
            await sw.provision_fleet(sw.ProvisionRequest(node_ids=None), _={})

    assert exc_info.value.status_code == 409
    # The genuinely-running state must be left untouched by the failed attempt.
    assert sw._provision_state["status"] == "running"
