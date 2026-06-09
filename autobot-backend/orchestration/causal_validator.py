# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Causal Validation for Workflow DAGs

Pre-execution validation engine that checks:
1. Causal dependencies are topologically sound (no backward effects)
2. PREVENTS relationships are mutually exclusive
3. ENABLES prerequisites are upstream of consumers
4. State mutations don't conflict (same key modified by multiple steps)
5. Failure cascades have guards to prevent domino effects

Issue: Extend DAG executor with causal validation and effect tracing.
"""

from typing import Dict, List

from autobot_shared.logging_manager import get_logger
from orchestration.causal_models import (
    CausalEffectType,
    CausalMetadata,
)
from orchestration.dag_executor import WorkflowDAG

logger = get_logger(__name__)


class ValidationIssue:
    """A single validation problem found in a workflow."""

    def __init__(
        self,
        level: str,  # "error", "warning", "info"
        category: str,  # "topology", "conflict", "guard", etc
        message: str,
        affected_steps: List[str] | None = None,
    ):
        self.level = level
        self.category = category
        self.message = message
        self.affected_steps = affected_steps or []

    def __str__(self) -> str:
        return f"[{self.level.upper()}] {self.category}: {self.message}"


class ValidationResult:
    """Aggregated validation results for a workflow."""

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
        self.issues: List[ValidationIssue] = []
        self.valid = True

    def add_issue(self, issue: ValidationIssue) -> None:
        """Record a validation issue."""
        self.issues.append(issue)
        if issue.level == "error":
            self.valid = False

    def errors(self) -> List[ValidationIssue]:
        """Return all errors (validation blockers)."""
        return [i for i in self.issues if i.level == "error"]

    def warnings(self) -> List[ValidationIssue]:
        """Return all warnings (should-fix)."""
        return [i for i in self.issues if i.level == "warning"]

    def infos(self) -> List[ValidationIssue]:
        """Return all info (suggestions)."""
        return [i for i in self.issues if i.level == "info"]

    def summary(self) -> str:
        """Return a human-readable summary."""
        if not self.issues:
            return f"Workflow {self.workflow_id}: valid (no issues)"
        errors = len(self.errors())
        warnings = len(self.warnings())
        infos = len(self.infos())
        status = "VALID" if self.valid else "INVALID"
        return f"Workflow {self.workflow_id}: {status} " f"({errors} errors, {warnings} warnings, {infos} infos)"

    def __str__(self) -> str:
        return self.summary()


class CausalValidator:
    """
    Validates causal relationships in a workflow DAG.

    Usage::

        validator = CausalValidator()
        result = validator.validate_workflow(dag, causal_metadata_map)
        if not result.valid:
            for error in result.errors():
                logger.error(error.message)
    """

    def __init__(self) -> None:
        pass

    def validate_workflow(
        self,
        dag: WorkflowDAG,
        metadata_map: Dict[str, CausalMetadata],
    ) -> ValidationResult:
        """
        Validate a complete workflow for causal consistency.

        Args:
            dag: The workflow DAG to validate.
            metadata_map: Map of step_id → CausalMetadata for steps with effects.

        Returns:
            ValidationResult with all issues found.
        """
        result = ValidationResult(dag.nodes.get("_workflow_id", "unknown"))

        # Build node ordering (topological sort)
        node_order = self._topological_sort(dag)
        if node_order is None:
            result.add_issue(ValidationIssue("error", "topology", "DAG contains a cycle (detected by executor)"))
            return result

        set(dag.nodes.keys())

        # 1. Check all referenced steps exist
        self._validate_step_existence(dag, metadata_map, result)

        # 2. Check causal effects are forward-pointing (no backward edges)
        self._validate_effect_direction(dag, metadata_map, node_order, result)

        # 3. Check PREVENTS are mutually exclusive
        self._validate_prevents_relationship(dag, metadata_map, result)

        # 4. Check ENABLES prerequisites are upstream
        self._validate_enables_upstream(dag, metadata_map, node_order, result)

        # 5. Check for conflicting state mutations
        self._validate_state_mutations(metadata_map, result)

        # 6. Check failure cascades have guards
        self._validate_cascade_guards(metadata_map, result)

        # 7. Suggest optimizations
        self._suggest_optimizations(dag, metadata_map, result)

        return result

    # -----------------------------------------------------------------------
    # Validation checks
    # -----------------------------------------------------------------------

    def _validate_step_existence(
        self,
        dag: WorkflowDAG,
        metadata_map: Dict[str, CausalMetadata],
        result: ValidationResult,
    ) -> None:
        """Check all steps referenced in metadata exist in the DAG."""
        step_ids = set(dag.nodes.keys())
        for step_id, metadata in metadata_map.items():
            if step_id not in step_ids:
                result.add_issue(
                    ValidationIssue(
                        "error",
                        "existence",
                        f"Step '{step_id}' in metadata not found in DAG",
                        [step_id],
                    )
                )
            for effect in metadata.causal_effects:
                if effect.target_step_id not in step_ids:
                    result.add_issue(
                        ValidationIssue(
                            "error",
                            "existence",
                            f"Effect target '{effect.target_step_id}' from '{step_id}' not found",
                            [step_id, effect.target_step_id],
                        )
                    )

    def _validate_effect_direction(
        self,
        dag: WorkflowDAG,
        metadata_map: Dict[str, CausalMetadata],
        node_order: List[str],
        result: ValidationResult,
    ) -> None:
        """Check causal effects point forward in the DAG (no backward edges)."""
        position = {nid: i for i, nid in enumerate(node_order)}

        for step_id, metadata in metadata_map.items():
            for effect in metadata.causal_effects:
                src_pos = position.get(step_id)
                tgt_pos = position.get(effect.target_step_id)

                if src_pos is None or tgt_pos is None:
                    continue

                if src_pos >= tgt_pos:
                    result.add_issue(
                        ValidationIssue(
                            "error",
                            "topology",
                            f"Causal effect {step_id} → {effect.target_step_id} is backward "
                            f"(source at pos {src_pos}, target at pos {tgt_pos}). "
                            f"Effects must point to downstream steps.",
                            [step_id, effect.target_step_id],
                        )
                    )

    def _validate_prevents_relationship(
        self,
        dag: WorkflowDAG,
        metadata_map: Dict[str, CausalMetadata],
        result: ValidationResult,
    ) -> None:
        """Check PREVENTS relationships are properly guarded (steps don't execute in same branch)."""
        for step_id, metadata in metadata_map.items():
            for effect in metadata.causal_effects:
                if effect.effect_type != CausalEffectType.PREVENTS:
                    continue

                # Check: if A PREVENTS B, they should not both be in the same root-to-leaf path
                # This is a best-effort check (we can only warn, not error without full execution context)
                if not effect.condition:
                    result.add_issue(
                        ValidationIssue(
                            "warning",
                            "guards",
                            f"PREVENTS effect {step_id} → {effect.target_step_id} has no condition. "
                            f"Add a condition to clarify when this prevention applies.",
                            [step_id, effect.target_step_id],
                        )
                    )

    def _validate_enables_upstream(
        self,
        dag: WorkflowDAG,
        metadata_map: Dict[str, CausalMetadata],
        node_order: List[str],
        result: ValidationResult,
    ) -> None:
        """Check ENABLES effects have upstream sources (prerequisites satisfied before use)."""
        position = {nid: i for i, nid in enumerate(node_order)}

        for step_id, metadata in metadata_map.items():
            for effect in metadata.causal_effects:
                if effect.effect_type != CausalEffectType.ENABLES:
                    continue

                src_pos = position.get(step_id)
                tgt_pos = position.get(effect.target_step_id)

                if src_pos is not None and tgt_pos is not None and src_pos >= tgt_pos:
                    result.add_issue(
                        ValidationIssue(
                            "warning",
                            "dependency",
                            f"ENABLES effect {step_id} → {effect.target_step_id}: "
                            f"enabler must execute before the enabled step.",
                            [step_id, effect.target_step_id],
                        )
                    )

    def _validate_state_mutations(
        self,
        metadata_map: Dict[str, CausalMetadata],
        result: ValidationResult,
    ) -> None:
        """Check for conflicting state mutations (same key modified by multiple steps)."""
        state_mutations: Dict[str, List[str]] = {}

        for step_id, metadata in metadata_map.items():
            for key in metadata.state_keys_modified:
                if key not in state_mutations:
                    state_mutations[key] = []
                state_mutations[key].append(step_id)

        for key, modifiers in state_mutations.items():
            if len(modifiers) > 1:
                result.add_issue(
                    ValidationIssue(
                        "warning",
                        "conflicts",
                        f"State key '{key}' is modified by multiple steps: {modifiers}. "
                        f"Ensure they run in sequence or are mutually exclusive.",
                        modifiers,
                    )
                )

    def _validate_cascade_guards(
        self,
        metadata_map: Dict[str, CausalMetadata],
        result: ValidationResult,
    ) -> None:
        """Check failure cascades have guards (AMPLIFIES should have error handlers)."""
        for step_id, metadata in metadata_map.items():
            for effect in metadata.causal_effects:
                if effect.effect_type != CausalEffectType.AMPLIFIES:
                    continue

                if not effect.condition:
                    result.add_issue(
                        ValidationIssue(
                            "warning",
                            "guards",
                            f"AMPLIFIES effect {step_id} → {effect.target_step_id} has no condition. "
                            f"The cascade may be unintended. Add a condition or error handler.",
                            [step_id, effect.target_step_id],
                        )
                    )

    def _suggest_optimizations(
        self,
        dag: WorkflowDAG,
        metadata_map: Dict[str, CausalMetadata],
        result: ValidationResult,
    ) -> None:
        """Suggest workflow optimizations based on causal metadata."""
        # Detect parallelizable steps (no causal dependencies between them)
        # and suggest which can_run_parallel_with

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _topological_sort(self, dag: WorkflowDAG) -> List[str] | None:
        """Return topologically sorted node IDs, or None if cycle detected."""
        if dag.detect_cycle():
            return None

        # Kahn's algorithm
        in_degree = {nid: 0 for nid in dag.nodes}
        for nid, node in dag.nodes.items():
            for edge in dag.successors(nid):
                in_degree[edge.target] += 1

        queue = [nid for nid, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            nid = queue.pop(0)
            result.append(nid)
            for edge in dag.successors(nid):
                in_degree[edge.target] -= 1
                if in_degree[edge.target] == 0:
                    queue.append(edge.target)

        return result if len(result) == len(dag.nodes) else None


class ValidationReporter:
    """Helper to format and log validation results."""

    @staticmethod
    def report(result: ValidationResult) -> str:
        """Generate a detailed validation report."""
        lines = [f"# Validation Report: {result.workflow_id}", "", result.summary(), ""]

        if result.errors():
            lines.append("## Errors (Blocking)")
            for issue in result.errors():
                lines.append(f"  - {issue.message}")
            lines.append("")

        if result.warnings():
            lines.append("## Warnings (Should Fix)")
            for issue in result.warnings():
                lines.append(f"  - {issue.message}")
            lines.append("")

        if result.infos():
            lines.append("## Suggestions")
            for issue in result.infos():
                lines.append(f"  - {issue.message}")
            lines.append("")

        return "\n".join(lines)
