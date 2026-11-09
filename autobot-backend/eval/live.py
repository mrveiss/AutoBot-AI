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
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List

from autobot_shared.env_registry import env
from autobot_shared.logging_manager import get_logger
from autobot_shared.tool_catalogue import APPROVAL_CATEGORY_TOOLS
from eval.live_classify import (  # noqa: F401  (re-exported: the live API surface)
    CATEGORIES,
    GROUNDED_TASK_CLASSES,
    LiveRunRecord,
    classify_failures,
    is_heuristic,
)
from eval.live_guard import EndpointResolver, Locality, assert_local_only  # noqa: F401
from eval.live_judge import Judge
from eval.runner import CandidateResult, RecordingUnusable, tools_match
from eval.store import GoldenTrajectory
from orchestration.success_criteria import SuccessCriteriaEvaluator

logger = get_logger(__name__)

#: The bounded profile every live run is governed by (``orchestration.agent_registry``).
READ_ONLY_AGENT_ID = "research_agent"
STATUS_COMPLETED, STATUS_ERROR, STATUS_AWAITING_APPROVAL, STATUS_TIMEOUT = (
    "completed",
    "error",
    "awaiting_approval",
    "timeout",
)

#: ``(golden, model, workspace) -> LiveRunRecord``: one headless turn.
TurnRunner = Callable[[GoldenTrajectory, str, Path], Awaitable[LiveRunRecord]]


def run_context(model: str) -> Dict[str, Any]:
    """The chat context for one live turn: the pinned model, the bounded profile, every approval gate."""
    return {
        "model": model,
        "agent_id": READ_ONLY_AGENT_ID,
        "requires_approval_before": sorted(APPROVAL_CATEGORY_TOOLS),
    }


def _as_dict(message: Any) -> Dict[str, Any]:
    if isinstance(message, dict):
        return message
    return {
        "type": getattr(message, "type", ""),
        "content": getattr(message, "content", ""),
        "metadata": dict(getattr(message, "metadata", None) or {}),
    }


def _final_text(state: Dict[str, Any], messages: List[Dict[str, Any]]) -> str:
    for text in reversed(state.get("all_llm_responses") or []):
        if text and text.strip():
            return text
    replies = [m.get("content", "") for m in messages if m.get("type") == "response"]
    return replies[-1] if replies else ""


def _status(state: Dict[str, Any]) -> str:
    if state.get("error"):
        return STATUS_ERROR
    return STATUS_AWAITING_APPROVAL if state.get("pending_approval") else STATUS_COMPLETED


def build_record(raw_messages: List[Any], state: Dict[str, Any]) -> LiveRunRecord:
    """A ``LiveRunRecord`` from the messages a turn streamed and the graph state read back afterwards."""
    messages = [_as_dict(m) for m in raw_messages]
    history = list(state.get("execution_history") or [])
    return LiveRunRecord(
        final_text=_final_text(state, messages),
        final_status=_status(state),
        tool_sequence=[str(e["tool"]) for e in history if e.get("tool")],
        raw_responses=list(state.get("all_llm_responses") or []),
        messages=messages,
        execution_history=history,
        tool_loop_count=int(state.get("tool_loop_count") or 0),
        iteration_count=int(state.get("iteration_count") or 0),
        should_continue=bool(state.get("should_continue")),
        used_knowledge=bool(state.get("used_knowledge")),
        rag_citations=list(state.get("rag_citations") or []),
        error=state.get("error"),
    )


async def chat_turn_runner(golden: GoldenTrajectory, model: str, workspace: Path) -> LiveRunRecord:
    """The default turn: the real chat graph on a unique throwaway session, whose checkpoints are always removed."""
    from chat_workflow import get_chat_workflow_manager
    from chat_workflow.graph import delete_thread_checkpoints, get_compiled_graph

    manager = get_chat_workflow_manager()
    await manager.initialize()
    session_id = f"eval-{golden.trajectory_id}-{uuid.uuid4().hex}"
    try:
        messages = await manager.process_message(session_id, golden.query, run_context(model))
        graph = await get_compiled_graph(manager)
        snapshot = await graph.aget_state({"configurable": {"thread_id": session_id}})
        return build_record(messages, dict(snapshot.values or {}))
    finally:
        await delete_thread_checkpoints(session_id)


async def chat_endpoint_for(model: str) -> str:
    """The endpoint chat will send *model*'s prompts to: SLM discovery first, then the SSOT routing."""
    from chat_workflow import get_chat_workflow_manager

    manager = get_chat_workflow_manager()
    return await manager._discover_ollama_from_slm() or manager._get_ollama_endpoint_for_model(model)


async def _evaluate_criteria(record: LiveRunRecord, golden: GoldenTrajectory) -> str:
    """Run the golden's declared criteria over the final answer; returns the detail text."""
    criteria = golden.criteria()
    if not criteria:
        return ""
    result = await SuccessCriteriaEvaluator().evaluate(
        criteria, {"output": record.final_text, "resources": {t: True for t in record.tool_sequence}}
    )
    record.criteria_overall = result.overall
    return "; ".join(f"{r.criteria.description or r.criteria.criteria_type.value}: {r.detail}" for r in result.results)


def _make_workspace(root: str) -> str:
    return tempfile.mkdtemp(prefix="autobot-eval-", dir=root or None)


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
    ):
        self.models = list(models)
        self.provider = provider
        self.turn_runner = turn_runner or chat_turn_runner
        self.judge = judge
        self.allow_remote = allow_remote
        self.resolve_endpoint = resolve_endpoint or chat_endpoint_for
        self.timeout_s = timeout_s if timeout_s is not None else float(env("AUTOBOT_EVAL_LIVE_TIMEOUT_S"))
        self.localities: Dict[str, Locality] = {}

    async def prepare(self) -> Dict[str, Locality]:
        """Run the local-only guard. Raises ``RemoteProviderRefused`` before any turn can run."""
        self.localities = await assert_local_only(
            self.models, self.provider, self.resolve_endpoint, allow_remote=self.allow_remote
        )
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
        workspace = await asyncio.to_thread(_make_workspace, str(env("AUTOBOT_EVAL_WORKSPACE_ROOT")))
        try:
            return await self.turn_runner(golden, model, Path(workspace))
        finally:
            await asyncio.to_thread(shutil.rmtree, workspace, True)


class ModelRunner:
    """A ``CandidateRunner`` bound to one model; the replayer reads ``live``/``model``/``timeout_s`` off it."""

    live = True

    def __init__(self, owner: LiveChatCandidate, model: str):
        self._owner = owner
        self.model = model
        self.provider = owner.provider
        self.timeout_s = owner.timeout_s

    async def __call__(self, golden: GoldenTrajectory) -> CandidateResult:
        owner = self._owner
        if self.model not in owner.localities:
            raise RuntimeError("the local-only guard has not run; call LiveChatCandidate.prepare() first")
        try:
            record = await owner.run_turn(golden, self.model)
        except Exception as exc:  # noqa: BLE001 - infrastructure failure: "not run", never a pass or a model failure
            logger.warning("live turn for %s failed", golden.trajectory_id, exc_info=True)
            raise RecordingUnusable(f"live turn for {golden.trajectory_id!r} failed: {type(exc).__name__}") from exc
        detail = await _evaluate_criteria(record, golden)
        record.grounding_required = golden.task_class in GROUNDED_TASK_CLASSES
        if owner.judge is not None and record.grounding_required:
            record.judge_unsupported = await owner.judge(record, golden)
        return self._result(golden, record, detail)

    def _result(self, golden: GoldenTrajectory, record: LiveRunRecord, detail: str) -> CandidateResult:
        categories = classify_failures(record)
        heuristic = [c for c in categories if is_heuristic(record, c)]
        if heuristic:
            detail = "; ".join(filter(None, [detail, f"heuristic: {', '.join(heuristic)}"]))
        passed = (
            record.final_status == golden.expected_status
            and tools_match(golden.expected_tools, record.tool_sequence, golden.tool_match)
            and record.criteria_overall in (None, "full")
            and not categories
        )
        return CandidateResult(
            response_text=record.final_text,
            tool_sequence=record.tool_sequence,
            final_status=record.final_status,
            model=self.model,
            provider=self.provider,
            failure_categories=categories,
            passed=passed,
            criteria_detail=detail,
            tokens=record.tokens,
        )
