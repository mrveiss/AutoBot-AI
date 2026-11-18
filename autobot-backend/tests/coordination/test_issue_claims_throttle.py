# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Failed claims-credential checks are limited and audited per source; one live credential per user (#18811).

Through the real routes, the real ``SecretsCoordinator`` and the shared ``RateLimiter`` over
fakeredis (see ``_issue_claims_harness``). The TestClient's own peer is the ``testclient`` source.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from api import coordination_issue_claims_credential as cred
from api import coordination_issue_claims_throttle as throttle
from api import envelope_secrets
from services.audit.taxonomy import AuditAction
from tests.coordination._issue_claims_harness import BASE, CREDENTIALS, mint, with_credential

SOURCE = "testclient"
LIMIT = 3
FORGED = "00000000-0000-0000-0000-000000000001." + "x" * 43


@pytest.fixture
def lookups(harness, monkeypatch) -> list:
    """Every ``verify_bearer`` call -- each one a store lookup -- recorded, then performed for real."""
    monkeypatch.setattr(throttle, "FAILURE_LIMIT", LIMIT)
    coordinator, calls = envelope_secrets._coordinator, []
    real = coordinator.verify_bearer

    async def _counted(session, **kwargs):
        calls.append(kwargs["secret_id"])
        return await real(session, **kwargs)

    monkeypatch.setattr(coordinator, "verify_bearer", _counted)
    return calls


def _claim(client, credential: str):
    return client.post(f"{BASE}/7", json={"owner": "s1"}, headers=with_credential(credential))


def _events(h, action: AuditAction) -> list:
    return [e for e in h.audit if e.action == action.value]


def test_past_the_limit_the_next_attempt_is_429_with_no_lookup(harness, lookups):
    assert [_claim(harness.client, FORGED).status_code for _ in range(LIMIT)] == [401] * LIMIT
    assert len(lookups) == LIMIT
    refused = _claim(harness.client, FORGED)
    assert refused.status_code == 429 and refused.headers["Retry-After"] == str(throttle.FAILURE_WINDOW_S)
    assert len(lookups) == LIMIT  # refused before any store lookup


def test_failures_are_one_aggregated_audit_event_with_the_count(harness, lookups):
    for _ in range(LIMIT + 1):
        _claim(harness.client, FORGED)
    assert _events(harness, AuditAction.SECRET_ACCESS) == []  # no row per miss
    assert _events(harness, AuditAction.CLAIMS_CREDENTIAL_CHECK_FAILURES) == []  # not before the window closes
    asyncio.run(cred.THROTTLE.tally.flush(SOURCE))
    (event,) = _events(harness, AuditAction.CLAIMS_CREDENTIAL_CHECK_FAILURES)
    assert event.outcome == "failure" and event.metadata["source"] == SOURCE
    assert (event.metadata["failures"], event.metadata["throttled"]) == (LIMIT, 1)
    assert event.metadata["window_s"] == throttle.FAILURE_WINDOW_S
    asyncio.run(cred.THROTTLE.tally.flush(SOURCE))
    assert len(_events(harness, AuditAction.CLAIMS_CREDENTIAL_CHECK_FAILURES)) == 1  # the window is closed


def test_a_success_still_audits_individually_and_is_not_counted(harness, lookups):
    credential = mint(harness)
    harness.audit.clear()
    assert [_claim(harness.client, credential).status_code for _ in range(LIMIT + 1)] == [200] * (LIMIT + 1)
    assert [e.outcome for e in _events(harness, AuditAction.SECRET_ACCESS)] == ["success"] * (LIMIT + 1)
    assert not asyncio.run(cred.THROTTLE.tally.flush(SOURCE))


def test_the_limit_is_per_source(harness, lookups):
    for _ in range(LIMIT):
        _claim(harness.client, FORGED)
    assert _claim(harness.client, FORGED).status_code == 429
    other = TestClient(harness.app, client=("198.51.100.7", 50000), raise_server_exceptions=False)
    assert _claim(other, FORGED).status_code == 401  # looked up and refused on its merits, not throttled
    assert len(lookups) == LIMIT + 1


@pytest.fixture
def redis_down(monkeypatch) -> None:
    """The shared limiter and the tally cannot reach Redis: the limiter fails open."""
    import autobot_shared.rate_limiter as rate_limiter

    async def _unreachable(database: str = "main"):
        return None

    for module in (rate_limiter, throttle):
        monkeypatch.setattr(module, "get_async_redis_client", _unreachable)


def test_with_redis_down_the_limit_still_refuses_without_a_lookup(harness, lookups, redis_down):
    assert [_claim(harness.client, FORGED).status_code for _ in range(LIMIT)] == [401] * LIMIT
    assert _claim(harness.client, FORGED).status_code == 429
    assert len(lookups) == LIMIT  # the in-process window refused before any store lookup


def test_with_redis_down_failures_under_the_limit_are_still_looked_up(harness, lookups, redis_down):
    assert [_claim(harness.client, FORGED).status_code for _ in range(LIMIT)] == [401] * LIMIT
    assert len(lookups) == LIMIT


def test_the_in_process_window_forgets_failures_older_than_the_window(monkeypatch):
    clock = iter([0.0, 1.0, 2.0, 2.0 + throttle.FAILURE_WINDOW_S])
    monkeypatch.setattr(throttle.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(throttle, "FAILURE_LIMIT", 1)
    window = throttle.LocalFailureWindow()  # t=0
    window.record(SOURCE)  # t=1
    assert window.remaining(SOURCE) == 0  # t=2: inside the window
    assert window.remaining(SOURCE) == 1  # one full window later: forgotten


def test_minting_again_revokes_the_previous_credential(harness):
    bob = harness.client.post(CREDENTIALS, headers=harness.bob).json()["credential"]
    first, second = mint(harness), mint(harness)
    assert _claim(harness.client, first).status_code == 401
    assert _claim(harness.client, second).status_code == 200
    assert harness.client.post(f"{BASE}/8", json={"owner": "s2"}, headers=with_credential(bob)).status_code == 200
    (revoked,) = _events(harness, AuditAction.CLAIMS_CREDENTIAL_REVOKE)
    assert revoked.resource_id == first.partition(".")[0] and revoked.metadata["reason"] == "superseded"
    assert revoked.metadata["superseded_by"] == second.partition(".")[0]
