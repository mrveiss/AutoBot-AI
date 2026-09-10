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

from autobot_shared.logging_manager import get_logger
from eval.runner import CandidateResult, CandidateRunner, RecordingUnusable
from eval.store import GoldenTrajectory

logger = get_logger(__name__)


class RecordingMissing(RecordingUnusable):
    """No recorded run exists for a golden, so nothing can be compared.

    Distinct from an empty or failing run: absence of evidence is not a
    passing trajectory, and the caller must be able to tell the two apart.
    """


class RecordingUnreadable(RecordingUnusable):
    """A recording exists but could not be parsed into an object.

    Raised at replay time rather than at load time. Loading eagerly is still
    right (#7444 forbids sync I/O in the async replay path), but *raising*
    eagerly meant one corrupt file aborted the whole run before the report was
    written -- turning "one trajectory is unreadable" into "no trajectory was
    reported", and exiting with the code reserved for a regression.
    """


class RecordingIncomplete(RecordingUnusable):
    """A recording omits a field the comparison depends on.

    Defaulting the field is the trap this exists to close: ``final_status``
    defaulted to ``"completed"`` and ``GoldenTrajectory.expected_status``
    defaults to the same string, so a status that was never recorded compared
    equal to the expected one and reported a pass for something never
    measured.
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


def _parse_recording(path: Path) -> dict | None:
    """Parse one recording, or return None if it cannot supply an actual side.

    A file that is not valid JSON, or whose payload is not a JSON object, has
    no fields to compare and is reported as unmeasured for its trajectory. It
    is deliberately not raised here: see ``RecordingUnreadable``.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        logger.warning("recording %s could not be read: %s", path.name, exc)
        return None
    if not isinstance(payload, dict):
        logger.warning("recording %s is %s, not an object", path.name, type(payload).__name__)
        return None
    return payload


def load_recordings(recorded_dir: Path) -> Dict[str, dict | None]:
    """Read recorded runs keyed by trajectory id.

    Eager and synchronous on purpose: the replay path is async, so reading
    files inside it would be sync I/O in a coroutine (#7444).

    An unreadable recording maps to ``None`` rather than propagating. The
    distinction it preserves is the one this module exists for: a key present
    with a ``None`` value means "this trajectory was recorded and the record is
    unusable", while an absent key means "never recorded". Both are unmeasured,
    and neither may abort the run -- a raise here happens before the report is
    emitted, so one corrupt file would suppress the verdicts on every other
    trajectory and exit under the code reserved for a regression.
    """
    if not recorded_dir.is_dir():
        return {}
    return {path.stem: _parse_recording(path) for path in sorted(recorded_dir.glob("*.json"))}


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
        if golden.trajectory_id not in recordings:
            raise RecordingMissing(
                f"no recorded run for {golden.trajectory_id!r}; "
                "this trajectory was not measured, which is not the same as passing"
            )
        record = recordings[golden.trajectory_id]
        if record is None:
            raise RecordingUnreadable(
                f"the recorded run for {golden.trajectory_id!r} could not be parsed; "
                "this trajectory was not measured, which is not the same as passing"
            )
        if "final_status" not in record:
            # No default here, deliberately. `GoldenTrajectory.expected_status`
            # defaults to "completed", so defaulting this side to the same
            # string made an unrecorded status compare equal to the expected
            # one -- a pass asserted about a field nothing ever measured.
            raise RecordingIncomplete(
                f"the recorded run for {golden.trajectory_id!r} has no 'final_status'; "
                "defaulting it would compare equal to the golden's own default"
            )
        return CandidateResult(
            response_text=str(record.get("output_text", "")),
            tool_sequence=_tools_from_events(record.get("events") or []),
            final_status=str(record["final_status"]),
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
