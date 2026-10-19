# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Issue claims through the API, behind the REAL canonical gate (#18811).

The holder is bound to the authenticated principal; every caller here is resolved by production
code (``_issue_claims_harness``): a real signed login JWT, the real internal-key check, the real
auth-disabled branch. No ``X-Organization-Id`` is ever sent: the endpoints are install-wide.
"""

from __future__ import annotations

import pytest

from autobot_shared.coordination import work_claims
from tests.coordination._issue_claims_harness import BASE


def _alice(h) -> dict:
    return h.creds["login_jwt"]


def test_claim_is_granted_and_bound_to_the_caller(harness):
    r = harness.client.post(f"{BASE}/18811", json={"owner": "s1", "note": "api"}, headers=_alice(harness))
    assert r.status_code == 200 and r.json()["granted"] is True
    assert r.json()["holder"]["agent_id"] == "alice/s1"


def test_second_user_claim_is_409_naming_the_holder(harness):
    harness.client.post(f"{BASE}/7", json={"owner": "s1"}, headers=_alice(harness))
    r = harness.client.post(f"{BASE}/7", json={"owner": "s1"}, headers=harness.bob)
    assert r.status_code == 409
    assert r.json()["detail"]["holder"]["agent_id"] == "alice/s1" and r.json()["detail"]["granted"] is False


def test_holder_releases_own_claim(harness):
    harness.client.post(f"{BASE}/7", json={"owner": "s1"}, headers=_alice(harness))
    r = harness.client.delete(f"{BASE}/7", params={"owner": "s1"}, headers=_alice(harness))
    assert r.status_code == 200 and r.json()["released"] is True
    assert harness.client.get(f"{BASE}/7", headers=harness.bob).json()["held"] is False


@pytest.mark.parametrize("owner", ["s1", "anything"])
def test_a_cross_user_release_is_409_and_the_claim_stays_held(harness, owner):
    harness.client.post(f"{BASE}/7", json={"owner": "s1"}, headers=_alice(harness))
    r = harness.client.delete(f"{BASE}/7", params={"owner": owner}, headers=harness.bob)
    assert r.status_code == 409 and r.json()["detail"]["released"] is False
    held = harness.client.get(f"{BASE}/7", headers=harness.bob).json()
    assert held["held"] is True and held["holder"]["agent_id"] == "alice/s1"


def test_same_owner_name_under_two_users_are_two_holders(harness):
    assert harness.client.post(f"{BASE}/7", json={"owner": "s1"}, headers=_alice(harness)).status_code == 200
    assert harness.client.post(f"{BASE}/8", json={"owner": "s1"}, headers=harness.bob).status_code == 200
    claims = harness.client.get(BASE, headers=_alice(harness)).json()["claims"]
    assert sorted(c["agent_id"] for c in claims) == ["alice/s1", "bob/s1"]


def test_owner_cannot_smuggle_another_principal_prefix(harness):
    r = harness.client.post(f"{BASE}/7", json={"owner": "alice/s1"}, headers=harness.bob)
    assert r.status_code == 400


def test_who_and_list_without_organization_header(harness):
    assert harness.client.get(f"{BASE}/7", headers=_alice(harness)).json() == {"held": False}
    harness.client.post(f"{BASE}/7", json={"owner": "s1"}, headers=_alice(harness))
    assert harness.client.get(f"{BASE}/7", headers=_alice(harness)).json()["holder"]["agent_id"] == "alice/s1"
    r = harness.client.get(BASE, headers=_alice(harness))
    assert r.status_code == 200 and len(r.json()["claims"]) == 1


def test_anonymous_is_401_everywhere(harness):
    c = harness.client
    assert c.post(f"{BASE}/7", json={"owner": "s1"}).status_code == 401
    assert c.delete(f"{BASE}/7", params={"owner": "s1"}).status_code == 401
    assert c.get(f"{BASE}/7").status_code == 401
    assert c.get(BASE).status_code == 401


def test_the_service_principal_reads_but_its_writes_are_403(harness):
    svc = harness.creds["internal_service_key"]
    assert harness.client.get(BASE, headers=svc).status_code == 200
    assert harness.client.post(f"{BASE}/7", json={"owner": "s1"}, headers=svc).status_code == 403
    assert harness.client.delete(f"{BASE}/7", params={"owner": "s1"}, headers=svc).status_code == 403
    assert harness.client.get(BASE, headers=svc).json()["claims"] == []


def test_a_wrong_internal_key_is_anonymous(harness):
    r = harness.client.post(f"{BASE}/7", json={"owner": "s1"}, headers={"X-Internal-API-Key": "wrong"})
    assert r.status_code == 401


def test_with_auth_disabled_writes_are_403(harness):
    """Every caller is the synthetic ``admin`` then, so a write could act under any owner."""
    harness.resolution.configure("auth_disabled")
    assert harness.client.post(f"{BASE}/7", json={"owner": "s1"}).status_code == 403
    assert harness.client.delete(f"{BASE}/7", params={"owner": "s1"}).status_code == 403
    assert harness.client.get(BASE).json()["claims"] == []


@pytest.mark.parametrize(
    "number,body",
    [(0, {"owner": "s1"}), (-3, {"owner": "s1"}), (7, {"owner": "  "}), (7, {"owner": "s1", "ttl_s": 5})],
)
def test_bad_number_owner_or_ttl_is_rejected_before_the_registry(harness, number, body):
    r = harness.client.post(f"{BASE}/{number}", json=body, headers=_alice(harness))
    assert r.status_code in (400, 422)
    assert harness.client.get(BASE, headers=_alice(harness)).json()["claims"] == []


def test_unreadable_registry_fails_closed(harness, monkeypatch):
    async def _none(database: str = "main"):
        return None

    monkeypatch.setattr(work_claims, "get_async_redis_client", _none)
    r = harness.client.post(f"{BASE}/7", json={"owner": "s1"}, headers=_alice(harness))
    assert r.status_code == 503
