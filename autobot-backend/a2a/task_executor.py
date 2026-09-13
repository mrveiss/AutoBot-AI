# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
A2A Task Executor

Issue #961: Bridges incoming A2A tasks to AutoBot's existing DistributedAgentCoordinator.
Runs as a FastAPI BackgroundTask so the POST /tasks endpoint returns immediately
with the task ID while execution continues asynchronously.
Issue #7358: Phase 2 — records task outcomes to the behavioural trust score manager
so peer trust levels evolve continuously from real interaction history.
"""

from typing import Any, Dict

from agents.declared_scope_check import INVALID_DECLARED_SCOPE
from agents.scope_enforcement import hold_scopes
from autobot_shared.coordination.work_claims import ScopeError
from autobot_shared.logging_manager import get_logger

from .pii_pipeline import PIIBlocked, scrub_outbound
from .self_evaluator import DEFAULT_EVAL_THRESHOLD, evaluate_task_output
from .task_manager import _TERMINAL_STATES, get_task_manager
from .trust_score import get_trust_manager
from .types import TaskArtifact, TaskState

logger = get_logger(__name__)


async def _is_cancelled(task_id: str, manager) -> bool:
    """True once `task_id` has moved to CANCELLED underneath a running executor.

    Checked at defined points inside `_execute_claimed` (#16174) -- never
    inside a single call into the orchestrator, which this cannot interrupt
    once it has started. Cancelling stops the NEXT checkpoint from doing more
    work; it does not abort work already in flight.
    """
    task = manager.get_task(task_id)
    return task is not None and task.status.state == TaskState.CANCELLED


async def _abort_if_cancelled(task_id: str, manager, where: str) -> bool:
    """A checkpoint: log and return True once cancellation should stop more work."""
    if await _is_cancelled(task_id, manager):
        logger.info("A2A task %s cancelled %s; no further work performed", task_id, where)
        return True
    return False


def _extract_response_text(result: Dict[str, Any]) -> str:
    """Pull the human-readable response from an orchestrator result dict.

    Issue #4501: include "response_text" key used by ChatAgent._build_chat_payload.
    """
    for key in ("response", "response_text", "message", "text", "output"):
        value = result.get(key)
        if value and isinstance(value, str):
            return value
    return str(result)


def _extract_routing_metadata(result: Dict[str, Any]) -> Dict[str, Any] | None:
    """Extract non-response metadata (agent used, timing, etc.) from result."""
    skip = {"response", "response_text", "message", "text", "output"}
    meta = {k: v for k, v in result.items() if k not in skip}
    return meta if meta else None


async def execute_a2a_task(
    task_id: str,
    input_text: str,
    context: Dict[str, Any] | None = None,
    eval_threshold: float = DEFAULT_EVAL_THRESHOLD,
    peer_id: str | None = None,
) -> None:
    """
    Execute an A2A task via the existing DistributedAgentCoordinator.

    Lifecycle:
      SUBMITTED → WORKING → (adds text + metadata artifacts)
                          → [self-eval quality gate]
                          → COMPLETED  (confidence >= eval_threshold)
                          → FAILED     (confidence < eval_threshold, eval_reason in metadata)

    This function is intentionally fire-and-forget (called via BackgroundTasks).

    Args:
        task_id: Unique A2A task identifier.
        input_text: Original task input from the caller.
        context: Optional extra context forwarded to the orchestrator.
        eval_threshold: Minimum self-eval confidence score required before
            transitioning to COMPLETED (default: DEFAULT_EVAL_THRESHOLD = 0.6).
        peer_id: Caller's X-A2A-Agent-Id (Issue #7358 phase 2: used to record
            behavioural trust outcomes against the submitting peer).
    """
    manager = get_task_manager()
    manager.update_state(task_id, TaskState.WORKING)
    manager.publish_event(task_id, {"event": "state_change", "state": "working", "task_id": task_id})

    # #15950: the scopes this task will touch, declared by the submitter. The
    # executor cannot ask an agent for them -- it calls the orchestrator, which
    # routes internally, so no specific agent is known here. Agent-level claims
    # are taken separately in `BaseAgent.execute_with_tracking`; these are the
    # task-level ones, and an empty declaration keeps today's behaviour exactly.
    declared = list((context or {}).get("declared_scopes") or [])

    async def _task_is_over() -> bool:
        task = manager.get_task(task_id)
        return task is None or task.status.state in _TERMINAL_STATES

    try:
        async with hold_scopes(
            declared, agent_id="a2a-executor", task_id=task_id, intent=input_text[:120], stop=_task_is_over
        ) as held:
            if not held.granted:
                _report_refusal(manager, task_id, held.conflict)
                return
            await _execute_claimed(task_id, input_text, context, eval_threshold, peer_id, manager)
    except ScopeError as exc:
        # `declared_scopes` is caller-supplied, so a typo reaches Scope.parse and
        # raises ScopeError -- which is not ClaimUnavailable, so hold_scopes does not
        # catch it. This function is fire-and-forget via BackgroundTasks, so nothing
        # above catches it either: the task sat in WORKING forever, indistinguishable
        # from one still working (#16209).
        #
        # Failed, not refused. A refusal answers "blocked by what" with a holder; this
        # has no holder, and reporting it as a conflict would put a fourth meaning on
        # ClaimConflict, which already renders three incompatible ways (#16208).
        _report_bad_scope(manager, task_id, declared, exc)


def _report_bad_scope(manager, task_id: str, declared: list, exc: Exception) -> None:
    """Fail the task naming the rejected declaration, not a bare error.

    The submitter's next question is "which one, and why" -- ScopeError already
    says both, and the declared list says what was sent.
    """
    logger.warning("task %s declared an unparseable scope: %s", task_id, exc)
    manager.add_artifact(
        task_id,
        TaskArtifact(
            artifact_type="json",
            content={"declared_scopes": list(declared), "reason": str(exc)},
        ),
    )
    manager.update_state(task_id, TaskState.FAILED, message=INVALID_DECLARED_SCOPE)
    manager.publish_event(
        task_id,
        {
            "event": "state_change",
            "state": "failed",
            "terminal": True,
            "message": INVALID_DECLARED_SCOPE,
            "task_id": task_id,
        },
    )


def _report_refusal(manager, task_id: str, conflict) -> None:
    """Fail the task with the holder named, not with a bare error.

    The operator's next question is "blocked by what?" -- a refusal that does not
    answer it turns a coordination event into a mystery, and the conflict object
    already renders holder, task, mode, expiry and intent.
    """
    manager.add_artifact(
        task_id,
        TaskArtifact(
            artifact_type="json",
            content={
                "refused_scope": conflict.requested,
                "held_by_agent": conflict.holder.agent_id,
                "held_by_task": conflict.holder.task_id,
                "holder_intent": conflict.holder.intent,
                "holder_expires_at": conflict.holder.expires_at,
                "reason": str(conflict),
            },
        ),
    )
    manager.update_state(task_id, TaskState.FAILED, message="scope_conflict")
    manager.publish_event(
        task_id,
        {
            "event": "state_change",
            "state": "failed",
            "terminal": True,
            "message": "scope_conflict",
            "task_id": task_id,
        },
    )
    logger.info("A2A task %s refused: %s", task_id, conflict)


def _scrub_inbound(task_id: str, input_text: str, peer_id: str | None, manager) -> str | None:
    """Scrub the inbound payload; None means the PII pipeline blocked it (#7355).

    None means "already reported" -- the task is failed and its event published
    here, so the caller returns rather than deciding again. Returning the text
    with a separate flag would let a caller keep using it after a block, which
    is the one thing this must not permit.
    """
    # Issue #7355: Scrub inbound payload before forwarding to orchestrator.
    # Prevents PII/credentials that arrived in the A2A request from leaking
    # into downstream RAG retrieval, agent prompts, or external API calls.
    try:
        scrub_result = scrub_outbound(input_text, peer_id=task_id, message_id=task_id)
        if scrub_result.redaction_count > 0:
            logger.info(
                "A2A task %s: scrubbed %d PII item(s) from inbound payload",
                task_id,
                scrub_result.redaction_count,
            )
        return scrub_result.text
    except PIIBlocked as exc:
        logger.warning("A2A task %s: inbound payload blocked by PII pipeline: %s", task_id, exc)
        # Issue #7358 phase 2: inbound PII block is a threat event.
        if peer_id:
            try:
                get_trust_manager().record_threat_event(peer_id)
            except Exception as trust_exc:
                logger.warning("trust_score: threat_event record failed peer=%s: %s", peer_id, trust_exc)
        manager.update_state(task_id, TaskState.FAILED, message="Blocked: PII detected in request")
        manager.publish_event(
            task_id,
            {
                "event": "state_change",
                "state": "failed",
                "terminal": True,
                "task_id": task_id,
                "message": "pii_blocked",
            },
        )
        return None


def _fail_on_eval(task_id: str, eval_result, eval_threshold: float, peer_id: str | None, manager) -> None:
    """The self-eval verdict said no: record why, then fail the task.

    Split from `_apply_eval_gate` only for length (#620). The confidence and
    threshold are both recorded because a failure that reports one without the
    other cannot be judged -- 0.55 is a pass or a fail depending on the bar.
    """
    eval_artifact = TaskArtifact(
        artifact_type="json",
        content={
            "eval_reason": eval_result.eval_reason,
            "eval_confidence": eval_result.confidence,
            "eval_threshold": eval_threshold,
        },
    )
    manager.add_artifact(task_id, eval_artifact)
    manager.update_state(
        task_id,
        TaskState.FAILED,
        message=eval_result.eval_reason,
    )
    manager.publish_event(
        task_id,
        {
            "event": "state_change",
            "state": "failed",
            "terminal": True,
            "task_id": task_id,
            "eval_confidence": eval_result.confidence,
            "eval_reason": eval_result.eval_reason,
        },
    )
    logger.warning(
        "A2A task %s failed self-eval (confidence=%.4f): %s",
        task_id,
        eval_result.confidence,
        eval_result.eval_reason,
    )
    # Issue #7358 phase 2: self-eval failure → negative trust signal.
    if peer_id:
        try:
            get_trust_manager().record_failure(peer_id)
        except Exception as trust_exc:
            logger.warning("trust_score: record_failure failed peer=%s: %s", peer_id, trust_exc)


def _apply_eval_gate(task_id: str, eval_result, eval_threshold: float, peer_id: str | None, manager) -> None:
    """Move the task to its terminal state on the self-eval verdict (#4687).

    Extracted for length, not reuse: `_execute_claimed` inherited the whole of
    the original `execute_a2a_task` body when the claim wrapper was added, and
    at 159 lines it failed the function-length guard (#620). The split follows
    the seam the original comments already drew.
    """
    if eval_result.passed:
        manager.update_state(task_id, TaskState.COMPLETED)
        manager.publish_event(
            task_id,
            {
                "event": "state_change",
                "state": "completed",
                "terminal": True,
                "task_id": task_id,
                "eval_confidence": eval_result.confidence,
            },
        )
        logger.info(
            "A2A task %s completed (confidence=%.4f)",
            task_id,
            eval_result.confidence,
        )
        # Issue #7358 phase 2: successful task → positive trust signal.
        if peer_id:
            try:
                get_trust_manager().record_success(peer_id)
            except Exception as trust_exc:
                logger.warning("trust_score: record_success failed peer=%s: %s", peer_id, trust_exc)
    else:
        _fail_on_eval(task_id, eval_result, eval_threshold, peer_id, manager)


def _store_response_artifacts(
    task_id: str, result: dict, peer_id: str | None, manager
) -> tuple[str, dict | None] | None:
    """Store the text and routing-metadata artifacts; return what the gate needs.

    Outbound scrubbing happens here so artifacts returned to remote peers are
    clean, and it returns the SCRUBBED text: handing back the raw response and
    scrubbing only what is stored would leave the caller holding the unscrubbed
    copy that the self-eval then reads.
    """
    # Artifact 1: primary text response — scrub before storing artifact
    # so response artifacts returned to remote callers are clean.
    response_text = _extract_response_text(result)
    try:
        out_scrub = scrub_outbound(response_text, peer_id=task_id, message_id=task_id)
        response_text = out_scrub.text
    except PIIBlocked:
        # Response itself blocked — surface as failed rather than leaking
        logger.warning("A2A task %s: response blocked by PII pipeline", task_id)
        # Issue #7358 phase 2: outbound PII in response is also a threat event
        # (indicates the orchestrator produced sensitive data for an external peer).
        if peer_id:
            try:
                get_trust_manager().record_threat_event(peer_id)
            except Exception as trust_exc:
                logger.warning("trust_score: threat_event record failed peer=%s: %s", peer_id, trust_exc)
        manager.update_state(task_id, TaskState.FAILED, message="Blocked: PII detected in response")
        manager.publish_event(
            task_id,
            {
                "event": "state_change",
                "state": "failed",
                "terminal": True,
                "task_id": task_id,
                "message": "pii_blocked_response",
            },
        )
        return None
    artifact_text = TaskArtifact(artifact_type="text", content=response_text)
    manager.add_artifact(task_id, artifact_text)
    manager.publish_event(
        task_id,
        {"event": "artifact_added", "artifact_type": "text", "task_id": task_id},
    )

    # Artifact 2: routing metadata (agent used, model, timing, etc.)
    metadata = _extract_routing_metadata(result)
    if metadata:
        artifact_meta = TaskArtifact(artifact_type="json", content=metadata)
        manager.add_artifact(task_id, artifact_meta)
        manager.publish_event(
            task_id,
            {"event": "artifact_added", "artifact_type": "json", "task_id": task_id},
        )

    return response_text, metadata


async def _execute_claimed(
    task_id: str,
    input_text: str,
    context: Dict[str, Any] | None,
    eval_threshold: float,
    peer_id: str | None,
    manager,
) -> None:
    """The original execution body, now with cooperative-cancellation checkpoints (#16174).

    A cancelled task's executor cannot be interrupted mid-call -- `cancel_task`
    only flips a state in Redis -- so each checkpoint below only ever stops
    the NEXT step from starting. `hold_scopes`'s `finally` releases the claim
    as soon as this function returns, at whichever checkpoint that is.
    """
    try:
        if await _abort_if_cancelled(task_id, manager, "before scrub"):
            return
        scrubbed = _scrub_inbound(task_id, input_text, peer_id, manager)
        if scrubbed is None:
            return
        input_text = scrubbed

        if await _abort_if_cancelled(task_id, manager, "before orchestration"):
            return

        # Late import to avoid circular deps at module load time
        from agents.agent_orchestration import get_distributed_agent_coordinator

        orchestrator = get_distributed_agent_coordinator()
        result: Dict[str, Any] = await orchestrator.process_request(
            input_text,
            context=context,
        )

        if await _abort_if_cancelled(task_id, manager, "after orchestration"):
            return

        artifacts = _store_response_artifacts(task_id, result, peer_id, manager)
        if artifacts is None:
            return
        response_text, metadata = artifacts

        # Issue #4687: self-evaluation quality gate before COMPLETED transition.
        eval_result = await evaluate_task_output(
            input_text=input_text,
            response_text=response_text,
            metadata=metadata or {},
            threshold=eval_threshold,
        )

        _apply_eval_gate(task_id, eval_result, eval_threshold, peer_id, manager)

    except Exception as exc:
        logger.error("A2A task %s failed: %s", task_id, exc)
        manager.add_artifact(
            task_id,
            TaskArtifact(artifact_type="error", content=type(exc).__name__),
        )
        manager.update_state(task_id, TaskState.FAILED, message=type(exc).__name__)
        manager.publish_event(
            task_id,
            {
                "event": "state_change",
                "state": "failed",
                "terminal": True,
                "message": type(exc).__name__,
                "task_id": task_id,
            },
        )
        # Issue #7358 phase 2: unexpected executor crash → negative trust signal.
        if peer_id:
            try:
                get_trust_manager().record_failure(peer_id)
            except Exception as trust_exc:
                logger.warning("trust_score: record_failure failed peer=%s: %s", peer_id, trust_exc)
