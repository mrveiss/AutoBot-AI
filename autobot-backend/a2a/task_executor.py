# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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

from autobot_shared.logging_manager import get_logger

from .pii_pipeline import PIIBlocked, scrub_outbound
from .self_evaluator import DEFAULT_EVAL_THRESHOLD, evaluate_task_output
from .task_manager import get_task_manager
from .trust_score import get_trust_manager
from .types import TaskArtifact, TaskState

logger = get_logger(__name__)


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

    try:
        # Issue #7355: Scrub inbound payload before forwarding to orchestrator.
        # Prevents PII/credentials that arrived in the A2A request from leaking
        # into downstream RAG retrieval, agent prompts, or external API calls.
        try:
            scrub_result = scrub_outbound(input_text, peer_id=task_id, message_id=task_id)
            input_text = scrub_result.text
            if scrub_result.redaction_count > 0:
                logger.info(
                    "A2A task %s: scrubbed %d PII item(s) from inbound payload",
                    task_id,
                    scrub_result.redaction_count,
                )
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
            return

        # Late import to avoid circular deps at module load time
        from agents.agent_orchestration import get_distributed_agent_coordinator

        orchestrator = get_distributed_agent_coordinator()
        result: Dict[str, Any] = await orchestrator.process_request(
            input_text,
            context=context,
        )

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
            return
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

        # Issue #4687: self-evaluation quality gate before COMPLETED transition.
        eval_result = await evaluate_task_output(
            input_text=input_text,
            response_text=response_text,
            metadata=metadata or {},
            threshold=eval_threshold,
        )

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
