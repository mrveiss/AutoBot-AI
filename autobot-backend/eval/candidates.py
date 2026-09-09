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
- ``recorded_replay_candidate`` — replays *recorded runs*: the tool sequence
  comes from the run's events and the text from its output, so the actual side
  and the expected side have different origins and can disagree.  That property
  is what makes a comparison mean anything, and it is the one the baseline
  lacks at any corpus size (#16157).  A golden with no recording raises
  ``RecordingMissing``: unmeasured is not the same as passing.
- ``live_replay_candidate`` — the wiring hook for a real candidate: dispatch
  the golden's inputs through the LLC replay path and read back the produced
  tool sequence + output.  Left as a thin, clearly-marked seam because a
  full live-agent dispatch needs a DB session + scheduler (see
  ``llc/api/replay.py``); the CLI accepts an injected runner so the
  provider-swap path can supply one without touching this module.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from eval.runner import CandidateResult, CandidateRunner
from eval.store import GoldenTrajectory


class RecordingMissing(RuntimeError):
    """No recorded run exists for a golden, so nothing can be compared.

    Distinct from an empty or failing run: absence of evidence is not a
    passing trajectory, and the caller must be able to tell the two apart.
    """


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


def load_recordings(recorded_dir: Path) -> Dict[str, dict]:
    """Read recorded runs keyed by trajectory id.

    Eager and synchronous on purpose: the replay path is async, so reading
    files inside it would be sync I/O in a coroutine (#7444), and loading up
    front turns a malformed recording into an immediate error rather than one
    surfacing mid-replay.
    """
    if not recorded_dir.is_dir():
        return {}
    return {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in sorted(recorded_dir.glob("*.json"))}


def recorded_replay_candidate(recorded_dir: Path) -> CandidateRunner:
    """A candidate whose answers come from recorded runs, not from the golden.

    This is the property that makes the comparison mean anything: the expected
    side is the golden fixture and the actual side is a record of what the
    system did, so the two can disagree. ``baseline_candidate`` cannot disagree
    with itself at any corpus size (#16157).

    Each golden is matched to ``<recorded_dir>/<trajectory_id>.json`` holding
    the run's ``events`` (read through ``_tools_from_events``), its
    ``output_text`` and its ``final_status``. A golden with no recording raises
    ``RecordingMissing`` rather than falling back to the golden's own values --
    an unmeasured trajectory must not read as a passing one.
    """
    recordings = load_recordings(recorded_dir)

    async def _candidate(golden: GoldenTrajectory) -> CandidateResult:
        record = recordings.get(golden.trajectory_id)
        if record is None:
            raise RecordingMissing(
                f"no recorded run for {golden.trajectory_id!r} in {recorded_dir}; "
                "this trajectory was not measured, which is not the same as passing"
            )
        return CandidateResult(
            response_text=str(record.get("output_text", "")),
            tool_sequence=_tools_from_events(record.get("events") or []),
            final_status=str(record.get("final_status", "completed")),
        )

    return _candidate


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
