# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoResearch Data Models

Issue #2597: Core data structures for experiment tracking.
"""

from __future__ import annotations

import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List

# Forward reference — PromptVariant is defined in prompt_optimizer to avoid
# circular imports; callers import VariantArchiveEntry directly from models.
# The type annotation below uses a string literal for the forward ref.


@dataclass
class VariantArchiveEntry:
    """A single entry in the quality-diversity archive.

    Issue #3222: Replaces the greedy top-K filter so that every evaluated
    variant is retained and eligible for weighted-random parent selection.
    """

    variant_id: str
    variant: Any  # PromptVariant — typed as Any to avoid circular import
    score: float
    parent_id: str | None
    generation: int
    valid_parent: bool = True
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "variant_id": self.variant_id,
            "variant": self.variant.to_dict(),
            "score": self.score,
            "parent_id": self.parent_id,
            "generation": self.generation,
            "valid_parent": self.valid_parent,
            "created_at": self.created_at,
        }


class ExperimentState(str, enum.Enum):
    """Lifecycle states for an experiment run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DISCARDED = "discarded"
    KEPT = "kept"


@dataclass
class ExperimentTask:
    """Per-task prompt overrides for experiment runner.

    Issue #3259: Allow temperature and system_prompt overrides at the task level.
    """

    prompt: str
    required_temperature: float | None = None
    system_prompt: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt": self.prompt,
            "required_temperature": self.required_temperature,
            "system_prompt": self.system_prompt,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExperimentTask":
        return cls(
            prompt=data["prompt"],
            required_temperature=data.get("required_temperature"),
            system_prompt=data.get("system_prompt"),
        )


@dataclass
class HyperParams:
    """Training hyperparameters for a single experiment."""

    learning_rate: float = 3e-4
    batch_size: int = 64
    max_steps: int = 5000
    warmup_steps: int = 100
    weight_decay: float = 0.1
    block_size: int = 256
    n_layer: int = 6
    n_head: int = 6
    n_embd: int = 384
    dropout: float = 0.2
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "learning_rate": self.learning_rate,
            "batch_size": self.batch_size,
            "max_steps": self.max_steps,
            "warmup_steps": self.warmup_steps,
            "weight_decay": self.weight_decay,
            "block_size": self.block_size,
            "n_layer": self.n_layer,
            "n_head": self.n_head,
            "n_embd": self.n_embd,
            "dropout": self.dropout,
        }
        result.update(self.extra)
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> HyperParams:
        known_fields = {
            "learning_rate",
            "batch_size",
            "max_steps",
            "warmup_steps",
            "weight_decay",
            "block_size",
            "n_layer",
            "n_head",
            "n_embd",
            "dropout",
        }
        known = {k: v for k, v in data.items() if k in known_fields}
        extra = {k: v for k, v in data.items() if k not in known_fields}
        return cls(**known, extra=extra)


@dataclass
class ExperimentResult:
    """Parsed metrics from a completed training run."""

    val_bpb: float | None = None
    train_loss: float | None = None
    val_loss: float | None = None
    steps_completed: int = 0
    tokens_per_second: float | None = None
    wall_time_seconds: float = 0.0
    raw_output: str = ""
    error_message: str | None = None

    @property
    def success(self) -> bool:
        return self.val_bpb is not None and self.error_message is None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "val_bpb": self.val_bpb,
            "train_loss": self.train_loss,
            "val_loss": self.val_loss,
            "steps_completed": self.steps_completed,
            "tokens_per_second": self.tokens_per_second,
            "wall_time_seconds": self.wall_time_seconds,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ExperimentResult:
        return cls(
            val_bpb=data.get("val_bpb"),
            train_loss=data.get("train_loss"),
            val_loss=data.get("val_loss"),
            steps_completed=data.get("steps_completed", 0),
            tokens_per_second=data.get("tokens_per_second"),
            wall_time_seconds=data.get("wall_time_seconds", 0.0),
            error_message=data.get("error_message"),
        )


@dataclass
class Experiment:
    """A single autoresearch experiment run."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    hypothesis: str = ""
    description: str = ""
    code_diff: str = ""
    hyperparams: HyperParams = field(default_factory=HyperParams)
    result: ExperimentResult | None = None
    state: ExperimentState = ExperimentState.PENDING
    baseline_val_bpb: float | None = None
    parent_experiment_id: str | None = None
    tags: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None

    @property
    def improvement(self) -> float | None:
        """Return bpb improvement over baseline (positive = better)."""
        if self.result and self.result.val_bpb is not None and self.baseline_val_bpb is not None:
            return self.baseline_val_bpb - self.result.val_bpb
        return None

    @property
    def improvement_pct(self) -> float | None:
        """Return percentage improvement over baseline."""
        if self.improvement is not None and self.baseline_val_bpb:
            return (self.improvement / self.baseline_val_bpb) * 100
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "hypothesis": self.hypothesis,
            "description": self.description,
            "code_diff": self.code_diff,
            "hyperparams": self.hyperparams.to_dict(),
            "result": self.result.to_dict() if self.result else None,
            "state": self.state.value,
            "baseline_val_bpb": self.baseline_val_bpb,
            "parent_experiment_id": self.parent_experiment_id,
            "tags": self.tags,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Experiment:
        hp = data.get("hyperparams", {})
        result_data = data.get("result")
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            hypothesis=data.get("hypothesis", ""),
            description=data.get("description", ""),
            code_diff=data.get("code_diff", ""),
            hyperparams=HyperParams.from_dict(hp) if hp else HyperParams(),
            result=(ExperimentResult.from_dict(result_data) if result_data else None),
            state=ExperimentState(data.get("state", "pending")),
            baseline_val_bpb=data.get("baseline_val_bpb"),
            parent_experiment_id=data.get("parent_experiment_id"),
            tags=data.get("tags", []),
            created_at=data.get("created_at", time.time()),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
        )


@dataclass
class ScorerResult:
    """Result from a single prompt evaluation.

    Issue #3261: Typed error field replaces magic strings so that
    filter_prompts() can distinguish error sentinels from genuine scores.
    """

    score: float | None
    error: str | None = None

    @property
    def is_error(self) -> bool:
        """Return True when this result represents a failure."""
        return self.error is not None

    def to_dict(self) -> Dict[str, Any]:
        return {"score": self.score, "error": self.error}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScorerResult":
        return cls(score=data.get("score"), error=data.get("error"))


@dataclass
class ExperimentStats:
    """Aggregate statistics across experiment runs."""

    total_experiments: int = 0
    completed: int = 0
    failed: int = 0
    kept: int = 0
    discarded: int = 0
    best_val_bpb: float | None = None
    baseline_val_bpb: float | None = None
    avg_wall_time: float = 0.0
    total_wall_time: float = 0.0
    improvement_trend: List[float] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_experiments": self.total_experiments,
            "completed": self.completed,
            "failed": self.failed,
            "kept": self.kept,
            "discarded": self.discarded,
            "best_val_bpb": self.best_val_bpb,
            "baseline_val_bpb": self.baseline_val_bpb,
            "avg_wall_time": self.avg_wall_time,
            "total_wall_time": self.total_wall_time,
            "improvement_trend": self.improvement_trend,
        }
