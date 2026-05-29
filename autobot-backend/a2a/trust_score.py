# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
A2A Behavioural Trust Score — federated peer evaluation.

Issue #7358: Continuous trust scoring for federated A2A peers. Every peer
starts UNTRUSTED; trust is earned through a sustained window of successful
interactions. Demotion is instant on any threat or integrity event.

Score formula
-------------
    trust = 0.4 * success_rate
           + 0.2 * uptime
           + 0.2 * threat_score
           + 0.2 * integrity_score

Trust levels and capability gates
----------------------------------
  UNTRUSTED  (score ≤ 0.30)  — discovery info only
  LIMITED    (0.30–0.60)     — discovery + task submission
  STANDARD   (0.60–0.85)     — + memory/knowledge queries
  TRUSTED    (> 0.85)        — + new agent definitions

Asymmetric update policy
------------------------
  Promotion:  only allowed after PROMOTION_WINDOW consecutive successes.
  Demotion:   instant on any threat or integrity event.

Persistence
-----------
  Active scores:   Redis  a2a:trust:{peer_id}  (JSON)
  Forensic audit:  SQLite table trust_audit     (level-change snapshots)

Usage
-----
    from a2a.trust_score import get_trust_manager, Capability, TrustAccessDenied

    mgr = get_trust_manager()
    mgr.record_success("partner-agent-1")
    level = mgr.get_trust_level("partner-agent-1")
    mgr.require_capability("partner-agent-1", Capability.SUBMIT_TASKS)  # raises on deny
"""

import json
import os
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Optional, Set

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from autobot_shared.ssot_config import config
from autobot_shared.trust_enums import TrustLevel

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Trust levels
# ---------------------------------------------------------------------------

PROMOTION_WINDOW: int = 50  # consecutive successes required for any promotion

_LEVEL_ORDER = [TrustLevel.UNTRUSTED, TrustLevel.LIMITED, TrustLevel.STANDARD, TrustLevel.TRUSTED]


def _level_rank(level: TrustLevel) -> int:
    return _LEVEL_ORDER.index(level)


def _level_from_score(score: float) -> TrustLevel:
    if score > 0.85:
        return TrustLevel.TRUSTED
    if score > 0.60:
        return TrustLevel.STANDARD
    if score > 0.30:
        return TrustLevel.LIMITED
    return TrustLevel.UNTRUSTED


# ---------------------------------------------------------------------------
# Capability matrix
# ---------------------------------------------------------------------------


class Capability(str, Enum):
    DISCOVERY = "discovery"  # view agent card, list capabilities
    SUBMIT_TASKS = "submit_tasks"  # submit new A2A tasks
    QUERY_MEMORY = "query_memory"  # read knowledge / memory stores
    DEFINE_AGENTS = "define_agents"  # contribute new agent definitions


_CAPABILITY_MATRIX: Dict[TrustLevel, Set[Capability]] = {
    TrustLevel.UNTRUSTED: {Capability.DISCOVERY},
    TrustLevel.LIMITED: {Capability.DISCOVERY, Capability.SUBMIT_TASKS},
    TrustLevel.STANDARD: {Capability.DISCOVERY, Capability.SUBMIT_TASKS, Capability.QUERY_MEMORY},
    TrustLevel.TRUSTED: {
        Capability.DISCOVERY,
        Capability.SUBMIT_TASKS,
        Capability.QUERY_MEMORY,
        Capability.DEFINE_AGENTS,
    },
}


class TrustAccessDenied(Exception):
    """Raised when a peer lacks the capability needed for the requested operation."""

    def __init__(self, peer_id: str, capability: Capability, level: TrustLevel) -> None:
        self.peer_id = peer_id
        self.capability = capability
        self.level = level
        super().__init__(f"Peer {peer_id!r} at trust level {level.value} " f"is not permitted to {capability.value}")


def get_capabilities(level: TrustLevel) -> Set[Capability]:
    return frozenset(_CAPABILITY_MATRIX[level])


def has_capability(level: TrustLevel, capability: Capability) -> bool:
    return capability in _CAPABILITY_MATRIX[level]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class TrustRecord:
    """Full state for a single federated peer."""

    peer_id: str

    # Task outcome counters (trailing window)
    success_count: int = 0
    failure_count: int = 0

    # Heartbeat counters for uptime component
    heartbeat_expected: int = 0
    heartbeat_received: int = 0

    # Threat / integrity event counters
    threat_event_count: int = 0
    integrity_violation_count: int = 0

    # Windowed promotion gate
    consecutive_successes: int = 0

    # Current trust state
    current_level: TrustLevel = TrustLevel.UNTRUSTED
    score: float = 0.0

    # Timestamps (Unix epoch floats)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    last_level_change_at: float = field(default_factory=time.time)

    def compute_score(self) -> float:
        total = self.success_count + self.failure_count
        success_rate = self.success_count / total if total > 0 else 0.0

        uptime = self.heartbeat_received / self.heartbeat_expected if self.heartbeat_expected > 0 else 0.0

        # Each threat event reduces threat_score by 0.20 (floor 0).
        threat_score = max(0.0, 1.0 - 0.20 * self.threat_event_count)

        # Each integrity violation reduces integrity_score by 0.25 (floor 0).
        integrity_score = max(0.0, 1.0 - 0.25 * self.integrity_violation_count)

        return round(
            0.4 * success_rate + 0.2 * uptime + 0.2 * threat_score + 0.2 * integrity_score,
            6,
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["current_level"] = self.current_level.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "TrustRecord":
        d = dict(d)
        d["current_level"] = TrustLevel(d["current_level"])
        return cls(**d)


# ---------------------------------------------------------------------------
# Redis key layout
# ---------------------------------------------------------------------------

_KEY_TRUST = "a2a:trust:{}"


def _default_trust_audit_db() -> Path:
    env_override = os.environ.get("AUTOBOT_TRUST_AUDIT_DB")
    if env_override:
        return Path(env_override)
    return config.data_path / "a2a_trust_audit.db"


_SQLITE_DB_DEFAULT = _default_trust_audit_db()


# ---------------------------------------------------------------------------
# TrustScoreManager
# ---------------------------------------------------------------------------


class TrustScoreManager:
    """
    Manages behavioural trust scores for federated A2A peers.

    Thread-safe for read operations.  Write operations rely on Redis
    atomic sets (last-writer-wins within a single heartbeat is acceptable
    because trust scores are soft state).
    """

    def __init__(self, sqlite_path: Optional[Path] = None) -> None:
        self._sqlite_path = sqlite_path or _SQLITE_DB_DEFAULT
        self._ensure_schema()

    # ------------------------------------------------------------------
    # Public record API
    # ------------------------------------------------------------------

    def record_success(self, peer_id: str) -> TrustLevel:
        """Record a successful task completion; may trigger windowed promotion."""
        record = self._load(peer_id)
        record.success_count += 1
        record.consecutive_successes += 1
        self._recompute_with_gate(record)
        self._save(record)
        return record.current_level

    def record_failure(self, peer_id: str) -> TrustLevel:
        """Record a failed/retried task; resets the promotion window."""
        record = self._load(peer_id)
        record.failure_count += 1
        record.consecutive_successes = 0
        self._recompute_with_gate(record)
        self._save(record)
        return record.current_level

    def record_heartbeat(self, peer_id: str, *, received: bool = True) -> TrustLevel:
        """Record a heartbeat event (expected always increments; received only if present)."""
        record = self._load(peer_id)
        record.heartbeat_expected += 1
        if received:
            record.heartbeat_received += 1
        self._recompute_with_gate(record)
        self._save(record)
        return record.current_level

    def record_threat_event(self, peer_id: str) -> TrustLevel:
        """
        Record a PII BLOCK, prompt-injection attempt, or schema violation.

        Applies instant demotion: current level is capped at LIMITED.
        Resets the promotion window.
        """
        record = self._load(peer_id)
        old_level = record.current_level
        record.threat_event_count += 1
        record.consecutive_successes = 0
        record.score = record.compute_score()

        # Instant demotion — cap at LIMITED; do not raise UNTRUSTED peers
        new_level = _LEVEL_ORDER[min(_level_rank(old_level), _level_rank(TrustLevel.LIMITED))]
        self._apply_level_change(record, old_level, new_level, reason="threat_event")
        self._save(record)
        return record.current_level

    def record_integrity_violation(self, peer_id: str) -> TrustLevel:
        """
        Record a card-signature failure, replay attempt, or TTL violation.

        Applies instant demotion to UNTRUSTED.  Resets the promotion window.
        """
        record = self._load(peer_id)
        old_level = record.current_level
        record.integrity_violation_count += 1
        record.consecutive_successes = 0
        record.score = record.compute_score()

        # Integrity violations demote directly to UNTRUSTED
        new_level = TrustLevel.UNTRUSTED
        self._apply_level_change(record, old_level, new_level, reason="integrity_violation")
        self._save(record)
        return record.current_level

    # ------------------------------------------------------------------
    # Capability gate
    # ------------------------------------------------------------------

    def get_trust_level(self, peer_id: str) -> TrustLevel:
        return self._load(peer_id).current_level

    def list_peers(self) -> list[TrustRecord]:
        """Return TrustRecords for all known peers (scanned from Redis)."""
        try:
            r = self._redis()
            keys = r.keys("a2a:trust:*")
            records = []
            for key in keys:
                raw = r.get(key)
                if raw:
                    try:
                        records.append(TrustRecord.from_dict(json.loads(raw)))
                    except Exception:
                        pass
            return sorted(records, key=lambda rec: rec.peer_id)
        except Exception as exc:
            logger.warning("trust_score: list_peers Redis scan failed: %s", exc)
            return []

    def get_audit_log(self, peer_id: str, limit: int = 100) -> list[dict]:
        """Return recent audit snapshots for a peer from SQLite (newest first)."""
        try:
            with sqlite3.connect(self._sqlite_path) as conn:
                rows = conn.execute(
                    """
                    SELECT peer_id, old_level, new_level, score, reason, snapshot_json, recorded_at
                    FROM trust_audit
                    WHERE peer_id = ?
                    ORDER BY recorded_at DESC
                    LIMIT ?
                    """,
                    (peer_id, limit),
                ).fetchall()
            return [
                {
                    "peer_id": r[0],
                    "old_level": r[1],
                    "new_level": r[2],
                    "score": r[3],
                    "reason": r[4],
                    "snapshot": json.loads(r[5]) if r[5] else None,
                    "recorded_at": r[6],
                }
                for r in rows
            ]
        except Exception as exc:
            logger.warning("trust_score: get_audit_log failed peer=%s: %s", peer_id, exc)
            return []

    def get_record(self, peer_id: str) -> TrustRecord:
        return self._load(peer_id)

    def require_capability(self, peer_id: str, capability: Capability) -> None:
        """Raise TrustAccessDenied if the peer lacks the required capability."""
        level = self.get_trust_level(peer_id)
        if not has_capability(level, capability):
            logger.warning(
                "trust_score: access denied peer=%s level=%s capability=%s",
                peer_id,
                level.value,
                capability.value,
            )
            raise TrustAccessDenied(peer_id, capability, level)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _recompute_with_gate(self, record: TrustRecord) -> None:
        """Recompute score and apply level change with asymmetric promotion gate."""
        old_level = record.current_level
        record.score = record.compute_score()
        computed_level = _level_from_score(record.score)

        old_rank = _level_rank(old_level)
        computed_rank = _level_rank(computed_level)

        if computed_rank < old_rank:
            # Demotion — always instant
            new_level = computed_level
        elif computed_rank > old_rank:
            # Promotion — gated by consecutive success window
            if record.consecutive_successes >= PROMOTION_WINDOW:
                new_level = computed_level
            else:
                new_level = old_level
        else:
            new_level = old_level

        self._apply_level_change(record, old_level, new_level, reason="score_update")

    def _apply_level_change(
        self,
        record: TrustRecord,
        old_level: TrustLevel,
        new_level: TrustLevel,
        reason: str,
    ) -> None:
        if new_level == old_level:
            return
        logger.info(
            "trust_score: peer=%s level_change %s→%s score=%.3f reason=%s",
            record.peer_id,
            old_level.value,
            new_level.value,
            record.score,
            reason,
        )
        record.current_level = new_level
        record.last_level_change_at = time.time()
        self._snapshot(record, old_level, new_level)

    # ------------------------------------------------------------------
    # Redis persistence
    # ------------------------------------------------------------------

    def _redis(self):
        from autobot_shared.redis_client import get_redis_client

        return get_redis_client(database="main")

    def _load(self, peer_id: str) -> TrustRecord:
        try:
            r = self._redis()
            raw = r.get(_KEY_TRUST.format(peer_id))
            if raw:
                return TrustRecord.from_dict(json.loads(raw))
        except Exception as exc:
            logger.warning("trust_score: Redis load failed peer=%s: %s", peer_id, exc)
        return TrustRecord(peer_id=peer_id)

    def _save(self, record: TrustRecord) -> None:
        record.updated_at = time.time()
        try:
            r = self._redis()
            r.set(_KEY_TRUST.format(record.peer_id), json.dumps(record.to_dict()))
        except Exception as exc:
            logger.warning("trust_score: Redis save failed peer=%s: %s", record.peer_id, exc)

    # ------------------------------------------------------------------
    # SQLite audit snapshot
    # ------------------------------------------------------------------

    def _ensure_schema(self) -> None:
        try:
            with sqlite3.connect(self._sqlite_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS trust_audit (
                        id            INTEGER PRIMARY KEY AUTOINCREMENT,
                        peer_id       TEXT    NOT NULL,
                        old_level     TEXT,
                        new_level     TEXT    NOT NULL,
                        score         REAL,
                        reason        TEXT,
                        snapshot_json TEXT,
                        recorded_at   REAL    NOT NULL
                    )
                    """)
                conn.commit()
        except Exception as exc:
            logger.warning("trust_score: SQLite schema init failed: %s", exc)

    def _snapshot(
        self,
        record: TrustRecord,
        old_level: Optional[TrustLevel],
        new_level: TrustLevel,
        reason: str = "",
    ) -> None:
        try:
            with sqlite3.connect(self._sqlite_path) as conn:
                conn.execute(
                    """
                    INSERT INTO trust_audit
                        (peer_id, old_level, new_level, score, reason, snapshot_json, recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.peer_id,
                        old_level.value if old_level else None,
                        new_level.value,
                        record.score,
                        reason,
                        json.dumps(record.to_dict()),
                        time.time(),
                    ),
                )
                conn.commit()
        except Exception as exc:
            logger.warning("trust_score: SQLite snapshot failed peer=%s: %s", record.peer_id, exc)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

get_trust_manager = lazy_singleton(TrustScoreManager)
