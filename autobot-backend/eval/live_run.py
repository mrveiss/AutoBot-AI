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
from eval.live_guard import assert_local_only
from eval.live_judge import response_judge
from eval.report import RegressionReport, TrajectoryOutcome
from eval.runner import TrajectoryReplayer
from eval.store import GoldenTrajectory, load_golden_set


def _sum_tokens(outcomes: List[TrajectoryOutcome]) -> int | None:
    """Total tokens, or None unless every outcome reported its own: a partial sum is an estimate."""
    counts = [o.tokens for o in outcomes]
    return sum(counts) if counts and all(c is not None for c in counts) else None


def _model_pin(loc: Any, outcomes: List[TrajectoryOutcome]) -> Dict[str, Any]:
    return {
        "model": loc.model,
        "provider": loc.provider,
        "endpoint_class": loc.endpoint_class,
        "local_only": loc.local_only,
        "tokens": _sum_tokens([o for o in outcomes if o.model == loc.model]),
    }


def build_pins(
    candidate: Any,
    outcomes: List[TrajectoryOutcome],
    goldens: List[GoldenTrajectory],
    repeat: int,
    label: str,
    judge: str,
) -> Dict[str, Any]:
    """The pins block: everything two reports must share to be comparable, and where the prompts went."""
    models = [_model_pin(loc, outcomes) for loc in candidate.localities.values()]
    return {
        "label": label,
        "step_budget": limits.MAX_CONTINUATION_ITERATIONS,
        "loop_abort_threshold": _LOOP_ABORT_THRESHOLD,
        "timeout": candidate.timeout_s,
        "repeats": repeat,
        "corpus_size": len(goldens),
        "judge_model": judge or None,
        "kb_status": candidate.kb_status,
        "local_only": all(m["local_only"] for m in models),
        "models": models,
    }


def _build_candidate(models: List[str], provider: str, judge_model: str, options: Dict[str, Any]) -> Any:
    """The live candidate, with the pinned judge when one is named (and none was injected)."""
    if options.get("judge") is None and judge_model:
        options["judge"] = response_judge(judge_model)
    options = {k: v for k, v in options.items() if v is not None}
    return live_replay_candidate(list(dict.fromkeys(models)), provider, **options)


async def run_live_eval(
    models: List[str],
    provider: str = "",
    repeat: int = 1,
    label: str = "",
    judge_model: str = "",
    golden_dir: Path | None = None,
    **options: Any,
) -> RegressionReport:
    """Run every golden against every model *repeat* times, behind the local-only guard.

    *options* are the ``LiveChatCandidate`` seams (``turn_runner``, ``judge``, ``allow_remote``,
    ``resolve_endpoint``, ``resolve_provider``, ``probe_kb``). Raises ``RemoteProviderRefused`` before any turn
    when a model, the judge or a fallback chain is not local-only.
    """
    goldens = load_golden_set(golden_dir)
    judge_model = judge_model or str(env("AUTOBOT_EVAL_JUDGE_MODEL"))
    candidate = _build_candidate(models, provider, judge_model, options)
    await candidate.prepare()
    if judge_model:
        await assert_local_only(
            [judge_model], candidate.provider, candidate.resolve_endpoint, allow_remote=candidate.allow_remote
        )
    repeats = max(repeat, 1)
    outcomes = await _run_all(candidate, goldens, repeats)
    pins = build_pins(candidate, outcomes, goldens, repeats, label, judge_model)
    return RegressionReport(outcomes=outcomes, run=pins)


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
