# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Causal Executor — DAG Executor with Effect Tracing

Wraps the DAGExecutor to track state mutations and trace causal effects.
Records which step modified what state, enabling analysis of failures and
understanding of interdependencies.

Issue: Extend DAG executor with causal validation and effect tracing.

Usage::

    executor = DAGExecutor(step_executor_callback)
    causal_executor = CausalExecutor(executor)
    ctx = await causal_executor.execute(dag, workflow_id, metadata_map)

    # Access the effect trace
    print(causal_executor.effect_trace)
    cascade_report = causal_executor.analyze_cascades()
"""

import time
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger
from orchestration.causal_models import (
    CascadeReport,
    CausalMetadata,
    EffectTrace,
    StateFrame,
)
from orchestration.causal_validator import CausalValidator, ValidationResult
from orchestration.dag_executor import (
    DAGExecutionContext,
    DAGExecutor,
    WorkflowDAG,
)

logger = get_logger(__name__)


class CausalExecutor:
    """
    Wraps a DAGExecutor with causal effect tracing and cascade analysis.

    Tracks state mutations through execution and enables post-hoc analysis
    of which steps affected which downstream steps.

    Attributes:
        executor: The underlying DAGExecutor.
        metadata_map: Map of step_id → CausalMetadata (optional).
        effect_trace: EffectTrace recording all mutations (built during execution).
        validation_result: Result of pre-execution causal validation (if enabled).
    """

    def __init__(
        self,
        executor: DAGExecutor,
        metadata_map: Dict[str, CausalMetadata] | None = None,
    ):
        """
        Initialize the causal executor.

        Args:
            executor: DAGExecutor to wrap.
            metadata_map: Optional causal metadata for steps.
        """
        self.executor = executor
        self.metadata_map = metadata_map or {}
        self.effect_trace: EffectTrace | None = None
        self.validation_result: ValidationResult | None = None

    async def execute(
        self,
        dag: WorkflowDAG,
        workflow_id: str,
        context: Dict[str, Any] | None = None,
        validate_causal: bool = True,
    ) -> DAGExecutionContext:
        """
        Execute a workflow DAG with causal tracing.

        Args:
            dag: Workflow DAG to execute.
            workflow_id: Identifier for this execution.
            context: Extra context forwarded to step executor.
            validate_causal: If True, validate causal relationships before execution.

        Returns:
            DAGExecutionContext after all steps complete.
        """
        # Initialize effect trace
        self.effect_trace = EffectTrace(workflow_id=workflow_id)

        # Pre-execution validation
        # #7010 cluster 4: validation runs whenever validate_causal=True,
        # regardless of whether metadata_map is populated. An empty
        # metadata_map yields a trivially-valid result (no causal
        # relationships declared = nothing to invalidate); the test
        # `test_validation_before_execution` documents this contract.
        if validate_causal:
            validator = CausalValidator()
            self.validation_result = validator.validate_workflow(dag, self.metadata_map)
            logger.info("Causal validation: %s", self.validation_result.summary())

            if not self.validation_result.valid:
                errors = self.validation_result.errors()
                logger.error("Causal validation failed with %d error(s)", len(errors))
                for error in errors:
                    logger.error("  - %s", error.message)

        # Wrap executor to capture state snapshots
        original_step_executor = self.executor._execute_step
        self.executor._execute_step = self._make_tracing_executor(original_step_executor, context or {})

        try:
            # Run the actual DAG execution
            execution_ctx = await self.executor.execute(dag, workflow_id, context)
        finally:
            # Restore original executor
            self.executor._execute_step = original_step_executor

        # Post-execution analysis
        self._analyze_mutations(execution_ctx)

        return execution_ctx

    # -----------------------------------------------------------------------
    # Effect tracing
    # -----------------------------------------------------------------------

    def _make_tracing_executor(self, original_executor: Any, context: Dict[str, Any]) -> Any:
        """Create a step executor that wraps the original with state tracking."""

        async def tracing_executor(node: Any, ctx: DAGExecutionContext) -> Dict[str, Any]:
            """Execute a step and record state mutations."""
            step_id = node.node_id
            t0 = time.time()

            # Capture state before execution
            state_before = dict(ctx.step_results)

            # Execute the actual step
            result = await original_executor(node, ctx)

            # Record output
            self.effect_trace.record_output(step_id, result or {})

            # Capture state after execution
            state_after = dict(ctx.step_results)

            # Detect mutations
            mutations = self._detect_mutations(state_before, state_after)

            # Record the state frame
            frame = StateFrame(
                step_id=step_id,
                timestamp=t0,
                state_snapshot=state_after,
                mutations=mutations,
            )
            self.effect_trace.add_frame(frame)

            logger.debug(
                "Step %s: traced %d state mutations: %s",
                step_id,
                len(mutations),
                list(mutations.keys()),
            )

            return result

        return tracing_executor

    def _detect_mutations(
        self,
        state_before: Dict[str, Any],
        state_after: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Detect which state keys were added or modified."""
        mutations = {}
        for key, value in state_after.items():
            if key not in state_before or state_before[key] != value:
                mutations[key] = value
        return mutations

    def _analyze_mutations(self, execution_ctx: DAGExecutionContext) -> None:
        """Analyze mutation patterns to infer dependencies."""
        if not self.effect_trace:
            return

        logger.info(
            "Effect trace: %d steps executed, %d state keys mutated",
            len(self.effect_trace.execution_frames),
            len(self.effect_trace.mutation_map),
        )

        # Log mutation chains
        for key, mutations in self.effect_trace.mutation_map.items():
            if len(mutations) > 1:
                chain = " → ".join(step_id for step_id, _ in mutations)
                logger.debug("State key '%s' mutated by: %s", key, chain)

    # -----------------------------------------------------------------------
    # Cascade analysis
    # -----------------------------------------------------------------------

    def analyze_cascades(self, execution_ctx: DAGExecutionContext, failed_step_id: str | None = None) -> CascadeReport:
        """
        Analyze cascading failures after execution.

        Args:
            execution_ctx: Execution context after steps have run.
            failed_step_id: If provided, analyze cascades from this step's failure.
                           If None, use the first failed step found in results.

        Returns:
            CascadeReport showing affected steps and propagation chain.
        """
        if not self.effect_trace:
            return CascadeReport(
                failed_step_id=failed_step_id or "unknown",
                failure_reason="No effect trace available",
            )

        # Find the failed step if not provided
        if not failed_step_id:
            for step_id, result in execution_ctx.step_results.items():
                if isinstance(result, dict) and not result.get("success", True):
                    failed_step_id = step_id
                    break

        if not failed_step_id:
            return CascadeReport(
                failed_step_id="unknown",
                failure_reason="No failed step found",
            )

        failure_reason = ""
        if isinstance(execution_ctx.step_results.get(failed_step_id), dict):
            failure_reason = execution_ctx.step_results[failed_step_id].get("error", "Unknown error")

        report = CascadeReport(
            failed_step_id=failed_step_id,
            failure_reason=failure_reason,
        )

        # Trace which steps depend on the failed step's outputs
        self.effect_trace.get_mutations_by_step(failed_step_id)

        for step_id, result in execution_ctx.step_results.items():
            if step_id == failed_step_id or not isinstance(result, dict):
                continue

            # Check if this step depends on the failed step's mutations
            is_affected = False
            reason = ""

            # Look for metadata declaring the dependency
            if self.metadata_map.get(failed_step_id):
                metadata = self.metadata_map[failed_step_id]
                for effect in metadata.causal_effects:
                    if effect.target_step_id == step_id:
                        is_affected = True
                        reason = f"Causal effect: {effect.effect_type.value}"
                        break

            # If step failed, consider it affected
            if is_affected:
                is_direct = step_id in self._get_direct_successors(failed_step_id, execution_ctx)
                report.add_affected(step_id, reason, direct=is_direct)

        # Suggest mitigation
        report.suggested_mitigation = self._suggest_mitigations(report, execution_ctx)

        logger.info("Cascade analysis: %s", report)
        return report

    def _get_direct_successors(self, step_id: str, execution_ctx: DAGExecutionContext) -> list[str]:
        """Get steps that directly depend on the given step."""
        successors = []
        for metadata in self.metadata_map.values():
            for effect in metadata.causal_effects:
                if effect.source_step_id == step_id:
                    successors.append(effect.target_step_id)
        return successors

    def _suggest_mitigations(self, report: CascadeReport, execution_ctx: DAGExecutionContext) -> list[str]:
        """Suggest workflow restructuring to prevent cascades."""
        suggestions = []

        if len(report.directly_affected) > 2:
            suggestions.append(
                f"Step '{report.failed_step_id}' affects {len(report.directly_affected)} "
                f"downstream steps. Consider breaking into smaller subtasks or adding "
                f"error handlers (SKIP/FALLBACK) to reduce cascade."
            )

        if len(report.indirectly_affected) > 0:
            suggestions.append(
                "Use ENABLES/PREVENTS causal relationships to clarify which steps can "
                "tolerate failures vs. which must be protected."
            )

        # Check for conflicting dependencies
        affected_steps = set(report.directly_affected + report.indirectly_affected)
        if len(affected_steps) > 0:
            suggestions.append(
                "Add error_config with SKIP or FALLBACK action to affected steps to prevent cascading failures."
            )

        if not suggestions:
            suggestions.append("Workflow structure allows failure isolation. No major restructuring recommended.")

        return suggestions

    # -----------------------------------------------------------------------
    # Reporting
    # -----------------------------------------------------------------------

    def trace_effect_chain(self, state_key: str) -> str:
        """Generate a human-readable trace of how a state key was set."""
        # #7010 cluster 4: callers (incl. UI) match on the substring
        # "not available" / "not modified" to detect the no-data case;
        # phrase both arms with those tokens explicitly.
        if not self.effect_trace:
            return f"Effect trace not available for key '{state_key}' (no execution data)"

        chain = self.effect_trace.trace_effect(state_key)
        if not chain:
            return f"State key '{state_key}' was not modified"

        parts = [f"State key '{state_key}' mutation chain:"]
        for i, (step_id, timestamp) in enumerate(chain, 1):
            parts.append(f"  {i}. Step '{step_id}' at t={timestamp:.3f}s")

        return "\n".join(parts)

    def summary(self) -> str:
        """Generate execution summary with causal insights."""
        if not self.effect_trace:
            return "No execution data available"

        # #7010 cluster 4: UI/test consumers grep these labels case-sensitively
        # for tokens "steps executed" and "mutated" — keep the lowercase
        # form so substring searches succeed.
        lines = [
            f"Workflow: {self.effect_trace.workflow_id}",
            f"steps executed: {len(self.effect_trace.execution_frames)}",
            f"state keys mutated: {len(self.effect_trace.mutation_map)}",
            f"total mutations: {sum(len(m) for m in self.effect_trace.mutation_map.values())}",
        ]

        if self.validation_result:
            lines.append(f"Validation: {self.validation_result.summary()}")

        return "\n".join(lines)
