# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Skill Distillation Scheduler (Issue #12809)

The missing trigger for the extraction pipeline delivered in #4338: a periodic
pass that reads conversations finished since the last run and feeds them through
``SkillExtractor`` -> ``SkillProposer``.

Two properties this scheduler is built around:

*Leader-elected.* Extraction calls an LLM and proposes to the SLM. If every
worker ran the pass, each would propose the same skill from the same
conversation. One elected leader runs it; the rest stay idle. Same Redis
SETNX-with-TTL-lease scheme the connector scheduler uses.

*Durable cursor.* The cursor advances past a conversation only after its
proposal call has returned. A crash mid-pass leaves the cursor on the last
conversation that actually completed, so everything after it is re-offered on
the next run — bounded re-work, never a silently skipped conversation.

Never on the chat request path: extraction is an LLM round-trip and must not add
turn latency.
"""

import asyncio
from typing import Any, Dict, List

from autobot_shared.env_utils import env_flag, env_int
from autobot_shared.leader_lease import LeaderLease
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client

from .skill_extractor import SkillExtractor
from .skill_proposer import SkillProposer

logger = get_logger(__name__)

# Ships inert. Enable deliberately once the LLM cost of an hourly pass is accepted.
DISTILLATION_ENABLED = env_flag("AUTOBOT_SKILL_DISTILLATION_ENABLED", False)
DISTILLATION_INTERVAL_S = env_int("AUTOBOT_SKILL_DISTILLATION_INTERVAL_S", 3600)
# Bounds the LLM spend of any single pass; the remainder is picked up next run
# because the cursor only advances over conversations actually processed.
MAX_SESSIONS_PER_RUN = env_int("AUTOBOT_SKILL_DISTILLATION_MAX_SESSIONS", 10)
# A conversation shorter than this cannot contain a workflow worth extracting;
# SkillExtractor rejects it anyway, so skip it before paying for the load.
MIN_MESSAGES_TO_DISTILL = env_int("AUTOBOT_SKILL_DISTILLATION_MIN_MESSAGES", 4)

_REDIS_DB = "knowledge"
_LEADER_KEY = "skills:distillation:leader"
_CURSOR_KEY = "skills:distillation:cursor"


def _decode(value: object) -> str | None:
    """Decode bytes to str; pass through str and None."""
    if isinstance(value, bytes):
        return value.decode()
    return value if isinstance(value, str) else None


class SkillDistillationScheduler:
    """Periodically distils finished conversations into proposed skills."""

    def __init__(self, extractor: SkillExtractor | None = None, proposer: SkillProposer | None = None) -> None:
        """Initialize with injectable extractor/proposer for testing."""
        self._extractor = extractor
        self._proposer = proposer
        # GH#12835: leader election lives in autobot_shared.leader_lease, shared
        # with the connector scheduler. Only the key and database are ours.
        self._lease = LeaderLease(key=_LEADER_KEY, database=_REDIS_DB, label="Skill distillation")
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> bool:
        """Spawn the leader-election loop. Returns False when the job is toggled off.

        GH#12820: the operator toggle is authoritative; ``DISTILLATION_ENABLED`` remains
        as a deploy-time force-on so an environment can opt in without touching Redis.
        """
        if not await self._enabled():
            logger.info("Skill distillation is toggled off; not starting")
            return False
        if self._task is not None and not self._task.done():
            logger.warning("Skill distillation scheduler already running")
            return True

        self._task = asyncio.create_task(self._leader_loop(), name="skill-distillation-leader")
        logger.info("Skill distillation scheduler started (interval: %ds)", DISTILLATION_INTERVAL_S)
        return True

    async def stop(self) -> None:
        """Cancel the loop and release leadership so another worker can take over."""
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        await self._lease.release()
        logger.info("Skill distillation scheduler stopped")

    # ------------------------------------------------------------------
    # Leader election
    # ------------------------------------------------------------------

    async def _enabled(self) -> bool:
        """Is this job toggled on? (GH#12820)

        ``DISTILLATION_ENABLED`` is an env-level force-on. Otherwise the operator
        toggle decides, falling back to the registry default — so flipping the switch
        takes effect on the next cycle with no restart.
        """
        if DISTILLATION_ENABLED:
            return True
        from services.scheduler_toggles import is_scheduler_enabled

        return await is_scheduler_enabled("SkillDistillationScheduler")

    async def _leader_loop(self) -> None:
        """Hold or acquire the lease; run one distillation pass per cycle while leader."""
        elapsed = DISTILLATION_INTERVAL_S  # run immediately on becoming leader
        while True:
            try:
                # Re-checked every cycle, not just at startup: an operator turning this
                # off must stop the work without needing a restart. The loop keeps
                # running (and keeps the lease honest) so re-enabling also needs no restart.
                if not await self._enabled():
                    await asyncio.sleep(self._lease.poll_s)
                    continue
                await self._lease.update_leadership()
                if self._lease.is_leader and elapsed >= DISTILLATION_INTERVAL_S:
                    await self.run_once()
                    elapsed = 0

                sleep_for = self._lease.refresh_s if self._lease.is_leader else self._lease.poll_s
                await asyncio.sleep(sleep_for)
                elapsed += sleep_for
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Skill distillation leader loop error: %s", exc)
                await asyncio.sleep(self._lease.poll_s)

    # ------------------------------------------------------------------
    # Distillation pass
    # ------------------------------------------------------------------

    async def run_once(self) -> Dict[str, Any]:
        """Distil every conversation finished since the cursor.

        Returns a summary of the pass: sessions seen, sessions distilled, and the
        skill names proposed.
        """
        cursor = await self._read_cursor()
        pending = await self._select_pending_sessions(cursor)
        if not pending:
            logger.debug("Skill distillation: no conversations since cursor %s", cursor or "(start)")
            return {"sessions_seen": 0, "sessions_distilled": 0, "proposed": []}

        distilled, proposed = await self._distil_pending(pending)

        logger.info(
            "Skill distillation pass: %d/%d conversations distilled, %d skills proposed",
            distilled,
            len(pending),
            len(proposed),
        )
        return {"sessions_seen": len(pending), "sessions_distilled": distilled, "proposed": proposed}

    async def _distil_pending(self, pending: List[Dict[str, Any]]) -> tuple[int, List[str]]:
        """Distil each pending conversation in order, advancing the cursor as it goes.

        Stops at the first conversation whose proposal did not land rather than
        skipping it — advancing past a failed session would drop it permanently.
        """
        proposed: List[str] = []
        distilled = 0
        for session in pending:
            names = await self._distil_session(session)
            if names is None:
                break
            proposed.extend(names)
            distilled += 1
            await self._write_cursor(session["updated_at"])
        return distilled, proposed

    async def _distil_session(self, session: Dict[str, Any]) -> List[str] | None:
        """Extract and propose for one conversation. ``None`` means the pass must stop."""
        session_id = session["id"]
        try:
            history = await self._load_history(session_id)
            if len(history) < MIN_MESSAGES_TO_DISTILL:
                return []
            skills = await self._get_extractor().extract_skills(history, self._list_existing_skills())
            if not skills:
                # A conversation that taught nothing reusable is a correct outcome,
                # and still counts as processed — the cursor moves past it.
                return []
            result = await self._get_proposer().propose_skills(skills, session_id=session_id)
            return list(result.get("proposed", []))
        except Exception as exc:
            logger.error("Skill distillation failed for conversation %s: %s", session_id, exc)
            return None

    async def _select_pending_sessions(self, cursor: str | None) -> List[Dict[str, Any]]:
        """Conversations updated after ``cursor``, oldest first, capped per run."""
        manager = await self._get_chat_history_manager()
        if manager is None:
            return []
        sessions = await manager.list_sessions_fast()

        pending = []
        for entry in sessions:
            updated_at = entry.get("updatedAt") or entry.get("lastModified")
            session_id = entry.get("id") or entry.get("chatId")
            if not updated_at or not session_id:
                continue
            if cursor is not None and updated_at <= cursor:
                continue
            pending.append({"id": session_id, "updated_at": updated_at})

        # ISO-8601 timestamps sort lexicographically, so ordering by string keeps the
        # cursor monotonic without parsing every entry.
        pending.sort(key=lambda item: item["updated_at"])
        return pending[:MAX_SESSIONS_PER_RUN]

    async def _load_history(self, session_id: str) -> List[Dict[str, str]]:
        """Load one conversation as ``[{"role": ..., "content": ...}]``."""
        manager = await self._get_chat_history_manager()
        if manager is None:
            return []
        messages = await manager.get_session_messages(session_id)
        return [
            {"role": msg.get("role", "unknown"), "content": msg.get("content", "")}
            for msg in messages
            if msg.get("content")
        ]

    # ------------------------------------------------------------------
    # Cursor
    # ------------------------------------------------------------------

    async def _read_cursor(self) -> str | None:
        """Last distilled conversation timestamp, or None on first ever run."""
        redis = await get_async_redis_client(database=_REDIS_DB)
        if redis is None:
            return None
        try:
            return _decode(await redis.get(_CURSOR_KEY))
        except Exception as exc:
            logger.warning("Skill distillation could not read cursor: %s", exc)
            return None

    async def _write_cursor(self, updated_at: str) -> None:
        """Advance the cursor. Called only after a proposal call has returned."""
        redis = await get_async_redis_client(database=_REDIS_DB)
        if redis is None:
            return
        try:
            await redis.set(_CURSOR_KEY, updated_at)
        except Exception as exc:
            # A cursor that fails to advance costs a re-distillation next run; one that
            # advances without the work having landed costs the conversation entirely.
            logger.warning("Skill distillation could not advance cursor to %s: %s", updated_at, exc)

    # ------------------------------------------------------------------
    # Collaborators (lazy so import stays cheap and tests can inject)
    # ------------------------------------------------------------------

    @staticmethod
    def _list_existing_skills() -> List[Dict[str, str]]:
        """Registered skills as prior art, so extraction can recognise what already exists."""
        try:
            from skills.registry import get_skill_registry

            return [
                {"name": skill.get("name", ""), "description": skill.get("description", "")}
                for skill in get_skill_registry().list_skills()
            ]
        except Exception as exc:
            # Prior art is an accuracy aid, not a precondition — a registry that cannot be
            # read degrades extraction to "propose new only" rather than failing the pass.
            logger.warning("Skill distillation could not list existing skills: %s", exc)
            return []

    def _get_extractor(self) -> SkillExtractor:
        if self._extractor is None:
            self._extractor = SkillExtractor()
        return self._extractor

    def _get_proposer(self) -> SkillProposer:
        if self._proposer is None:
            self._proposer = SkillProposer()
        return self._proposer

    @staticmethod
    async def _get_chat_history_manager():
        """Resolve the shared ChatHistoryManager outside any request scope."""
        try:
            from utils.resource_factory import ResourceFactory

            return await ResourceFactory.get_chat_history_manager()
        except Exception as exc:
            logger.error("Skill distillation could not resolve chat history manager: %s", exc)
            return None


_scheduler: SkillDistillationScheduler | None = None


def get_skill_distillation_scheduler() -> SkillDistillationScheduler:
    """Process-wide scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = SkillDistillationScheduler()
    return _scheduler
