# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The sandbox probe must report the degraded state, not infer it away (#14872).

Behaviour, not source text: each test drives ``probe_sandbox`` with a different
world (no SDK, SDK but no daemon, both present) and asserts what it *reports*.
The bug being guarded is a sandbox that looks configured and silently runs
uncontainerised, so the assertion that matters is that ``containerised`` is
False and the status is not ``ok`` whenever a container is not actually
involved.
"""

from __future__ import annotations

import asyncio

import pytest

from api.sandbox_health import _PROBE_NAME, probe_sandbox
from api.system_health import KnownProbes, list_registered_probes


def test_the_probe_is_registered_under_the_canonical_name() -> None:
    """A probe nobody registered reports nothing, and nothing says so."""
    assert _PROBE_NAME == KnownProbes.SANDBOX.value
    assert _PROBE_NAME in list_registered_probes()


@pytest.mark.asyncio
async def test_a_missing_sdk_is_reported_as_uncontainerised(monkeypatch) -> None:
    """The #14872 headline: no SDK means code runs as a local subprocess."""
    monkeypatch.setattr("api.sandbox_health._docker_sdk_present", lambda: False)

    health = await probe_sandbox()

    assert health.data["docker_sdk"] is False
    assert health.data["containerised"] is False
    assert health.status != "ok", "an uncontainerised sandbox must never report ok"
    assert "UNSANDBOXED" in (health.detail or "")


@pytest.mark.asyncio
async def test_an_unreachable_daemon_is_reported_as_uncontainerised(monkeypatch) -> None:
    """An installed SDK is not a running daemon.

    This is the case a `find_spec`-only check would call healthy: the package
    is there, so the sandbox "exists" — while every execution still runs
    outside a container.
    """
    monkeypatch.setattr("api.sandbox_health._docker_sdk_present", lambda: True)

    async def _unreachable() -> tuple[bool, str]:
        return False, "connection refused"

    monkeypatch.setattr("api.sandbox_health._daemon_reachable", _unreachable)

    health = await probe_sandbox()

    assert health.data["docker_sdk"] is True
    assert health.data["daemon_reachable"] is False
    assert health.data["containerised"] is False
    assert health.status != "ok"
    assert "connection refused" in (health.detail or ""), "the reason must reach the operator"


@pytest.mark.asyncio
async def test_a_working_daemon_is_reported_as_containerised(monkeypatch) -> None:
    """Negative control: a probe that reported 'degraded' unconditionally would
    satisfy every test above while telling an operator nothing."""
    monkeypatch.setattr("api.sandbox_health._docker_sdk_present", lambda: True)

    async def _reachable() -> tuple[bool, None]:
        return True, None

    monkeypatch.setattr("api.sandbox_health._daemon_reachable", _reachable)

    health = await probe_sandbox()

    assert health.data["containerised"] is True
    assert health.status == "ok"
    assert health.detail is None


@pytest.mark.asyncio
async def test_a_hanging_daemon_ping_does_not_hold_the_aggregator(monkeypatch) -> None:
    """A ping that never returns must become a reported failure, not a stall.

    The aggregator gives every probe a 2s budget. Without its own bound this
    probe would spend the whole of it on one blocking socket call and take the
    rest of the health page down with it.
    """
    monkeypatch.setattr("api.sandbox_health._docker_sdk_present", lambda: True)
    monkeypatch.setattr("api.sandbox_health._PING_TIMEOUT_S", 0.05)

    def _hang() -> bool:
        import time

        time.sleep(5)
        return True

    monkeypatch.setattr("api.sandbox_health._ping_daemon", _hang)

    health = await asyncio.wait_for(probe_sandbox(), timeout=2.0)

    assert health.data["containerised"] is False
    assert health.status != "ok"
    assert "did not answer" in (health.detail or "")
