# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Agent run replay service (GH#9034).

Responsibilities:
- record_run: called on terminal-status; writes a LLCRunReplayLog row (non-blocking).
- get_replay_log: fetch recorded log for a run (for step-browser / fixture export).
- replay_run: re-dispatch with stored inputs, creating a new linked run.
- redact_log: apply credential/PII redaction to a log snapshot.
- diff_runs: compute unified text diff of two run output_text values.

Architecture note on step-through:
  For subprocess adapters (claude_code, copilot, etc.) the agent runs as a
  detached CLI process — there is no way to pause/resume it between tool calls
  in real-time.  Instead, recorded_events captures the JSONL output, and the
  frontend step-browses the recorded timeline (post-hoc step-browsing).
  For in-process AutoBotAgentAdapter runs, the same post-hoc approach is used
  (log lines are recorded rather than individual tool calls because the in-
  process adapter does not expose a tool-call hook).  Real-time step-through
  would require invasive adapter refactoring and is explicitly out of scope for
  GH#9034 — see NOTES in the issue.
"""

from __future__ import annotations

import difflib
import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.env_utils import env_int
from user_management.database import get_async_session_factory

from ..models.heartbeat_run import LLCHeartbeatRun
from ..models.replay_log import LLCRunReplayLog

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Caps — configurable via env vars; no hard-coded numbers in function bodies
# ---------------------------------------------------------------------------

# Maximum number of JSONL events stored per run.
_REPLAY_EVENT_CAP: int = env_int("LLC_REPLAY_EVENT_CAP", 2000)

# Maximum bytes stored for output_text.
_REPLAY_OUTPUT_CAP: int = env_int("LLC_REPLAY_OUTPUT_CAP", 131072)  # 128 KiB

# Maximum bytes for output_text_excerpt in fixture export (L1).
_REPLAY_FIXTURE_EXCERPT_CAP: int = env_int("LLC_REPLAY_FIXTURE_EXCERPT_CAP", 2048)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class RunReplayService:
    """Service for recording and replaying heartbeat runs (GH#9034)."""

    async def record_run(
        self,
        run_id: uuid.UUID,
        agent: Dict[str, Any],
        context: Dict[str, Any],
        final_status: str,
        output_text: Optional[str] = None,
        recorded_events: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Persist a replay log for *run_id*.

        Non-blocking best-effort: any exception is caught and logged; the run's
        own status update is never affected.  Callers must NOT await this from
        within an open session that has not been committed (use background task
        pattern).

        For subprocess adapters (claude_code etc.) ``output_text`` and
        ``recorded_events`` carry the JSONL transcript.  For in-process
        (autobot_agent) runs there is no output file so both fields are None.
        """
        factory = get_async_session_factory()
        try:
            # Fetch company_id from the run row (agent dict may not carry it).
            company_id: Optional[uuid.UUID] = None
            agent_id: str = str(agent.get("agent_id", ""))

            async with factory() as session:
                row = await session.execute(select(LLCHeartbeatRun.company_id).where(LLCHeartbeatRun.id == run_id))
                company_id = row.scalar_one_or_none()

            if company_id is None:
                logger.warning(
                    "replay_service.record_run: run %s not found — skipping recording",
                    run_id,
                )
                return

            # M6: store RAW context so replay can re-dispatch with the original
            # values (redacted values would re-inject "***" as inputs).
            # The fixture export endpoint always applies PII redaction on read;
            # the replay-log endpoint applies it when ?redact_pii=true.
            # We strip only agent_api_key (ephemeral run-scoped token) because
            # that value is not needed for faithful replay and is sensitive.
            raw_context = {k: v for k, v in context.items() if k != "agent_api_key"}
            raw_agent = {k: v for k, v in (agent or {}).items() if k != "agent_api_key"}

            # Cap events and output.
            capped_events = recorded_events[:_REPLAY_EVENT_CAP] if recorded_events else None
            capped_output = _cap_text(output_text, _REPLAY_OUTPUT_CAP)

            log_entry = LLCRunReplayLog(
                id=uuid.uuid4(),
                run_id=run_id,
                replay_of_run_id=None,
                company_id=company_id,
                agent_id=agent_id,
                inputs_snapshot=raw_context,
                agent_snapshot=raw_agent,
                recorded_events=capped_events,
                output_text=capped_output,
                final_status=final_status,
            )
            async with factory() as session:
                session.add(log_entry)
                await session.commit()

            logger.debug("replay_service: recorded log for run %s", run_id)

        except Exception:
            logger.exception("replay_service.record_run failed for run %s — skipping", run_id)

    async def get_replay_log(
        self,
        session: AsyncSession,
        run_id: uuid.UUID,
        company_id: uuid.UUID,
        redact_pii: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Return the replay log for *run_id* (org-scoped), or None if absent."""
        result = await session.execute(
            select(LLCRunReplayLog).where(
                LLCRunReplayLog.run_id == run_id,
                LLCRunReplayLog.company_id == company_id,
            )
        )
        log = result.scalar_one_or_none()
        if log is None:
            return None
        return _log_to_dict(log, redact_pii=redact_pii)

    async def replay_run(
        self,
        session: AsyncSession,
        run_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> LLCHeartbeatRun:
        """Create a new heartbeat run re-executing stored inputs for *run_id*.

        Returns the new (QUEUED) run; caller must commit, then call
        ``HeartbeatScheduler.dispatch_run(agent, new_run.id, context)``.
        """
        # Load the original log.
        result = await session.execute(
            select(LLCRunReplayLog).where(
                LLCRunReplayLog.run_id == run_id,
                LLCRunReplayLog.company_id == company_id,
            )
        )
        log = result.scalar_one_or_none()
        if log is None:
            raise ReplayLogNotFoundError(f"No replay log found for run {run_id}")

        agent_snapshot = log.agent_snapshot or {}
        context = dict(log.inputs_snapshot or {})

        from ..models.enums import HeartbeatInvocationSource, LLCRunStatus

        new_run = LLCHeartbeatRun(
            id=uuid.uuid4(),
            company_id=company_id,
            agent_id=log.agent_id,
            invocation_source=HeartbeatInvocationSource.MANUAL.value,
            status=LLCRunStatus.QUEUED.value,
            context_snapshot={"replay_of_run_id": str(run_id), "mode": "replay"},
        )
        session.add(new_run)
        await session.flush()

        # Write the replay log row immediately (replay_of_run_id set).
        replay_log = LLCRunReplayLog(
            id=uuid.uuid4(),
            run_id=new_run.id,
            replay_of_run_id=run_id,
            company_id=company_id,
            agent_id=log.agent_id,
            inputs_snapshot=dict(context),
            agent_snapshot=dict(agent_snapshot),
            recorded_events=None,
            output_text=None,
            final_status=None,
        )
        session.add(replay_log)

        return new_run

    async def get_run_diff(
        self,
        session: AsyncSession,
        run_id_a: uuid.UUID,
        run_id_b: uuid.UUID,
        company_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Return unified text diff between two run output_texts."""
        log_a = await self.get_replay_log(session, run_id_a, company_id)
        log_b = await self.get_replay_log(session, run_id_b, company_id)

        text_a = (log_a or {}).get("output_text") or ""
        text_b = (log_b or {}).get("output_text") or ""

        diff = "\n".join(
            difflib.unified_diff(
                text_a.splitlines(),
                text_b.splitlines(),
                fromfile=f"run/{run_id_a}",
                tofile=f"run/{run_id_b}",
                lineterm="",
            )
        )
        return {
            "run_id_a": str(run_id_a),
            "run_id_b": str(run_id_b),
            "diff": diff,
            "identical": text_a == text_b,
        }

    async def export_fixture(
        self,
        session: AsyncSession,
        run_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Export run as a JSON test fixture (inputs + expected output shape).

        Always applies PII redaction.  For in-process (autobot_agent) runs
        ``output_text`` and ``recorded_events`` will be None — only inputs are
        recorded for those runs since there is no subprocess output file.
        """
        log = await self.get_replay_log(session, run_id, company_id, redact_pii=True)
        if log is None:
            raise ReplayLogNotFoundError(f"No replay log found for run {run_id}")

        run_result = await session.execute(
            select(LLCHeartbeatRun).where(
                LLCHeartbeatRun.id == run_id,
                LLCHeartbeatRun.company_id == company_id,
            )
        )
        run = run_result.scalar_one_or_none()

        return {
            "fixture_version": "1",
            "run_id": str(run_id),
            "agent_id": log.get("agent_id"),
            "final_status": log.get("final_status"),
            "inputs": log.get("inputs_snapshot") or {},
            "agent_config": log.get("agent_snapshot") or {},
            "expected_output": {
                "final_status": run.status if run else log.get("final_status"),
                "output_text_excerpt": _cap_text(log.get("output_text"), _REPLAY_FIXTURE_EXCERPT_CAP),
            },
            "recorded_event_count": len(log.get("recorded_events") or []),
        }


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ReplayLogNotFoundError(Exception):
    """Raised when no replay log is found for the requested run."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _log_to_dict(log: LLCRunReplayLog, *, redact_pii: bool = False) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "id": str(log.id),
        "run_id": str(log.run_id) if log.run_id else None,
        "replay_of_run_id": str(log.replay_of_run_id) if log.replay_of_run_id else None,
        "company_id": str(log.company_id),
        "agent_id": log.agent_id,
        "inputs_snapshot": log.inputs_snapshot,
        "agent_snapshot": log.agent_snapshot,
        "recorded_events": log.recorded_events,
        "output_text": log.output_text,
        "final_status": log.final_status,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }
    if redact_pii:
        data = _redact_log_dict(data)
    return data


def _redact_sensitive(obj: Any) -> Any:
    """Redact credentials from inputs/agent snapshots before storage."""
    if not isinstance(obj, dict):
        return obj
    from llm_shared.credential_redaction import redact_dict  # deferred — avoids top-level import chain issues

    return redact_dict(obj)


def _redact_log_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Deep-redact PII/credential patterns from a log dict for export."""
    from llm_shared.credential_redaction import redact_dict, redact_string  # deferred

    out: Dict[str, Any] = {}
    for k, v in data.items():
        if isinstance(v, dict):
            out[k] = redact_dict(v)
        elif isinstance(v, str):
            out[k] = redact_string(v)
        elif isinstance(v, list):
            out[k] = [
                (
                    redact_dict(item)
                    if isinstance(item, dict)
                    else (redact_string(item) if isinstance(item, str) else item)
                )
                for item in v
            ]
        else:
            out[k] = v
    return out


def _cap_text(text: Optional[str], max_bytes: int) -> Optional[str]:
    """Truncate *text* to *max_bytes* bytes (UTF-8), returning None when empty."""
    if not text:
        return None
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="replace")


def parse_jsonl_events(content: str, cap: int = _REPLAY_EVENT_CAP) -> List[Dict[str, Any]]:
    """Parse JSONL output file content into a list of event dicts.

    Each line is parsed as JSON; non-JSON lines are skipped.  Returns at most
    *cap* events (from the start of the file so the timeline is intact).

    Used by the recording hook in heartbeat_scheduler when reading subprocess
    output files (claude_code, copilot adapters).
    """
    events: List[Dict[str, Any]] = []
    for line in content.splitlines():
        if len(events) >= cap:
            break
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                events.append(obj)
        except (json.JSONDecodeError, ValueError):
            continue
    return events
