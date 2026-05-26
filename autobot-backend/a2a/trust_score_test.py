# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Trust Score Unit + Integration Tests

Issue #7358: Covers formula components, trust-level thresholds,
asymmetric update policy (instant demotion / windowed promotion),
capability gates, Redis + SQLite persistence, and the integration
acceptance criteria from the issue.
"""

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from a2a.trust_score import (
    PROMOTION_WINDOW,
    Capability,
    TrustAccessDenied,
    TrustLevel,
    TrustRecord,
    TrustScoreManager,
    _level_from_score,
    get_capabilities,
    has_capability,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _manager_no_redis(tmp_path: Path) -> TrustScoreManager:
    """
    Return a TrustScoreManager backed by an in-process dict instead of Redis.

    Replaces _load / _save so state persists within the test without a live
    Redis instance.
    """
    import time as _time

    mgr = TrustScoreManager(sqlite_path=tmp_path / "audit.db")
    _store: dict = {}

    def _load(peer_id: str) -> TrustRecord:
        if peer_id in _store:
            return TrustRecord.from_dict(json.loads(_store[peer_id]))
        return TrustRecord(peer_id=peer_id)

    def _save(record: TrustRecord) -> None:
        record.updated_at = _time.time()
        _store[record.peer_id] = json.dumps(record.to_dict())

    mgr._load = _load
    mgr._save = _save
    return mgr


# ---------------------------------------------------------------------------
# TrustRecord.compute_score — formula components
# ---------------------------------------------------------------------------


class TestTrustFormula:
    def test_zero_interactions_gives_partial_score(self):
        r = TrustRecord(peer_id="p")
        score = r.compute_score()
        # success_rate=0, uptime=0, threat=1.0, integrity=1.0
        assert abs(score - (0.2 + 0.2)) < 1e-6

    def test_perfect_success_rate(self):
        r = TrustRecord(peer_id="p", success_count=100, failure_count=0)
        score = r.compute_score()
        # 0.4*1 + 0.2*0 + 0.2*1 + 0.2*1 = 0.8
        assert abs(score - 0.8) < 1e-6

    def test_success_rate_component(self):
        r = TrustRecord(peer_id="p", success_count=3, failure_count=1)
        # success_rate = 0.75
        score = r.compute_score()
        expected = 0.4 * 0.75 + 0.2 * 0.0 + 0.2 * 1.0 + 0.2 * 1.0
        assert abs(score - expected) < 1e-6

    def test_uptime_component(self):
        r = TrustRecord(peer_id="p", heartbeat_expected=10, heartbeat_received=8)
        # uptime = 0.8
        expected = 0.4 * 0.0 + 0.2 * 0.8 + 0.2 * 1.0 + 0.2 * 1.0
        assert abs(r.compute_score() - expected) < 1e-6

    def test_threat_score_decreases_with_events(self):
        r = TrustRecord(peer_id="p", threat_event_count=3)
        # threat_score = max(0, 1.0 - 0.2*3) = 0.4
        expected = 0.4 * 0.0 + 0.2 * 0.0 + 0.2 * 0.4 + 0.2 * 1.0
        assert abs(r.compute_score() - expected) < 1e-6

    def test_threat_score_floors_at_zero(self):
        r = TrustRecord(peer_id="p", threat_event_count=10)
        # threat_score = max(0, 1 - 0.2*10) = 0
        expected = 0.4 * 0.0 + 0.2 * 0.0 + 0.2 * 0.0 + 0.2 * 1.0
        assert abs(r.compute_score() - expected) < 1e-6

    def test_integrity_score_decreases_with_violations(self):
        r = TrustRecord(peer_id="p", integrity_violation_count=2)
        # integrity_score = max(0, 1 - 0.25*2) = 0.5
        expected = 0.4 * 0.0 + 0.2 * 0.0 + 0.2 * 1.0 + 0.2 * 0.5
        assert abs(r.compute_score() - expected) < 1e-6

    def test_integrity_score_floors_at_zero(self):
        r = TrustRecord(peer_id="p", integrity_violation_count=10)
        expected = 0.4 * 0.0 + 0.2 * 0.0 + 0.2 * 1.0 + 0.2 * 0.0
        assert abs(r.compute_score() - expected) < 1e-6

    def test_all_components_combined(self):
        r = TrustRecord(
            peer_id="p",
            success_count=8,
            failure_count=2,
            heartbeat_expected=10,
            heartbeat_received=9,
            threat_event_count=1,
            integrity_violation_count=0,
        )
        expected = 0.4 * 0.8 + 0.2 * 0.9 + 0.2 * 0.8 + 0.2 * 1.0
        assert abs(r.compute_score() - expected) < 1e-6


# ---------------------------------------------------------------------------
# Level thresholds
# ---------------------------------------------------------------------------


class TestTrustLevelMapping:
    def test_zero_score_is_untrusted(self):
        assert _level_from_score(0.0) == TrustLevel.UNTRUSTED

    def test_score_at_limit_is_untrusted(self):
        assert _level_from_score(0.30) == TrustLevel.UNTRUSTED

    def test_just_above_untrusted_is_limited(self):
        assert _level_from_score(0.31) == TrustLevel.LIMITED

    def test_score_at_limited_ceiling_is_limited(self):
        assert _level_from_score(0.60) == TrustLevel.LIMITED

    def test_just_above_limited_is_standard(self):
        assert _level_from_score(0.61) == TrustLevel.STANDARD

    def test_score_at_standard_ceiling_is_standard(self):
        assert _level_from_score(0.85) == TrustLevel.STANDARD

    def test_just_above_standard_is_trusted(self):
        assert _level_from_score(0.86) == TrustLevel.TRUSTED

    def test_perfect_score_is_trusted(self):
        assert _level_from_score(1.0) == TrustLevel.TRUSTED


# ---------------------------------------------------------------------------
# Capability matrix
# ---------------------------------------------------------------------------


class TestCapabilityMatrix:
    def test_untrusted_has_only_discovery(self):
        caps = get_capabilities(TrustLevel.UNTRUSTED)
        assert caps == {Capability.DISCOVERY}

    def test_limited_has_discovery_and_tasks(self):
        caps = get_capabilities(TrustLevel.LIMITED)
        assert Capability.DISCOVERY in caps
        assert Capability.SUBMIT_TASKS in caps
        assert Capability.QUERY_MEMORY not in caps

    def test_standard_has_memory(self):
        caps = get_capabilities(TrustLevel.STANDARD)
        assert Capability.QUERY_MEMORY in caps
        assert Capability.DEFINE_AGENTS not in caps

    def test_trusted_has_all_capabilities(self):
        caps = get_capabilities(TrustLevel.TRUSTED)
        assert caps == {
            Capability.DISCOVERY,
            Capability.SUBMIT_TASKS,
            Capability.QUERY_MEMORY,
            Capability.DEFINE_AGENTS,
        }

    def test_has_capability_positive(self):
        assert has_capability(TrustLevel.STANDARD, Capability.SUBMIT_TASKS)

    def test_has_capability_negative(self):
        assert not has_capability(TrustLevel.UNTRUSTED, Capability.SUBMIT_TASKS)


# ---------------------------------------------------------------------------
# TrustScoreManager — asymmetric update policy
# ---------------------------------------------------------------------------


class TestAsymmetricUpdates:
    def test_new_peer_starts_untrusted(self, tmp_path):
        mgr = _manager_no_redis(tmp_path)
        assert mgr.get_trust_level("new-peer") == TrustLevel.UNTRUSTED

    def test_promotion_requires_full_window(self, tmp_path):
        mgr = _manager_no_redis(tmp_path)
        peer = "slow-peer"
        for _ in range(PROMOTION_WINDOW - 1):
            mgr.record_success(peer)
        # One short of the window — must still be UNTRUSTED
        assert mgr.get_trust_level(peer) == TrustLevel.UNTRUSTED

    def test_promotion_at_exact_window(self, tmp_path):
        mgr = _manager_no_redis(tmp_path)
        peer = "ready-peer"
        for _ in range(PROMOTION_WINDOW):
            mgr.record_success(peer)
        # Score after 50 successes with no uptime: 0.4*1 + 0 + 0.2 + 0.2 = 0.8 → STANDARD
        assert mgr.get_trust_level(peer) == TrustLevel.STANDARD

    def test_failure_resets_promotion_window(self, tmp_path):
        mgr = _manager_no_redis(tmp_path)
        peer = "interrupted"
        for _ in range(PROMOTION_WINDOW - 1):
            mgr.record_success(peer)
        mgr.record_failure(peer)
        for _ in range(PROMOTION_WINDOW - 1):
            mgr.record_success(peer)
        # Window reset by failure; still one short
        assert mgr.get_trust_level(peer) == TrustLevel.UNTRUSTED

    def test_threat_event_causes_instant_demotion(self, tmp_path):
        mgr = _manager_no_redis(tmp_path)
        peer = "threat-peer"
        # Bring to STANDARD first
        for _ in range(PROMOTION_WINDOW):
            mgr.record_success(peer)
        assert mgr.get_trust_level(peer) == TrustLevel.STANDARD

        mgr.record_threat_event(peer)
        # Instant demotion to LIMITED
        assert mgr.get_trust_level(peer) == TrustLevel.LIMITED

    def test_threat_event_does_not_raise_untrusted_peer(self, tmp_path):
        mgr = _manager_no_redis(tmp_path)
        peer = "brand-new"
        mgr.record_threat_event(peer)
        # UNTRUSTED stays UNTRUSTED (min of UNTRUSTED, LIMITED = UNTRUSTED)
        assert mgr.get_trust_level(peer) == TrustLevel.UNTRUSTED

    def test_integrity_violation_causes_instant_demotion_to_untrusted(self, tmp_path):
        mgr = _manager_no_redis(tmp_path)
        peer = "bad-sig-peer"
        for _ in range(PROMOTION_WINDOW):
            mgr.record_success(peer)
        assert mgr.get_trust_level(peer) == TrustLevel.STANDARD

        mgr.record_integrity_violation(peer)
        assert mgr.get_trust_level(peer) == TrustLevel.UNTRUSTED

    def test_threat_resets_consecutive_successes(self, tmp_path):
        mgr = _manager_no_redis(tmp_path)
        peer = "reset-peer"
        for _ in range(PROMOTION_WINDOW):
            mgr.record_success(peer)
        mgr.record_threat_event(peer)
        record = mgr.get_record(peer)
        assert record.consecutive_successes == 0


# ---------------------------------------------------------------------------
# require_capability
# ---------------------------------------------------------------------------


class TestRequireCapability:
    def test_raises_for_denied_capability(self, tmp_path):
        mgr = _manager_no_redis(tmp_path)
        with pytest.raises(TrustAccessDenied) as exc_info:
            mgr.require_capability("new-peer", Capability.SUBMIT_TASKS)
        assert exc_info.value.peer_id == "new-peer"
        assert exc_info.value.capability == Capability.SUBMIT_TASKS
        assert exc_info.value.level == TrustLevel.UNTRUSTED

    def test_no_raise_for_allowed_capability(self, tmp_path):
        mgr = _manager_no_redis(tmp_path)
        # UNTRUSTED can do discovery
        mgr.require_capability("new-peer", Capability.DISCOVERY)  # must not raise

    def test_standard_peer_can_query_memory(self, tmp_path):
        mgr = _manager_no_redis(tmp_path)
        peer = "std-peer"
        for _ in range(PROMOTION_WINDOW):
            mgr.record_success(peer)
        mgr.require_capability(peer, Capability.QUERY_MEMORY)  # must not raise


# ---------------------------------------------------------------------------
# TrustRecord serialisation
# ---------------------------------------------------------------------------


class TestTrustRecordSerialisation:
    def test_roundtrip(self):
        r = TrustRecord(
            peer_id="p",
            success_count=10,
            failure_count=2,
            current_level=TrustLevel.STANDARD,
            score=0.72,
        )
        assert TrustRecord.from_dict(r.to_dict()) == r

    def test_to_dict_level_is_string(self):
        r = TrustRecord(peer_id="p", current_level=TrustLevel.LIMITED)
        assert r.to_dict()["current_level"] == "LIMITED"


# ---------------------------------------------------------------------------
# SQLite audit trail
# ---------------------------------------------------------------------------


class TestSQLiteAudit:
    def test_level_change_is_snapshotted(self, tmp_path):
        mgr = _manager_no_redis(tmp_path)
        peer = "audit-peer"
        for _ in range(PROMOTION_WINDOW):
            mgr.record_success(peer)

        db_path = tmp_path / "audit.db"
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT peer_id, old_level, new_level FROM trust_audit WHERE peer_id = ?",
                (peer,),
            ).fetchall()

        assert len(rows) >= 1
        # Final transition should be to STANDARD
        final = rows[-1]
        assert final[0] == peer
        assert final[2] == TrustLevel.STANDARD.value

    def test_threat_demotion_is_snapshotted(self, tmp_path):
        mgr = _manager_no_redis(tmp_path)
        peer = "demoted-peer"
        for _ in range(PROMOTION_WINDOW):
            mgr.record_success(peer)
        mgr.record_threat_event(peer)

        db_path = tmp_path / "audit.db"
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT new_level FROM trust_audit WHERE peer_id = ? ORDER BY id DESC LIMIT 1",
                (peer,),
            ).fetchall()

        assert rows[0][0] == TrustLevel.LIMITED.value


# ---------------------------------------------------------------------------
# Integration acceptance test (from GH#7358)
# ---------------------------------------------------------------------------


class TestIntegrationAcceptanceCriteria:
    """
    Issue #7358 acceptance:
      - Peer with 50 successes promoted to STANDARD.
      - One PII BLOCK event demotes to LIMITED instantly.
    """

    def test_50_successes_promoted_to_standard_then_pii_block_demotes_to_limited(self, tmp_path):
        mgr = _manager_no_redis(tmp_path)
        peer = "federation-partner"

        # Start UNTRUSTED
        assert mgr.get_trust_level(peer) == TrustLevel.UNTRUSTED

        # 50 consecutive successes → STANDARD
        for _ in range(PROMOTION_WINDOW):
            mgr.record_success(peer)
        assert mgr.get_trust_level(peer) == TrustLevel.STANDARD

        # One PII BLOCK (threat event) → instant demotion to LIMITED
        mgr.record_threat_event(peer)
        assert mgr.get_trust_level(peer) == TrustLevel.LIMITED

    def test_audit_log_records_both_transitions(self, tmp_path):
        mgr = _manager_no_redis(tmp_path)
        peer = "audited-peer"

        for _ in range(PROMOTION_WINDOW):
            mgr.record_success(peer)
        mgr.record_threat_event(peer)

        db_path = tmp_path / "audit.db"
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT old_level, new_level FROM trust_audit WHERE peer_id = ? ORDER BY id",
                (peer,),
            ).fetchall()

        # Should have at least two transitions: →STANDARD and STANDARD→LIMITED
        new_levels = [r[1] for r in rows]
        assert TrustLevel.STANDARD.value in new_levels
        assert TrustLevel.LIMITED.value in new_levels
