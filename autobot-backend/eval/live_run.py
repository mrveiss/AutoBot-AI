# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Orchestration of a live eval run: guard, models x repeats, pins (#20843)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from autobot_shared.env_registry import env
from chat_workflow import limits
from chat_workflow.tool_call_loop import _LOOP_ABORT_THRESHOLD
from eval.candidates import live_replay_candidate
from eval.live_guard import EndpointResolver, assert_local_only
from eval.live_judge import Judge, response_judge
from eval.report import RegressionReport, TrajectoryOutcome
from eval.runner import TrajectoryReplayer
from eval.store import GoldenTrajectory, load_golden_set


def _sum_tokens(outcomes: List[TrajectoryOutcome]) -> int | None:
    """Total tokens, or None unless every outcome reported its own: a partial sum is an estimate."""
    counts = [o.tokens for o in outcomes]
    return sum(counts) if counts and all(c is not None for c in counts) else None


def build_pins(
    candidate: Any,
    outcomes: List[TrajectoryOutcome],
    goldens: List[GoldenTrajectory],
    repeat: int,
    label: str,
    judge: str,
) -> Dict[str, Any]:
    """The pins block: everything two reports must share to be comparable, and where the prompts went."""
    models = [
        {
            "model": loc.model,
            "provider": loc.provider,
            "endpoint_class": loc.endpoint_class,
            "local_only": loc.local_only,
            "tokens": _sum_tokens([o for o in outcomes if o.model == loc.model]),
        }
        for loc in candidate.localities.values()
    ]
    return {
        "label": label,
        "step_budget": limits.MAX_CONTINUATION_ITERATIONS,
        "loop_abort_threshold": _LOOP_ABORT_THRESHOLD,
        "timeout": candidate.timeout_s,
        "repeats": repeat,
        "corpus_size": len(goldens),
        "judge_model": judge or None,
        "local_only": all(m["local_only"] for m in models),
        "models": models,
    }


async def run_live_eval(
    models: List[str],
    provider: str,
    repeat: int = 1,
    label: str = "",
    judge_model: str = "",
    allow_remote: bool = False,
    golden_dir: Path | None = None,
    turn_runner: Any = None,
    resolve_endpoint: EndpointResolver | None = None,
    judge: Judge | None = None,
) -> RegressionReport:
    """Run every golden against every model *repeat* times, behind the local-only guard.

    Raises ``RemoteProviderRefused`` before any turn when a model (or the judge) is not local-only.
    """
    goldens = load_golden_set(golden_dir)
    judge_model = judge_model or str(env("AUTOBOT_EVAL_JUDGE_MODEL"))
    judge = judge or (response_judge(judge_model) if judge_model else None)
    extra = {"resolve_endpoint": resolve_endpoint} if resolve_endpoint else {}
    candidate = live_replay_candidate(
        list(dict.fromkeys(models)), provider, turn_runner=turn_runner, judge=judge, allow_remote=allow_remote, **extra
    )
    await candidate.prepare()
    if judge_model:
        await assert_local_only([judge_model], provider, candidate.resolve_endpoint, allow_remote=allow_remote)
    repeats = max(repeat, 1)
    outcomes = await _run_all(candidate, goldens, repeats)
    return RegressionReport(
        outcomes=outcomes, run=build_pins(candidate, outcomes, goldens, repeats, label, judge_model)
    )


async def _run_all(candidate: Any, goldens: List[GoldenTrajectory], repeats: int) -> List[TrajectoryOutcome]:
    """Every golden against every model, *repeats* times; each outcome records which repeat it belongs to."""
    outcomes: List[TrajectoryOutcome] = []
    replayer = TrajectoryReplayer()
    for model in candidate.models:
        for index in range(repeats):
            run = await replayer.run(goldens, candidate.runner_for(model))
            for outcome in run.outcomes:
                outcome.repeat = index
            outcomes.extend(run.outcomes)
    return outcomes
