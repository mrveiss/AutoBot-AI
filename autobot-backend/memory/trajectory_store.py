# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
TrajectoryStore — retrieval-augmented trajectory learning for AutoBot agents.

GH#7357: Stores completed workflow trajectories (task + action sequence +
outcome + reward) in the ``trajectories`` ChromaDB collection so planners can
retrieve similar past solutions instead of re-deriving plans from scratch.

## Reward signal

Reward is a float in [0.0, 1.0] computed from two complementary signals:

*Explicit:* pass ``reward=1.0`` (or any explicit score) when the caller has
direct success/failure information — e.g. acceptance-criteria evaluation from
``SuccessCriteriaEvaluator``.

*Implicit (default):* ``TrajectoryStore.reward_from_execution`` derives a
score from the workflow result dict when no explicit reward is given:
- ``success=True`` with no retry → 1.0
- ``success=True`` with retry → 0.8
- ``success=False`` (partial via criteria) → 0.5
- ``success=False`` with no criteria → 0.0

## Usage

    store = TrajectoryStore()

    # Capture after workflow completion
    traj_id = await store.capture(
        task_text="Deploy service X to staging",
        action_sequence=[{"agent": "deploy_agent", "action": "run_playbook"}],
        outcome="success",
        reward=1.0,
        duration=12.4,
        agent_id="deploy_agent",
        plan_id="plan-abc",
    )

    # Retrieve for planner
    similar = await store.find_similar_trajectories(
        task_text="Deploy service Y to staging",
        top_k=5,
        min_reward=0.7,
    )
"""

import asyncio
import hashlib
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple

from autobot_shared.env_utils import env_flag, env_float, env_int
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_COLLECTION_NAME = "trajectories"
_DEFAULT_TOP_K = 5
_MIN_REWARD_DEFAULT = 0.7

# #11263: consolidation defaults. Duplicate near-identical tasks hurt retrieval
# precision, and stale low-reward failures are noise. Both thresholds are env-tunable.
_CONSOLIDATE_MIN_REWARD_FLOOR = env_float("AUTOBOT_TRAJECTORY_PRUNE_REWARD_FLOOR", default=0.4)
_CONSOLIDATE_MAX_AGE_DAYS = env_int("AUTOBOT_TRAJECTORY_PRUNE_MAX_AGE_DAYS", default=30)
# Upper bound on rows scanned per pass so consolidation stays bounded on huge stores.
_CONSOLIDATE_SCAN_LIMIT = env_int("AUTOBOT_TRAJECTORY_CONSOLIDATE_SCAN_LIMIT", default=50000)

# #11089: retrieval scoping. tenant_id alone is insufficient in single-company
# deployments (org_id is frequently empty/identical across all users), so a
# low-privilege user's trajectory could still be retrieved into another user's
# plan within the same org. Default to strict per-user isolation; an org can
# opt back into shared org-level learning by setting this flag false.
_USER_SCOPED_RETRIEVAL = env_flag("AUTOBOT_TRAJECTORY_USER_SCOPED", default=True)


# ---------------------------------------------------------------------------
# Public data shapes
# ---------------------------------------------------------------------------


class Trajectory:
    """Immutable value object describing one completed workflow execution.

    Attributes:
        trajectory_id: Unique stable ID stored in ChromaDB.
        task_text: Natural-language description of the task (used for embedding).
        start_state_hash: SHA-256 of the serialised start-state dict, or an
            empty string when no start-state was captured.
        action_sequence: Ordered list of action dicts executed during the plan.
        outcome: ``"success"``, ``"partial"``, or ``"failure"``.
        reward: Float in [0.0, 1.0] — higher is better.
        duration: Wall-clock seconds for the full workflow.
        agent_id: The agent (or orchestrator) that executed the plan.
        plan_id: The ``WorkflowPlan.plan_id`` for cross-reference.
        strategy: Execution strategy name (e.g. ``"sequential"``).
        timestamp: UTC datetime of capture.
    """

    __slots__ = (
        "trajectory_id",
        "task_text",
        "start_state_hash",
        "action_sequence",
        "outcome",
        "reward",
        "duration",
        "agent_id",
        "plan_id",
        "strategy",
        "timestamp",
    )

    def __init__(
        self,
        trajectory_id: str,
        task_text: str,
        start_state_hash: str,
        action_sequence: List[Dict[str, Any]],
        outcome: Literal["success", "partial", "failure"],
        reward: float,
        duration: float,
        agent_id: str,
        plan_id: str,
        strategy: str,
        timestamp: datetime,
    ) -> None:
        self.trajectory_id = trajectory_id
        self.task_text = task_text
        self.start_state_hash = start_state_hash
        self.action_sequence = action_sequence
        self.outcome = outcome
        self.reward = reward
        self.duration = duration
        self.agent_id = agent_id
        self.plan_id = plan_id
        self.strategy = strategy
        self.timestamp = timestamp

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trajectory_id": self.trajectory_id,
            "task_text": self.task_text,
            "start_state_hash": self.start_state_hash,
            "action_sequence": self.action_sequence,
            "outcome": self.outcome,
            "reward": self.reward,
            "duration": self.duration,
            "agent_id": self.agent_id,
            "plan_id": self.plan_id,
            "strategy": self.strategy,
            "timestamp": self.timestamp.isoformat(),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hash_start_state(start_state: Optional[Dict[str, Any]]) -> str:
    if not start_state:
        return ""
    canonical = json.dumps(start_state, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def reward_from_execution(result: Dict[str, Any]) -> float:
    """Derive an implicit reward from a WorkflowRunner result dict.

    Rules:
    - success=True, no retry_count → 1.0
    - success=True, retry_count > 0 → 0.8
    - success=False, criteria says "partial" → 0.5
    - success=False → 0.0
    """
    if result.get("success"):
        if result.get("retry_count", 0) > 0:
            return 0.8
        return 1.0
    criteria = result.get("criteria_evaluation", {})
    if isinstance(criteria, dict) and criteria.get("overall") == "partial":
        return 0.5
    return 0.0


def _parse_ts(raw: str) -> Optional[datetime]:
    """Parse a stored ISO timestamp, returning None when absent/malformed."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None


def _dedup_delete_ids(ids: List[str], docs: List[str], metas: List[Dict[str, Any]]) -> set:
    """IDs of duplicate trajectories to drop, keeping the best per (task, user, tenant).

    Two entries collide when their task_text (normalised) and owner match. The
    survivor is the highest reward, ties broken by the most recent timestamp.
    """
    groups: Dict[Tuple[str, str, str], List[Tuple[str, float, str]]] = {}
    for tid, doc, meta in zip(ids, docs, metas):
        key = ((doc or "").strip().lower(), meta.get("user_id", ""), meta.get("tenant_id", ""))
        groups.setdefault(key, []).append((tid, float(meta.get("reward", 0.0)), meta.get("timestamp", "")))
    drop: set = set()
    for entries in groups.values():
        if len(entries) < 2:
            continue
        ranked = sorted(entries, key=lambda e: (e[1], e[2]), reverse=True)
        drop.update(tid for tid, _, _ in ranked[1:])
    return drop


def _stale_delete_ids(
    ids: List[str], metas: List[Dict[str, Any]], reward_floor: float, cutoff: datetime, skip: set
) -> set:
    """IDs of low-reward trajectories older than *cutoff* (excludes already-dropped)."""
    drop: set = set()
    for tid, meta in zip(ids, metas):
        if tid in skip:
            continue
        if float(meta.get("reward", 0.0)) >= reward_floor:
            continue
        ts = _parse_ts(meta.get("timestamp", ""))
        if ts is not None and ts < cutoff:
            drop.add(tid)
    return drop


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class TrajectoryStore:
    """Append-write / similarity-read trajectory bank backed by ChromaDB.

    Collection ``trajectories`` uses HNSW cosine distance on the embedded
    ``task_text`` document.  ChromaDB handles embedding automatically via its
    default ``all-MiniLM-L6-v2`` model (same as every other KB collection).

    One process-level singleton is sufficient.  All methods are coroutine-safe.
    """

    def __init__(self) -> None:
        self._collection = None
        self._init_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_collection(self):
        """Lazily create/open the ``trajectories`` ChromaDB collection."""
        if self._collection is not None:
            return self._collection
        async with self._init_lock:
            if self._collection is not None:
                return self._collection
            from utils.async_chromadb_client import get_async_chromadb_client

            client = await get_async_chromadb_client()
            self._collection = await client.get_or_create_collection(
                name=_COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("TrajectoryStore: collection '%s' ready", _COLLECTION_NAME)
            return self._collection

    # ------------------------------------------------------------------
    # Public API: write path
    # ------------------------------------------------------------------

    async def capture(
        self,
        task_text: str,
        action_sequence: Sequence[Dict[str, Any]],
        outcome: Literal["success", "partial", "failure"],
        reward: float,
        duration: float,
        agent_id: str = "",
        plan_id: str = "",
        strategy: str = "",
        start_state: Optional[Dict[str, Any]] = None,
        timestamp: Optional[datetime] = None,
        tenant_id: str = "",
        user_id: str = "",
    ) -> str:
        """Store a completed workflow trajectory.

        Args:
            task_text: Natural-language task description (becomes the embedding
                document — keep it as the original user request for best retrieval).
            action_sequence: Ordered list of action dicts from the workflow plan.
            outcome: ``"success"``, ``"partial"``, or ``"failure"``.
            reward: Float in [0.0, 1.0].
            duration: Wall-clock seconds for the full workflow.
            agent_id: Executing agent identifier.
            plan_id: ``WorkflowPlan.plan_id`` for cross-reference.
            strategy: Execution strategy name.
            start_state: Optional dict of world-state facts at plan start.
                Stored as a SHA-256 hash; not used for retrieval today.
            timestamp: UTC capture time (defaults to now).

        Returns:
            ``trajectory_id`` of the stored entry.

        Raises:
            ValueError: ``task_text`` is empty, ``reward`` is out of range,
                or ``outcome`` is not one of the three accepted values.
        """
        if not task_text or not task_text.strip():
            raise ValueError("task_text cannot be empty")
        if not (0.0 <= reward <= 1.0):
            raise ValueError(f"reward must be in [0.0, 1.0], got {reward}")
        if outcome not in {"success", "partial", "failure"}:
            raise ValueError(f"outcome must be 'success', 'partial', or 'failure', got {outcome!r}")

        ts = timestamp or datetime.now(tz=timezone.utc)
        traj_id = f"traj_{uuid.uuid4().hex}"
        state_hash = _hash_start_state(start_state)

        metadata: Dict[str, Any] = {
            "start_state_hash": state_hash,
            "action_sequence_json": json.dumps(list(action_sequence), default=str),
            "outcome": outcome,
            "reward": reward,
            "duration": duration,
            "agent_id": agent_id,
            "plan_id": plan_id,
            "strategy": strategy,
            "timestamp": ts.isoformat(),
            # Tenant/user tags for isolation-scoped retrieval (#11015). Empty
            # string = untenanted (legacy); a scoped query filters on these.
            "tenant_id": tenant_id,
            "user_id": user_id,
        }

        collection = await self._get_collection()
        t0 = time.perf_counter()
        await collection.add(
            ids=[traj_id],
            documents=[task_text],
            metadatas=[metadata],
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.debug(
            "TrajectoryStore.capture: id=%s outcome=%s reward=%.2f elapsed_ms=%.1f",
            traj_id,
            outcome,
            reward,
            elapsed_ms,
        )
        return traj_id

    # ------------------------------------------------------------------
    # Public API: read path
    # ------------------------------------------------------------------

    async def find_similar_trajectories(
        self,
        task_text: str,
        top_k: int = _DEFAULT_TOP_K,
        min_reward: float = _MIN_REWARD_DEFAULT,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return the *top_k* most-similar past trajectories above *min_reward*.

        Similarity is computed over ``task_text`` using ChromaDB's HNSW cosine
        index.  The ``min_reward`` post-filter is applied client-side because
        ChromaDB's numeric ``where`` filter on floats can vary by version.

        Args:
            task_text: Description of the current task to find matches for.
            top_k: Maximum number of trajectories to return.  The store queries
                ``top_k * 4`` candidates internally to absorb reward filtering.
            min_reward: Only return trajectories with ``reward >= min_reward``.
            tenant_id: When set, restrict matches to this tenant (#11015).
            user_id: When set and ``AUTOBOT_TRAJECTORY_USER_SCOPED`` is enabled
                (default), also restrict matches to this user — strict
                intra-tenant isolation so one user's trajectory cannot surface in
                another's plan (#11089).

        Returns:
            List of dicts (subset of :class:`Trajectory`.to_dict()) plus a
            ``similarity`` key (float in [0.0, 1.0]).  Ordered by descending
            similarity.  Empty list on empty query or no matches.
        """
        if not task_text or not task_text.strip():
            return []
        if top_k <= 0:
            raise ValueError("top_k must be positive")

        collection = await self._get_collection()
        # Fetch extra candidates so min_reward filtering doesn't starve top_k
        fetch_k = max(top_k * 4, 20)
        # #11015: when a tenant is supplied, isolate the query to that tenant so
        # one org's trajectories can never surface in another's plan. A None/empty
        # tenant_id keeps the un-scoped behaviour (backward compatible for callers
        # and legacy trajectories that predate tenant tagging).
        # #11089: additionally scope by user_id when supplied and user-scoping is
        # enabled (default) — closes intra-tenant cross-user leakage, which
        # tenant-only scoping misses when org_id is empty/shared.
        query_kwargs: Dict[str, Any] = {
            "query_texts": [task_text],
            "n_results": fetch_k,
            "include": ["documents", "metadatas", "distances"],
        }
        scope_user = bool(user_id) and _USER_SCOPED_RETRIEVAL
        where_conditions: List[Dict[str, Any]] = []
        if tenant_id:
            where_conditions.append({"tenant_id": tenant_id})
        if scope_user:
            where_conditions.append({"user_id": user_id})
        if len(where_conditions) == 1:
            query_kwargs["where"] = where_conditions[0]
        elif len(where_conditions) > 1:
            query_kwargs["where"] = {"$and": where_conditions}
        t0 = time.perf_counter()
        try:
            raw = await collection.query(**query_kwargs)
        except Exception as exc:
            logger.error("TrajectoryStore.find_similar_trajectories failed: %s", exc)
            return []

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.debug(
            "TrajectoryStore.find_similar_trajectories: query_ms=%.1f top_k=%d min_reward=%.2f",
            elapsed_ms,
            top_k,
            min_reward,
        )

        ids = raw.get("ids", [[]])[0]
        docs = raw.get("documents", [[]])[0]
        metas = raw.get("metadatas", [[]])[0]
        distances = raw.get("distances", [[]])[0]

        results = []
        for traj_id, doc, meta, dist in zip(ids, docs, metas, distances):
            # Client-side tenant/user backstop — the ChromaDB `where` filter is the
            # primary guard, but enforce again here so a version whose metadata
            # filter is lenient can never leak another tenant's (#11015) or another
            # user's (#11089) trajectory.
            if tenant_id and meta.get("tenant_id", "") != tenant_id:
                continue
            if scope_user and meta.get("user_id", "") != user_id:
                continue
            reward = float(meta.get("reward", 0.0))
            if reward < min_reward:
                continue
            action_seq = json.loads(meta.get("action_sequence_json", "[]"))
            results.append(
                {
                    "trajectory_id": traj_id,
                    "task_text": doc,
                    "similarity": max(0.0, 1.0 - dist),
                    "start_state_hash": meta.get("start_state_hash", ""),
                    "action_sequence": action_seq,
                    "outcome": meta.get("outcome", ""),
                    "reward": reward,
                    "duration": float(meta.get("duration", 0.0)),
                    "agent_id": meta.get("agent_id", ""),
                    "plan_id": meta.get("plan_id", ""),
                    "strategy": meta.get("strategy", ""),
                    "timestamp": meta.get("timestamp", ""),
                }
            )
            if len(results) >= top_k:
                break

        return results

    # ------------------------------------------------------------------
    # Public API: maintenance path
    # ------------------------------------------------------------------

    async def consolidate(
        self,
        reward_floor: float = _CONSOLIDATE_MIN_REWARD_FLOOR,
        max_age_days: int = _CONSOLIDATE_MAX_AGE_DAYS,
        now: Optional[datetime] = None,
    ) -> Dict[str, int]:
        """Compact the ``trajectories`` collection (#11263).

        Two passes, both delete-only so retrieval quality can only improve:
        1. **dedup** — collapse near-identical (task, user, tenant) entries to the
           single highest-reward survivor.
        2. **prune** — drop low-reward (``< reward_floor``) entries older than
           ``max_age_days``.

        Returns a summary dict ``{scanned, duplicates_removed, pruned, remaining}``.
        Non-fatal: on any read error an empty summary is returned and logged.
        """
        collection = await self._get_collection()
        try:
            raw = await collection.get(include=["documents", "metadatas"], limit=_CONSOLIDATE_SCAN_LIMIT)
        except Exception as exc:
            logger.warning("TrajectoryStore.consolidate: read failed (non-fatal): %s", exc)
            return {"scanned": 0, "duplicates_removed": 0, "pruned": 0, "remaining": 0}

        ids = raw.get("ids", []) or []
        docs = raw.get("documents", []) or []
        metas = raw.get("metadatas", []) or []

        dup_ids = _dedup_delete_ids(ids, docs, metas)
        cutoff = (now or datetime.now(tz=timezone.utc)) - timedelta(days=max_age_days)
        stale_ids = _stale_delete_ids(ids, metas, reward_floor, cutoff, skip=dup_ids)

        to_delete = list(dup_ids | stale_ids)
        if to_delete:
            await collection.delete(ids=to_delete)
        summary = {
            "scanned": len(ids),
            "duplicates_removed": len(dup_ids),
            "pruned": len(stale_ids),
            "remaining": len(ids) - len(to_delete),
        }
        logger.info(
            "TrajectoryStore.consolidate: scanned=%d dedup=%d pruned=%d remaining=%d",
            summary["scanned"],
            summary["duplicates_removed"],
            summary["pruned"],
            summary["remaining"],
        )
        return summary


# ---------------------------------------------------------------------------
# Process-level singleton
# ---------------------------------------------------------------------------

_store: TrajectoryStore | None = None
_store_lock = asyncio.Lock()


async def get_trajectory_store() -> TrajectoryStore:
    """Return the process-level TrajectoryStore singleton."""
    global _store
    if _store is not None:
        return _store
    async with _store_lock:
        if _store is None:
            _store = TrajectoryStore()
        return _store
