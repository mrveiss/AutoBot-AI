# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The live candidate: drive the real chat graph headless, one golden at a time (#20843).

``LiveChatCandidate`` runs each golden through ``ChatWorkflowManager.process_message`` and reads the final graph
state back, so the eval measures the loop that harness changes actually change. The model is pinned through
chat's own per-session selector (``context["model"]`` -> ``session.metadata["model_override"]``,
``chat_workflow/manager.py``), never through a URL built here. The turn is injectable (``turn_runner``) so a
different runner (an LLC replay) can be measured by the same report later.

Safety: every run gets a throwaway workspace (handed to the ``turn_runner``; chat has no per-session working
directory to point it at, so for the default runner the next two measures are what isolate it), runs under the
bounded ``research_agent`` profile (its ``forbidden_work`` hard-blocks shell and infrastructure tools) and with
every approval category gated, so a mutating tool halts at an approval nobody grants. The first corpus is
read-only as well.
"""

from __future__ import annotations

import asyncio
import math
import shutil
import tempfile
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List

from autobot_shared.env_registry import env
from autobot_shared.env_utils import env_registered
from autobot_shared.logging_manager import get_logger
from eval.live_classify import (  # noqa: F401  (re-exported: the live API surface)
    CATEGORIES,
    FORBIDDEN_TOOL,
    GROUNDED_TASK_CLASSES,
    LiveRunRecord,
    classify_failures,
    is_heuristic,
)
from eval.live_guard import (  # noqa: F401
    EndpointResolver,
    Locality,
    RemoteProviderRefused,
    assert_chains_local,
    assert_local_only,
    classify_locality,
    remote_allowed,
)
from eval.live_judge import Judge
from eval.live_turn import (  # noqa: F401  (re-exported: the live API surface)
    KB_POPULATED,
    READ_ONLY_AGENT_ID,
    GraphDidNotRun,
    build_record,
    chat_endpoint_for,
    chat_resolved_provider,
    chat_turn_runner,
    probe_knowledge_base,
    run_context,
)
from eval.runner import CandidateResult, RecordingUnusable, tools_match
from eval.store import GoldenTrajectory
from orchestration.success_criteria import SuccessCriteria, SuccessCriteriaEvaluator

logger = get_logger(__name__)

#: ``(golden, model, workspace) -> LiveRunRecord``: one headless turn.
TurnRunner = Callable[[GoldenTrajectory, str, Path], Awaitable[LiveRunRecord]]
#: The ``resource_exists`` key a golden uses to require grounded answers; judged apart from the content criteria,
#: so a missing citation is an ``unsupported_claim`` and never also a ``false_done``.
GROUNDED_KEY = "grounded"
#: Resource key that is true only when the turn called no tool at all.
NO_TOOLS_KEY = "no_tool_calls"


def _is_grounding(criterion: SuccessCriteria) -> bool:
    return criterion.parameters.get("key") == GROUNDED_KEY


def _resources(record: LiveRunRecord) -> Dict[str, bool]:
    """What the evaluator's ``resource_exists`` criteria can ask about: tools called, no tools, grounding."""
    resources = {tool: True for tool in record.tool_sequence}
    resources[NO_TOOLS_KEY] = not record.tool_sequence
    resources[GROUNDED_KEY] = bool(record.used_knowledge or record.rag_citations)
    return resources


def _detail(result: Any) -> str:
    return "; ".join(f"{r.criteria.description or r.criteria.criteria_type.value}: {r.detail}" for r in result.results)


async def _evaluate_criteria(record: LiveRunRecord, golden: GoldenTrajectory) -> str:
    """Run the golden's declared criteria over the answer; returns the detail text.

    Grounding criteria are judged separately (``record.grounding_ok``) from the content criteria
    (``record.criteria_overall``), so the two failures stay distinct categories.
    """
    criteria = golden.criteria()
    if not criteria:
        return ""
    workflow_result = {"output": record.final_text, "resources": _resources(record)}
    evaluator = SuccessCriteriaEvaluator()
    content = [c for c in criteria if not _is_grounding(c)]
    grounding = [c for c in criteria if _is_grounding(c)]
    details = []
    if content:
        result = await evaluator.evaluate(content, workflow_result)
        record.criteria_overall = result.overall
        details.append(_detail(result))
    if grounding:
        result = await evaluator.evaluate(grounding, workflow_result)
        record.grounding_ok = result.overall == "full"
        details.append(_detail(result))
    return "; ".join(details)


def forbidden_tools(golden: GoldenTrajectory, record: LiveRunRecord) -> List[str]:
    """Tools the turn called that the golden neither expects nor allows (``allowed_tools`` is empty by default)."""
    permitted = set(golden.expected_tools) | set(golden.allowed_tools)
    return [tool for tool in dict.fromkeys(record.tool_sequence) if tool not in permitted]


def _make_workspace(root: str) -> str:
    return tempfile.mkdtemp(prefix="autobot-eval-", dir=root or None)


def _remove_workspace(workspace: str) -> None:
    """Remove a throwaway workspace; a failure is reported by name (never the full path) and never raised."""
    try:
        shutil.rmtree(workspace)
    except FileNotFoundError:
        pass
    except OSError:
        logger.warning("could not remove the eval workspace %s; remove it by hand", Path(workspace).name)


async def _allocate_workspace(root: str) -> str:
    """A new workspace; if the wait is cancelled, the worker's result is still removed."""
    allocation = asyncio.ensure_future(asyncio.to_thread(_make_workspace, root))
    try:
        return await asyncio.shield(allocation)
    except asyncio.CancelledError:
        allocation.add_done_callback(
            lambda done: _remove_workspace(done.result()) if not done.cancelled() and not done.exception() else None
        )
        raise


def _checked_timeout(timeout_s: float | None) -> float:
    """The per-turn bound: the explicit value, else the registered one; always finite and positive."""
    value = env_registered("AUTOBOT_EVAL_LIVE_TIMEOUT_S", positive_finite=True) if timeout_s is None else timeout_s
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"the live-eval timeout must be a positive finite number of seconds, got {value!r}")
    return float(value)


class LiveChatCandidate:
    """The thing under test for ``--live``: the chat graph, per model, behind the local-only guard."""

    def __init__(
        self,
        models: List[str],
        provider: str,
        turn_runner: TurnRunner | None = None,
        judge: Judge | None = None,
        allow_remote: bool = False,
        resolve_endpoint: EndpointResolver | None = None,
        timeout_s: float | None = None,
        resolve_provider: Callable[[], str] | None = None,
        probe_kb: Callable[[], Awaitable[str]] | None = None,
    ):
        self.models = list(models)
        self.provider = provider
        self.turn_runner = turn_runner or chat_turn_runner
        self.judge = judge
        self.allow_remote = allow_remote
        self.resolve_endpoint = resolve_endpoint or chat_endpoint_for
        self.resolve_provider = resolve_provider or chat_resolved_provider
        self.probe_kb = probe_kb or probe_knowledge_base
        self.timeout_s = _checked_timeout(timeout_s)
        self.localities: Dict[str, Locality] = {}
        #: The pinned judge's locality, set by the orchestrator when a judge model is named.
        self.judge_locality: Locality | None = None
        #: Operator fallback chains that can leave the local provider (non-empty only on an allowed remote run).
        self.remote_chains: List[str] = []
        self.kb_status: str = ""

    #: A candidate over one model is itself a ``CandidateRunner``; the replayer reads these three off it.
    live = True

    @property
    def model(self) -> str | None:
        return self.models[0] if len(self.models) == 1 else None

    async def prepare(self) -> Dict[str, Locality]:
        """Run the guards and probe the KB. Raises ``RemoteProviderRefused`` before any turn can run.

        The provider checked is the one chat resolves; a different ``provider`` label is refused, not trusted.
        """
        resolved = self.resolve_provider()
        if self.provider and self.provider.lower() != resolved.lower():
            raise RemoteProviderRefused(
                f"--provider {self.provider!r} is not the provider chat resolves for its turns ({resolved!r})"
            )
        self.provider = resolved
        self.remote_chains = assert_chains_local(allow_remote=self.allow_remote)
        self.localities = await assert_local_only(
            self.models, resolved, self.resolve_endpoint, allow_remote=self.allow_remote
        )
        self.kb_status = await self.probe_kb()
        return self.localities

    def runner_for(self, model: str) -> "ModelRunner":
        """The candidate runner for one of the configured models."""
        if model not in self.models:
            raise ValueError(f"{model!r} is not one of the configured models {self.models}")
        return ModelRunner(self, model)

    async def __call__(self, golden: GoldenTrajectory) -> CandidateResult:
        if len(self.models) != 1:
            raise ValueError("call runner_for(model) when more than one model is configured")
        return await self.runner_for(self.models[0])(golden)

    async def run_turn(self, golden: GoldenTrajectory, model: str) -> LiveRunRecord:
        """One turn in a throwaway workspace, which is removed whatever happens."""
        await self._recheck_locality(model)
        workspace = await _allocate_workspace(str(env("AUTOBOT_EVAL_WORKSPACE_ROOT")))
        try:
            return await self.turn_runner(golden, model, Path(workspace))
        finally:
            await asyncio.shield(asyncio.to_thread(_remove_workspace, workspace))

    async def _recheck_locality(self, model: str) -> None:
        """Re-resolve the endpoint chat will use for this turn: discovery can move after ``prepare``.

        A turn whose endpoint is no longer local is refused unless the operator allowed it; when allowed, the
        report carries the locality observed, so it cannot keep claiming ``local_only`` for a turn that was not.
        """
        current = await classify_locality(model, self.provider, self.resolve_endpoint)
        if current.local_only:
            return
        if not (self.allow_remote or remote_allowed()):
            raise RemoteProviderRefused(f"{model} now resolves to a non-local endpoint ({current.endpoint_class})")
        self.localities[model] = current


class ModelRunner:
    """A ``CandidateRunner`` bound to one model; the replayer reads ``live``/``model``/``timeout_s`` off it."""

    live = True

    def __init__(self, owner: LiveChatCandidate, model: str):
        self._owner = owner
        self.model = model
        self.provider = owner.provider
        self.timeout_s = owner.timeout_s

    def _require_ready(self, golden: GoldenTrajectory) -> None:
        owner = self._owner
        if self.model not in owner.localities:
            raise RuntimeError("the local-only guard has not run; call LiveChatCandidate.prepare() first")
        criteria = golden.criteria()
        grounded = golden.task_class in GROUNDED_TASK_CLASSES
        if (grounded or any(_is_grounding(c) for c in criteria)) and owner.kb_status != KB_POPULATED:
            # An environment cause, not the model's: with no documents the answer cannot be grounded.
            raise RecordingUnusable(f"environment: the knowledge base is {owner.kb_status or 'unprobed'}")
        if grounded and owner.judge is None and all(_is_grounding(c) for c in criteria):
            # Nothing would check what the answer says, so any short reply after the expected tools would pass.
            raise RecordingUnusable("the golden declares no content criteria and no judge is pinned")

    async def __call__(self, golden: GoldenTrajectory) -> CandidateResult:
        owner = self._owner
        self._require_ready(golden)
        try:
            record = await owner.run_turn(golden, self.model)
        except RecordingUnusable:
            raise
        except Exception as exc:  # noqa: BLE001 - infrastructure failure: "not run", never a pass or a model failure
            logger.warning("live turn for %s failed", golden.trajectory_id, exc_info=True)
            raise RecordingUnusable(f"live turn for {golden.trajectory_id!r} failed: {type(exc).__name__}") from exc
        if not record.final_text.strip() and not record.tool_sequence and record.final_status == "completed":
            raise RecordingUnusable("the turn produced no answer and called no tool")
        detail = await _evaluate_criteria(record, golden)
        record.grounding_required = golden.task_class in GROUNDED_TASK_CLASSES
        if owner.judge is not None and record.grounding_required:
            record.judge_unsupported = await self._judged(golden, record)
        return self._result(golden, record, detail)

    async def _judged(self, golden: GoldenTrajectory, record: LiveRunRecord) -> bool:
        """The pinned judge's verdict; a judge that fails is infrastructure, so the run is ``not_run``."""
        try:
            return await self._owner.judge(record, golden)
        except RecordingUnusable:
            raise
        except Exception as exc:  # noqa: BLE001 - an injected judge may raise anything: never end the replay
            logger.warning("judge for %s failed", golden.trajectory_id, exc_info=True)
            raise RecordingUnusable(f"the judge failed: {type(exc).__name__}") from exc

    def _result(self, golden: GoldenTrajectory, record: LiveRunRecord, detail: str) -> CandidateResult:
        categories = classify_failures(record)
        forbidden = forbidden_tools(golden, record)
        if forbidden:
            categories.append(FORBIDDEN_TOOL)  # counted in the per-model histogram like any other category
        notes = [detail] if detail else []
        if heuristic := [c for c in categories if is_heuristic(record, c)]:
            notes.append(f"heuristic: {', '.join(heuristic)}")
        if forbidden:
            notes.append(f"forbidden_tool: {', '.join(forbidden)}")
        passed = (
            record.final_status == golden.expected_status
            and tools_match(golden.expected_tools, record.tool_sequence, golden.tool_match)
            and record.criteria_overall in (None, "full")
            and record.grounding_ok in (None, True)
            and not categories
            and not forbidden
        )
        return CandidateResult(
            response_text=record.final_text,
            tool_sequence=record.tool_sequence,
            final_status=record.final_status,
            model=self.model,
            provider=self.provider,
            failure_categories=categories,
            passed=passed,
            criteria_detail="; ".join(notes),
            tokens=record.tokens,
        )
