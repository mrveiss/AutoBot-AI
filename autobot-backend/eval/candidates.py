# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Candidate runners (GH#10546).

A *candidate* is the thing under test: a model / prompt / skill set,
expressed as an async ``golden -> CandidateResult``.  This module provides
the concrete candidates the CLI and CI use.

- ``baseline_candidate`` — replays the golden's *own* recorded outcome
  (tool sequence + output excerpt).  Running the suite against this is the
  "did the harness itself change?" smoke check and always passes; it is
  also the default so ``python -m eval.run`` is runnable with no live model.
- ``live_replay_candidate`` — the wiring hook for a real candidate: dispatch
  the golden's inputs through the LLC replay path and read back the produced
  tool sequence + output.  Left as a thin, clearly-marked seam because a
  full live-agent dispatch needs a DB session + scheduler (see
  ``llc/api/replay.py``); the CLI accepts an injected runner so the
  provider-swap path can supply one without touching this module.
"""

from __future__ import annotations

from typing import List

from eval.runner import CandidateResult
from eval.store import GoldenTrajectory


async def baseline_candidate(golden: GoldenTrajectory) -> CandidateResult:
    """Echo the golden's own recorded outcome (self-consistency check)."""
    return CandidateResult(
        response_text=golden.expected_output_excerpt or golden.query,
        tool_sequence=list(golden.expected_tools),
        final_status=golden.expected_status,
    )


def _tools_from_events(events: List[dict]) -> List[str]:
    """Extract an ordered tool-name sequence from recorded replay events."""
    tools: List[str] = []
    for event in events or []:
        name = event.get("tool") or event.get("tool_name") or event.get("name")
        if event.get("type") in ("tool_call", "tool_use") and name:
            tools.append(str(name))
        elif name and "tool" in str(event.get("type", "")):
            tools.append(str(name))
    return tools


async def live_replay_candidate(golden: GoldenTrajectory) -> CandidateResult:  # pragma: no cover - wiring seam
    """Dispatch the golden's inputs through the live LLC replay path.

    Wiring seam: a full implementation opens an async session, calls
    ``RunReplayService.replay_run`` + the heartbeat scheduler
    (``llc/api/replay.py``), polls the new run to terminal status, then reads
    back ``recorded_events`` / ``output_text`` from the replay log.  It is
    intentionally not run in unit tests (needs DB + scheduler); the CLI
    injects a runner so callers wire this without editing the harness.
    """
    raise NotImplementedError(
        "live_replay_candidate requires a DB session + heartbeat scheduler; "
        "inject a runner via eval.run(runner=...) to wire the live path."
    )
