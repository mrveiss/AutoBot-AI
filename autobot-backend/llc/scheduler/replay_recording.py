# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Recording a heartbeat run for replay, extracted from ``heartbeat_scheduler``.

One concern: taking what an adapter left behind -- its JSONL output file, or the
structured events of an in-process agent -- and writing a replay log row for it.
Nothing here decides *when* an agent runs, which is the rest of the scheduler.

Extracted for #17726. The scheduler sat at its shrink-only size ceiling, so the
idle short-circuit had nowhere to go; this is a seam that was already there, not
a file carved to hit a number. The three functions move verbatim.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from autobot_shared.logging_manager import get_logger

from ..services.replay_service import RunReplayService, parse_jsonl_events

logger = get_logger(__name__)


def _resolve_adapter_output_file(
    adapter_type: str, output_dir: str, agent_id: str, external_run_id: str
) -> Optional[str]:
    """Locate the transcript an adapter run actually wrote (#13614, #14760).

    Delegates to the adapters package, which resolves the path helpers from the
    adapter registered under *adapter_type* rather than importing one family's
    helpers directly. The previous version imported `claude_code_adapter`'s pair
    unconditionally, so the copilot adapters — which name their files
    `llc_copilot_*` rather than `llc_agent_*` — missed on both the state-file
    lookup and the recomputed fallback, every time. The function was generic in
    name only (#14760).
    """
    try:
        from ..adapters.subprocess_base import resolve_transcript_path
    except ImportError:
        # Losing the helpers is a wiring fault, not an absent transcript. The
        # caller cannot tell those apart from a None, so say which it was.
        logger.exception(
            "Could not import adapter path helpers — replay transcript resolution is disabled for run %s",
            external_run_id,
        )
        return None

    return resolve_transcript_path(adapter_type, output_dir, agent_id, external_run_id)


async def record_run_for_replay(
    agent: Dict[str, Any],
    run_id: uuid.UUID,
    context: Dict[str, Any],
    final_status: str,
    *,
    external_run_id: Optional[str] = None,
) -> None:
    """Best-effort replay recording fired after a run reaches terminal status (GH#9034).

    For subprocess adapters the JSONL output file is resolved via the adapter's
    ``_output_path`` helper using the exact ``external_run_id`` returned by
    ``adapter.invoke`` — no mtime glob, no concurrent-run collision (H1 fix).
    For in-process agents there is no file; recorded_events is stored as None.
    Any exception is swallowed so the scheduler is never blocked.
    """
    import asyncio as _asyncio
    import os as _os

    try:
        output_text: Optional[str] = None
        recorded_events = None

        adapter_type = agent.get("adapter_type") or "autobot_agent"
        if adapter_type != "autobot_agent" and external_run_id is not None:
            # Resolve the exact output file via the adapter's own path helper.
            cfg = agent.get("adapter_config") or {}
            output_dir: str = cfg.get("output_dir", "/tmp")  # nosec B108
            agent_id_str = str(agent.get("agent_id", ""))
            output_file: Optional[str] = _resolve_adapter_output_file(
                adapter_type, output_dir, agent_id_str, external_run_id
            )

            if output_file and _os.path.exists(output_file):
                try:
                    raw: str = await _asyncio.to_thread(_read_file_text, output_file)
                    from ..services.replay_service import _REPLAY_OUTPUT_CAP

                    output_text = raw[-_REPLAY_OUTPUT_CAP:] if len(raw) > _REPLAY_OUTPUT_CAP else raw
                    recorded_events = parse_jsonl_events(raw)
                except OSError:
                    logger.warning(
                        "Could not read transcript for replay (run_id: %s) — recording the run without output",
                        run_id,
                    )
            elif output_file:
                # A configured transcript path that does not exist is currently
                # indistinguishable from an empty transcript: the replay record is
                # written either way, with no output and no trace of why.
                logger.warning(
                    "Transcript file for replay does not exist (run_id: %s) — recording the run without output",
                    run_id,
                )

        svc = RunReplayService()
        await svc.record_run(
            run_id=run_id,
            agent=agent,
            context=context,
            final_status=final_status,
            output_text=output_text,
            recorded_events=recorded_events,
        )
    except Exception:
        logger.exception("record_run_for_replay: unexpected error for run %s", run_id)


def _read_file_text(path: str) -> str:
    """Read a file as text — runs in a thread via asyncio.to_thread (M4)."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()
