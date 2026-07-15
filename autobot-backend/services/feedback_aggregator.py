# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Preference / Feedback Aggregator — closes the feedback→behavior loop. Issue #10545.

AutoBot already CAPTURES human signals (approvals, rejections, edits, agent-diary
reflections, retrieval feedback) but does not yet CONSUME them to change behavior.
This module is the last wire: it turns those captured signals into durable,
queryable per-user / per-org / per-task-class **preferences**, and exposes a small
read API that ``AgentRouter``, ``StrategyPlanner`` and ``prompt_manager`` call to
BIAS their next choice — bounded, explainable, and tenant-isolated.

Reuse (not a parallel store)
----------------------------
Signals persist in the SAME Redis ``analytics`` database used by
``knowledge.search_components.retrieval_learner.RetrievalLearner`` and follow its
established conventions: exponential-moving-average scoring, 30-day TTL, and
namespaced keys. This generalises the per-retrieval learner into a cross-cutting
preference surface rather than adding a second learning system.

Redis key layout (tenant-isolated)
----------------------------------
pref:signal:{org_id}:{user_id}:{task_class}:{behavior}  HASH
    fields: reject_count, accept_count, edit_count, aversion (EMA in [0,1]),
            last_reason, last_seen

``org_id`` is the FIRST namespace segment so a signal from org A can never be read
under org B's scope — cross-org leakage is structurally impossible.
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from constants.ttl_constants import TTL_30_DAYS

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Preferences share the retrieval-learner 30-day horizon.
_SIGNAL_TTL_SECONDS = TTL_30_DAYS
# Key namespace prefix (org_id is the first — isolating — segment).
_SIGNAL_KEY_PREFIX = "pref:signal:"
# EMA smoothing factor — one event nudges, never overrides (mirrors learner alpha).
_EMA_ALPHA = 0.2
# Aversion below this is treated as "no learned preference" (noise floor).
_AVERSION_FLOOR = 0.15
# Minimum observed events before a preference is allowed to influence behavior.
_MIN_EVIDENCE = 3
# Hard cap on how far a single preference may shift a downstream score/weight.
# Bounded influence: a signal biases, it never fully overrides the base choice.
_MAX_BIAS = 0.30
# Best-effort Redis budget (seconds). Consumption hooks fire on the hot path;
# a slow/unavailable Redis degrades to "no bias" rather than blocking the agent.
_REDIS_TIMEOUT_SECONDS = 1.5
# Sentinels for unauthenticated / org-less scope.
GLOBAL_ORG = "__global_org__"
GLOBAL_USER = "__global_user__"

# Action → which counter it increments and its aversion contribution [0,1].
# rejected/edited raise aversion; accepted lowers it.
_ACTION_WEIGHTS = {
    "rejected": 1.0,
    "edited": 0.6,
    "accepted": 0.0,
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PreferenceSignal:
    """A durable per-(org, user, task-class, behavior) preference signal."""

    org_id: str
    user_id: str
    task_class: str
    behavior: str
    reject_count: int = 0
    accept_count: int = 0
    edit_count: int = 0
    aversion: float = 0.0  # EMA in [0,1]; higher = humans dislike this behavior
    last_reason: str = ""
    last_seen: float = field(default_factory=time.time)

    def to_redis_mapping(self) -> Dict[str, str]:
        """Serialise to a flat string dict for Redis HSET."""
        return {
            "org_id": self.org_id,
            "user_id": self.user_id,
            "task_class": self.task_class,
            "behavior": self.behavior,
            "reject_count": str(self.reject_count),
            "accept_count": str(self.accept_count),
            "edit_count": str(self.edit_count),
            "aversion": str(self.aversion),
            "last_reason": self.last_reason,
            "last_seen": str(self.last_seen),
        }

    @classmethod
    def from_redis_mapping(cls, mapping: Dict) -> "PreferenceSignal":
        """Deserialise from a Redis HGETALL response (bytes or str)."""

        def _dec(v):
            return v.decode("utf-8") if isinstance(v, bytes) else v

        m = {_dec(k): _dec(v) for k, v in mapping.items()}
        return cls(
            org_id=m.get("org_id", GLOBAL_ORG),
            user_id=m.get("user_id", GLOBAL_USER),
            task_class=m.get("task_class", "general"),
            behavior=m.get("behavior", ""),
            reject_count=int(m.get("reject_count", 0)),
            accept_count=int(m.get("accept_count", 0)),
            edit_count=int(m.get("edit_count", 0)),
            aversion=float(m.get("aversion", 0.0)),
            last_reason=m.get("last_reason", ""),
            last_seen=float(m.get("last_seen", 0.0)),
        )

    def events(self) -> int:
        """Total observed events backing this signal."""
        return self.reject_count + self.accept_count + self.edit_count


@dataclass
class PreferenceBias:
    """A bounded, explainable adjustment returned to a consumption hook."""

    behavior: str
    aversion: float
    bias: float  # signed magnitude in [-_MAX_BIAS, _MAX_BIAS]; negative = avoid
    explanation: str
    evidence_events: int

    def to_trajectory_entry(self) -> Dict[str, object]:
        """Structured record for the trajectory/decision log (explainability)."""
        return {
            "kind": "preference_bias",
            "behavior": self.behavior,
            "aversion": round(self.aversion, 3),
            "bias": round(self.bias, 3),
            "explanation": self.explanation,
            "evidence_events": self.evidence_events,
        }


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


class FeedbackAggregator:
    """Turns captured human signals into durable, biasing preferences (#10545).

    Write path:  ``record_signal(action, behavior, ...)`` — called by feedback
    capture / approval_workflow / diary reflection ingestion.
    Read path:   ``get_bias(behavior, ...)`` and ``get_biases_for_class(...)`` —
    called by the three consumption hooks.

    Storage reuses the RetrievalLearner ``analytics`` Redis database and its
    EMA + 30-day-TTL conventions; org_id is the first key segment so scopes
    cannot leak across tenants.
    """

    def __init__(self, redis=None) -> None:
        self._redis = redis
        # Set True after a timed-out/failed acquisition so hot-path hooks stop
        # paying the Redis budget repeatedly when the store is unreachable.
        self._redis_unavailable = False

    # ------------------------------------------------------------------
    # Redis access (mirrors RetrievalLearner._get_redis)
    # ------------------------------------------------------------------

    async def _get_redis(self):
        """Lazily obtain the async ``analytics`` Redis client (shared with learner).

        Acquisition is time-boxed so a stuck connection/retry-storm on the hot
        path degrades to ``None`` (no bias) instead of blocking routing/planning.
        """
        if self._redis is not None:
            return self._redis
        if self._redis_unavailable:
            return None
        from autobot_shared.redis_client import get_redis_client

        try:
            self._redis = await asyncio.wait_for(
                get_redis_client(async_client=True, database="analytics"),
                timeout=_REDIS_TIMEOUT_SECONDS,
            )
        except (asyncio.TimeoutError, Exception) as exc:  # noqa: BLE001
            self._redis_unavailable = True
            logger.warning("FeedbackAggregator: Redis unavailable, bias disabled: %s", exc)
            return None
        return self._redis

    @staticmethod
    def _key(org_id: str, user_id: str, task_class: str, behavior: str) -> str:
        """Build the tenant-isolated signal key (org_id first — no leakage)."""
        return f"{_SIGNAL_KEY_PREFIX}{org_id}:{user_id}:{task_class}:{behavior}"

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    async def record_signal(
        self,
        action: str,
        behavior: str,
        *,
        task_class: str = "general",
        user_id: str | None = None,
        org_id: str | None = None,
        reason: str = "",
    ) -> None:
        """Fold one captured human signal into the durable preference store.

        Args:
            action:     One of ``accepted`` / ``rejected`` / ``edited``.
            behavior:   The behavior being judged (e.g. an agent id, skill name,
                        strategy, or prompt-style tag).
            task_class: Task category the judgement applies to (e.g. ``code-fix``).
            user_id:    Authenticated user; global sentinel when None.
            org_id:     Tenant; global sentinel when None. First key segment.
            reason:     Optional human/diary rationale, surfaced in explanations.
        """
        weight = _ACTION_WEIGHTS.get(action)
        if weight is None:
            logger.debug("FeedbackAggregator: ignoring unknown action %s", action)
            return
        if not behavior:
            return

        org = org_id or GLOBAL_ORG
        uid = user_id or GLOBAL_USER
        key = self._key(org, uid, task_class, behavior)
        try:
            redis = await self._get_redis()
            if redis is None:
                return
            existing = await redis.hgetall(key)
            signal = (
                PreferenceSignal.from_redis_mapping(existing)
                if existing
                else PreferenceSignal(org_id=org, user_id=uid, task_class=task_class, behavior=behavior)
            )
            self._apply_action(signal, action, weight, reason)
            await redis.hset(key, mapping=signal.to_redis_mapping())
            await redis.expire(key, _SIGNAL_TTL_SECONDS)
            logger.debug(
                "FeedbackAggregator: %s '%s' (class=%s aversion=%.2f)",
                action,
                behavior,
                task_class,
                signal.aversion,
            )
        except Exception as exc:  # noqa: BLE001 — best-effort, never break capture
            logger.warning("FeedbackAggregator: record_signal failed for %s: %s", key, exc)

    @staticmethod
    def _apply_action(signal: PreferenceSignal, action: str, weight: float, reason: str) -> None:
        """Update counters and the EMA aversion for one event (nudge, not override)."""
        if action == "rejected":
            signal.reject_count += 1
        elif action == "edited":
            signal.edit_count += 1
        else:
            signal.accept_count += 1
        signal.aversion = signal.aversion * (1.0 - _EMA_ALPHA) + weight * _EMA_ALPHA
        signal.last_seen = time.time()
        if reason:
            signal.last_reason = reason[:200]

    # ------------------------------------------------------------------
    # Read path (consumption hooks call these)
    # ------------------------------------------------------------------

    async def get_bias(
        self,
        behavior: str,
        *,
        task_class: str = "general",
        user_id: str | None = None,
        org_id: str | None = None,
    ) -> PreferenceBias | None:
        """Return a bounded, explainable bias for ``behavior``, or None.

        Lookup order (tenant-isolated): user-scoped within the org first, then
        the org-wide (all-users) fallback. A GLOBAL_ORG signal is NEVER consulted
        for a real org, and org A is never read under org B.

        The returned ``bias`` is capped at ``±_MAX_BIAS`` — it can only nudge a
        downstream score, never fully override the base choice.
        """
        signal = await self._best_signal(behavior, task_class, user_id, org_id)
        if signal is None:
            return None
        return self._to_bias(signal)

    async def _best_signal(
        self,
        behavior: str,
        task_class: str,
        user_id: str | None,
        org_id: str | None,
    ) -> PreferenceSignal | None:
        """Fetch the strongest qualifying signal from user then org-wide scope."""
        org = org_id or GLOBAL_ORG
        candidates: List[str] = []
        if user_id:
            candidates.append(self._key(org, user_id, task_class, behavior))
        candidates.append(self._key(org, GLOBAL_USER, task_class, behavior))
        try:
            redis = await self._get_redis()
            if redis is None:
                return None
            best: PreferenceSignal | None = None
            for key in candidates:
                raw = await redis.hgetall(key)
                if not raw:
                    continue
                signal = PreferenceSignal.from_redis_mapping(raw)
                if signal.events() < _MIN_EVIDENCE or signal.aversion < _AVERSION_FLOOR:
                    continue
                if best is None or signal.aversion > best.aversion:
                    best = signal
            return best
        except Exception as exc:  # noqa: BLE001
            logger.warning("FeedbackAggregator: _best_signal failed for %s: %s", behavior, exc)
            return None

    @staticmethod
    def _to_bias(signal: PreferenceSignal) -> PreferenceBias:
        """Map an aversion signal to a bounded negative bias + explanation."""
        # Aversion in [floor,1] → magnitude in [0,_MAX_BIAS]; sign negative (avoid).
        span = max(1e-6, 1.0 - _AVERSION_FLOOR)
        magnitude = min(_MAX_BIAS, _MAX_BIAS * (signal.aversion - _AVERSION_FLOOR) / span)
        reason_tail = f" ({signal.last_reason})" if signal.last_reason else ""
        explanation = (
            f"biased away from '{signal.behavior}' for task-class '{signal.task_class}': "
            f"humans rejected/edited it {signal.reject_count + signal.edit_count}× "
            f"(aversion={signal.aversion:.2f}){reason_tail}"
        )
        return PreferenceBias(
            behavior=signal.behavior,
            aversion=signal.aversion,
            bias=-magnitude,
            explanation=explanation,
            evidence_events=signal.events(),
        )

    async def get_biases_for_class(
        self,
        behaviors: List[str],
        *,
        task_class: str = "general",
        user_id: str | None = None,
        org_id: str | None = None,
    ) -> Dict[str, PreferenceBias]:
        """Return biases for a set of candidate behaviors (skill/agent selection)."""
        result: Dict[str, PreferenceBias] = {}
        for behavior in behaviors:
            bias = await self.get_bias(behavior, task_class=task_class, user_id=user_id, org_id=org_id)
            if bias is not None:
                result[behavior] = bias
        return result


get_feedback_aggregator = lazy_singleton(FeedbackAggregator)


# ---------------------------------------------------------------------------
# Serialisation helper for consumers that log to the trajectory
# ---------------------------------------------------------------------------


def biases_to_trajectory(biases: Dict[str, PreferenceBias]) -> str:
    """JSON-encode a bias map for embedding in a trajectory/decision log field."""
    return json.dumps(
        {b: pb.to_trajectory_entry() for b, pb in biases.items()},
        ensure_ascii=False,
    )
