# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A2A trust is keyed on (credential, peer id), and an admin grant is the way back in (#16950).

Owner decision (#16950): trust keyed on the self-declared header alone let one
credential claim whichever peer id held the highest trust. Re-keyed on the pair,
every existing peer starts UNTRUSTED, and an admin re-grants each one. The old
header-only records are kept, never read for access.
"""

import json

import pytest

from a2a.peer_identity import credential_subject, peer_trust_key
from a2a.trust_score import PROMOTION_WINDOW, TrustRecord, TrustScoreManager
from autobot_shared.trust_enums import TrustLevel


@pytest.fixture
def manager(tmp_path, monkeypatch):
    """A real TrustScoreManager over an in-process Redis, so both key namespaces are exercised."""
    fakeredis = pytest.importorskip("fakeredis")
    client = fakeredis.FakeRedis(decode_responses=True)
    mgr = TrustScoreManager(sqlite_path=tmp_path / "audit.db")
    monkeypatch.setattr(mgr, "_redis", lambda: client)
    mgr.client = client
    return mgr


class TestTheKey:
    def test_two_credentials_presenting_one_peer_id_have_distinct_trust(self, manager):
        alice, bob = peer_trust_key("alice", "peer-y"), peer_trust_key("bob", "peer-y")

        manager.grant(alice, TrustLevel.STANDARD, actor="admin")

        assert manager.get_trust_level(alice) == TrustLevel.STANDARD
        assert manager.get_trust_level(bob) == TrustLevel.UNTRUSTED

    def test_parts_containing_the_separator_cannot_collide(self):
        assert peer_trust_key("a/b", "c") != peer_trust_key("a", "b/c")

    def test_the_subject_is_the_verified_principal_not_nobody(self):
        assert credential_subject({"user_id": "u-1", "username": "alice"}) == "u-1"
        assert credential_subject({"username": "service:slm", "service": True}) == "service:slm"
        with pytest.raises(ValueError):
            credential_subject({})


class TestTheLegacyRecords:
    def _plant_legacy(self, manager, peer_id, level):
        record = TrustRecord(peer_id=peer_id, current_level=level)
        manager.client.set(f"a2a:trust:{peer_id}", json.dumps(record.to_dict()))

    def test_a_legacy_header_only_record_grants_nothing_under_the_new_key(self, manager):
        self._plant_legacy(manager, "peer-x", TrustLevel.TRUSTED)

        assert manager.get_trust_level(peer_trust_key("alice", "peer-x")) == TrustLevel.UNTRUSTED

    def test_legacy_records_are_kept_and_listed_for_the_admin(self, manager):
        self._plant_legacy(manager, "peer-x", TrustLevel.TRUSTED)

        manager.grant(peer_trust_key("alice", "peer-x"), TrustLevel.STANDARD, actor="admin")

        assert manager.client.exists("a2a:trust:peer-x"), "reset must not destroy the history"
        assert [row["peer_id"] for row in manager.list_legacy_peers()] == ["peer-x"]

    def test_pairs_and_legacy_records_do_not_mix_in_listings(self, manager):
        self._plant_legacy(manager, "peer-x", TrustLevel.TRUSTED)
        manager.grant(peer_trust_key("alice", "peer-x"), TrustLevel.LIMITED, actor="admin")

        assert [r.peer_id for r in manager.list_peers()] == [peer_trust_key("alice", "peer-x")]


class TestTheGrant:
    def test_a_grant_is_audited_with_actor_pair_and_level(self, manager):
        pair = peer_trust_key("alice", "peer-x")

        manager.grant(pair, TrustLevel.STANDARD, actor="admin-1")

        entry = manager.get_audit_log(pair)[0]
        assert entry["new_level"] == TrustLevel.STANDARD.value
        assert "admin-1" in entry["reason"]

    def test_a_grant_survives_score_drift(self, manager):
        """Without a floor, the first recompute of a history-less record would demote it at once."""
        pair = peer_trust_key("alice", "peer-x")
        manager.grant(pair, TrustLevel.STANDARD, actor="admin")

        manager.record_failure(pair)

        assert manager.get_trust_level(pair) == TrustLevel.STANDARD

    def test_misconduct_revokes_the_grant(self, manager):
        pair = peer_trust_key("alice", "peer-x")
        manager.grant(pair, TrustLevel.STANDARD, actor="admin")

        manager.record_threat_event(pair)
        manager.record_success(pair)

        assert manager.get_trust_level(pair) != TrustLevel.STANDARD
        assert manager.get_record(pair).granted_level is None

    def test_the_control_an_ungranted_pair_cannot_climb_in_one_step(self, manager):
        """The grant is what lifted the pairs above: the behavioural path still needs its window."""
        pair = peer_trust_key("alice", "peer-x")

        for _ in range(PROMOTION_WINDOW - 1):
            manager.record_success(pair)

        assert manager.get_trust_level(pair) == TrustLevel.UNTRUSTED


def test_the_grant_route_keys_on_the_pair_and_records_the_acting_admin():
    from unittest.mock import MagicMock, patch

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import api.a2a_trust as trust_api

    app = FastAPI()
    app.include_router(trust_api.router, prefix="/api/a2a")
    app.dependency_overrides[trust_api.get_current_user] = lambda: {"username": "admin-1", "user_id": "admin-1"}
    manager = MagicMock()
    manager.grant.return_value = TrustRecord(peer_id=peer_trust_key("alice", "peer-x"), current_level=TrustLevel.STANDARD)

    with patch.object(trust_api, "get_trust_manager", return_value=manager):
        response = TestClient(app).post(
            "/api/a2a/trust/grant", json={"subject": "alice", "peer_id": "peer-x", "level": "STANDARD"}
        )

    assert response.status_code == 200, response.text
    manager.grant.assert_called_once_with(peer_trust_key("alice", "peer-x"), TrustLevel.STANDARD, actor="admin-1")
