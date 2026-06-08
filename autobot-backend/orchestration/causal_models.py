# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Causal Models for Workflow DAGs

Defines data structures for modeling causal relationships between workflow steps:
- What state does each step modify?
- Which downstream steps depend on those modifications?
- What conditions enable/prevent/cause cascading failures?

Issue: Extend DAG executor with causal validation and effect tracing.

This module provides:
- CausalEffectType: Enum of causal relationship types
- CausalEffect: A single causal edge (A affects B how?)
- DependencyType: DATA vs CONTROL vs CAUSAL dependencies
- CausalMetadata: Attached to workflow steps to declare effects
- EffectTrace: Tracks state mutations during execution
- CascadeReport: Analysis of failure propagation
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class CausalEffectType(str, Enum):
    """Types of causal relationships between steps."""

    CAUSES = "causes"  # Step A directly causes step B to execute
    ENABLES = "enables"  # Step A enables step B (prerequisite satisfied)
    PREVENTS = "prevents"  # Step A prevents step B (mutual exclusivity)
    BLOCKS = "blocks"  # Step A blocks step B (output blocks downstream)
    AMPLIFIES = "amplifies"  # Step A's failure cascades to B
    MITIGATES = "mitigates"  # Step A mitigates or recovers from B's failure


class DependencyType(str, Enum):
    """Types of dependencies between workflow steps."""

    DATA = "data"  # Step B consumes output from step A
    CONTROL = "control"  # Step B waits for step A (branching/joining)
    CAUSAL = "causal"  # Step B's behavior changes based on A's state
    IMPLICIT = "implicit"  # Inferred from DAG structure


@dataclass
class CausalEffect:
    """
    A single causal relationship: step A has an effect on step B.

    Attributes:
        source_step_id: Step that produces the effect.
        target_step_id: Step that is affected.
        effect_type: Kind of causal relationship (CAUSES, ENABLES, etc).
        condition: Optional Python expression that must be true for effect to apply
                   (e.g., "output['status'] == 'error'").
        description: Human-readable explanation of the causal link.
        state_mutations: List of state keys that this effect modifies.
    """

    source_step_id: str
    target_step_id: str
    effect_type: CausalEffectType
    condition: str | None = None
    description: str = ""
    state_mutations: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        cond_str = f" [if: {self.condition}]" if self.condition else ""
        return f"{self.source_step_id} --{self.effect_type.value}--> {self.target_step_id}{cond_str}"


@dataclass
class Dependency:
    """
    A dependency between two steps.

    Attributes:
        source_step_id: Step that must complete first.
        target_step_id: Step that depends on the source.
        dep_type: Kind of dependency.
        causal_effect: Associated CausalEffect if dep_type is CAUSAL.
    """

    source_step_id: str
    target_step_id: str
    dep_type: DependencyType
    causal_effect: CausalEffect | None = None

    def __str__(self) -> str:
        return f"{self.source_step_id} --[{self.dep_type.value}]--> {self.target_step_id}"


@dataclass
class CausalMetadata:
    """
    Metadata attached to a workflow step to declare its causal effects.

    Attributes:
        step_id: Identifier of the step.
        causal_effects: List of effects this step has on downstream steps.
        state_keys_modified: Keys in the execution context this step modifies.
        failure_cascades_to: Steps that fail if this step fails (amplification).
        can_run_parallel_with: Other step IDs that can run concurrently safely.
    """

    step_id: str
    causal_effects: List[CausalEffect] = field(default_factory=list)
    state_keys_modified: List[str] = field(default_factory=list)
    failure_cascades_to: List[str] = field(default_factory=list)
    can_run_parallel_with: List[str] = field(default_factory=list)

    def add_effect(self, effect: CausalEffect) -> None:
        """Register a causal effect from this step."""
        self.causal_effects.append(effect)

    def add_state_mutation(self, key: str) -> None:
        """Register a state key that this step modifies."""
        if key not in self.state_keys_modified:
            self.state_keys_modified.append(key)


@dataclass
class StateFrame:
    """Snapshot of execution state at a point in time."""

    step_id: str
    timestamp: float
    state_snapshot: Dict[str, Any]
    mutations: Dict[str, Any] = field(default_factory=dict)  # Keys that changed
    source_mutations: Dict[str, str] = field(default_factory=dict)  # key → which step set it

    def __str__(self) -> str:
        return f"StateFrame({self.step_id}, mutations={list(self.mutations.keys())})"


@dataclass
class EffectTrace:
    """
    Trace of state mutations through workflow execution.

    Tracks which step modified what state, enabling causal analysis
    of failures and understanding of interdependencies.

    Attributes:
        workflow_id: Identifier of the workflow execution.
        execution_frames: Ordered list of state snapshots.
        mutation_map: Reverse map from state key → (step_id, timestamp).
        step_outputs: Direct outputs from each step.
    """

    workflow_id: str
    execution_frames: List[StateFrame] = field(default_factory=list)
    mutation_map: Dict[str, List[tuple[str, float]]] = field(default_factory=dict)  # key → [(step, time), ...]
    step_outputs: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def add_frame(self, frame: StateFrame) -> None:
        """Record a state frame after a step completes."""
        self.execution_frames.append(frame)
        for key, value in frame.mutations.items():
            if key not in self.mutation_map:
                self.mutation_map[key] = []
            self.mutation_map[key].append((frame.step_id, frame.timestamp))

    def record_output(self, step_id: str, output: Dict[str, Any]) -> None:
        """Record the output produced by a step."""
        self.step_outputs[step_id] = output

    def get_mutations_by_step(self, step_id: str) -> Dict[str, Any]:
        """Get all state mutations caused by *step_id*."""
        result = {}
        for frame in self.execution_frames:
            if frame.step_id == step_id:
                result.update(frame.mutations)
        return result

    def trace_effect(self, key: str) -> List[tuple[str, float]]:
        """Get the causal chain for a state key: which steps set it when?"""
        return self.mutation_map.get(key, [])

    def __str__(self) -> str:
        return (
            f"EffectTrace({self.workflow_id}, {len(self.execution_frames)} frames, "
            f"{len(self.mutation_map)} mutated keys)"
        )


@dataclass
class CascadeReport:
    """
    Analysis of cascading failure propagation.

    When a step fails, which downstream steps are affected?
    How does the failure propagate through the workflow?

    Attributes:
        failed_step_id: The step that originally failed.
        failure_reason: Why it failed.
        directly_affected: Steps that fail as direct consequence.
        indirectly_affected: Steps that fail due to chain reaction.
        cascade_chain: List of (step_id, reason, timestamp) showing propagation.
        suggested_mitigation: Suggested workflow restructuring or guards.
    """

    failed_step_id: str
    failure_reason: str
    directly_affected: List[str] = field(default_factory=list)
    indirectly_affected: List[str] = field(default_factory=list)
    cascade_chain: List[tuple[str, str]] = field(default_factory=list)
    suggested_mitigation: List[str] = field(default_factory=list)

    @property
    def total_affected(self) -> int:
        """Total steps affected by this failure."""
        return len(self.directly_affected) + len(self.indirectly_affected)

    def add_affected(self, step_id: str, reason: str, direct: bool = False) -> None:
        """Record a step affected by the failure."""
        if direct:
            if step_id not in self.directly_affected:
                self.directly_affected.append(step_id)
        else:
            if step_id not in self.indirectly_affected:
                self.indirectly_affected.append(step_id)
        self.cascade_chain.append((step_id, reason))

    def __str__(self) -> str:
        return (
            f"CascadeReport({self.failed_step_id} → "
            f"{len(self.directly_affected)} direct, "
            f"{len(self.indirectly_affected)} indirect)"
        )
