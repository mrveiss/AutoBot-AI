# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Loop Types

Type definitions for the agent loop system including states, phases,
iteration results, and configuration.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any

from autobot_shared.time_utils import now_utc
from constants.threshold_constants import BatchConfig, RetryConfig

# =============================================================================
# Loop States and Phases
# =============================================================================


class LoopPhase(Enum):
    """
    The 6 phases of the agent loop (Manus pattern).

    Each iteration cycles through these phases in order.
    """

    ANALYZE_EVENTS = auto()  # 1. Understand state from event stream
    SELECT_TOOLS = auto()  # 2. Choose tools based on plan + knowledge
    WAIT_FOR_EXECUTION = auto()  # 3. Sandbox executes tool
    ITERATE = auto()  # 4. Check if more iterations needed
    SUBMIT_RESULTS = auto()  # 5. Deliver results via message tools
    STANDBY = auto()  # 6. Idle state, await new tasks


class LoopState(Enum):
    """Overall state of the agent loop."""

    IDLE = auto()  # Not running, awaiting task
    INITIALIZING = auto()  # Setting up for new task
    RUNNING = auto()  # Actively executing iterations
    PAUSED = auto()  # Temporarily paused (user intervention)
    COMPLETING = auto()  # Wrapping up task
    COMPLETED = auto()  # Task finished successfully
    FAILED = auto()  # Task failed
    CANCELLED = auto()  # Task was cancelled


class LoopOutcome(Enum):
    """Terminal outcome of a loop run.

    ABSTAINED is distinct from FAILED: the agent recognised it could not
    produce a reliable answer and chose governed silence over hallucination.
    It is re-runnable with different inputs; FAILED typically is not.
    """

    COMPLETED = "completed"
    ABSTAINED = "abstained"
    CANCELLED = "cancelled"
    HALTED = "halted"
    FAILED = "failed"


class ThinkCategory(Enum):
    """
    Categories for Think Tool reasoning (Devin pattern).

    Mandatory thinking is required for certain decision points.
    """

    # Mandatory categories
    GIT_DECISION = auto()  # Before git/GitHub operations
    TRANSITION = auto()  # From exploring to making changes
    COMPLETION = auto()  # Before reporting completion to user

    # Optional categories
    PROBLEM_ANALYSIS = auto()  # Analyzing a complex problem
    APPROACH_SELECTION = auto()  # Choosing between approaches
    ERROR_RECOVERY = auto()  # Deciding how to recover from errors
    ASSUMPTION_CHECK = auto()  # Validating assumptions
    SELF_REFLECTION = auto()  # RLM: evaluating own response quality (#1373)
    GENERAL = auto()  # General reasoning
    CAUSAL_ANALYSIS = auto()  # Causal chain reasoning — WHY not just WHAT


# =============================================================================
# Think Tool Types
# =============================================================================


@dataclass
class ThinkResult:
    """Result of a Think Tool invocation."""

    category: ThinkCategory
    reasoning: str
    conclusion: str
    confidence: float  # 0.0 to 1.0
    alternatives_considered: list[str] = field(default_factory=list)
    risks_identified: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=now_utc)
    task_id: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for event content."""
        return {
            "category": self.category.name,
            "reasoning": self.reasoning,
            "conclusion": self.conclusion,
            "confidence": self.confidence,
            "alternatives_considered": self.alternatives_considered,
            "risks_identified": self.risks_identified,
            "timestamp": self.timestamp.isoformat(),
            "task_id": self.task_id,
        }


# =============================================================================
# Iteration Types
# =============================================================================


@dataclass
class IterationResult:
    """Result of a single agent loop iteration."""

    iteration_number: int
    # overwritten by _execute_iteration_phases
    phase_completed: LoopPhase = LoopPhase.ANALYZE_EVENTS
    tools_executed: list[str] = field(default_factory=list)
    tool_results: dict[str, Any] = field(default_factory=dict)
    events_analyzed: int = 0
    plan_progress: float | None = None  # 0.0 to 1.0
    think_results: list[ThinkResult] = field(default_factory=list)
    should_continue: bool = True
    error: str | None = None
    timestamp: datetime = field(default_factory=now_utc)

    def to_dict(self) -> dict:
        """Convert to dictionary for logging/events."""
        return {
            "iteration_number": self.iteration_number,
            "phase_completed": self.phase_completed.name,
            "tools_executed": self.tools_executed,
            "events_analyzed": self.events_analyzed,
            "plan_progress": self.plan_progress,
            "should_continue": self.should_continue,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
        }


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class AgentLoopConfig:
    """Configuration for the agent loop.

    Issue #670: Uses centralized constants from threshold_constants.py
    """

    # Iteration limits
    max_iterations: int = BatchConfig.MAX_CONCURRENCY  # 100 - Maximum iterations per task
    max_consecutive_errors: int = RetryConfig.DEFAULT_RETRIES  # 3 - Stop after N consecutive errors

    # Timeouts (milliseconds) - kept as specific values for tool execution timing
    iteration_timeout_ms: int = 60000  # Max time per iteration
    tool_timeout_ms: int = 30000  # Max time per tool execution
    total_task_timeout_ms: int = 600000  # Max time for entire task (10 min)

    # Think tool settings
    mandatory_think_enabled: bool = True  # Require thinking at decision points
    think_on_git: bool = True  # Think before git operations
    think_on_transition: bool = True  # Think when transitioning modes
    think_on_completion: bool = True  # Think before reporting complete

    # Event stream settings
    events_to_analyze: int = BatchConfig.MEDIUM_BATCH  # 50 - Recent events to consider
    include_system_events: bool = False  # Include SYSTEM events in analysis

    # Parallel execution
    enable_parallel_tools: bool = True  # Use parallel tool executor
    max_parallel_tools: int = BatchConfig.DEFAULT_CONCURRENCY  # 10 - Max concurrent tool calls

    # Recovery settings
    retry_failed_tools: bool = True  # Retry failed tool calls
    max_tool_retries: int = RetryConfig.MIN_RETRIES  # 2 - Max retries per tool

    # Per-severity retry budgets (GH#6628)
    max_retries_critical: int = 0  # CRITICAL: immediate halt, no retry
    max_retries_high: int = 1  # HIGH severity: 1 retry
    max_retries_medium: int = 3  # MEDIUM severity: 3 retries (legacy default)
    max_retries_low: int = 5  # LOW/RETRY-class: 5 retries (transient errors)

    # Repetitive tool-call detection (#3255)
    max_identical_tool_calls: int = 3  # Halt when same tool+args seen N times

    # Semantic stagnation detection (#6627)
    stagnation_window: int = 5  # Rolling window of observations to evaluate
    min_observation_novelty: float = 0.05  # Min avg novel-token ratio to avoid halt
    halt_on_stagnation: bool = True  # Enable stagnation-based halt

    # Schema self-correction (Issue #4482)
    max_schema_retries: int = 3  # Max retries when tool argument schema validation fails

    # Approval workflow (Issue #4092)
    require_approval_for_sensitive: bool = True  # Gate sensitive ops behind user approval
    approval_timeout_seconds: int = 300  # Max seconds to wait for user response

    # First-turn priming (Issue #4481)
    first_turn_priming_enabled: bool = True  # Inject context note on first iteration

    # Confidence-based abstention (GH#6626)
    abstain_on_low_confidence: bool = True  # Halt with ABSTAINED outcome when confidence stays low
    min_confidence_floor: float = 0.3  # Confidence threshold below which a think step is "low"
    confidence_window: int = 3  # Consecutive low-confidence steps before abstention fires

    # Logging
    log_iterations: bool = True  # Log each iteration
    log_tool_results: bool = True  # Log tool execution results
    emit_progress_events: bool = True  # Emit progress to event stream


# =============================================================================
# Message Types (Manus Pattern)
# =============================================================================


class MessageType(Enum):
    """
    Message semantics for agent-user communication (Manus pattern).

    - NOTIFY: Non-blocking progress updates
    - ASK: Blocking questions requiring user response
    """

    NOTIFY = auto()  # Non-blocking notification
    ASK = auto()  # Blocking question


@dataclass
class AgentMessage:
    """A message from agent to user with semantic type."""

    message_type: MessageType
    content: str
    options: list[str] | None = None  # For ASK messages
    metadata: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=now_utc)
    task_id: str | None = None
    requires_response: bool = False

    def __post_init__(self):
        """Set requires_response based on message type."""
        self.requires_response = self.message_type == MessageType.ASK

    def to_dict(self) -> dict:
        """Convert to dictionary for events."""
        return {
            "type": self.message_type.name.lower(),
            "content": self.content,
            "options": self.options,
            "requires_response": self.requires_response,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
            "task_id": self.task_id,
        }


# =============================================================================
# Loop Outcomes (Issue #6627)
# =============================================================================


class LoopOutcome(Enum):
    """High-level reason a loop run terminated."""

    COMPLETED = auto()  # Task finished normally
    REPETITION_HALT = auto()  # Halted: identical tool calls (#3877)
    STAGNATED = auto()  # Halted: observation novelty plateaued (#6627)
    MAX_ITERATIONS = auto()  # Exceeded iteration budget
    MAX_ERRORS = auto()  # Exceeded consecutive-error budget
    CANCELLED = auto()  # Externally cancelled


# =============================================================================
# Observation Fingerprint (Issue #6627)
# =============================================================================


@dataclass
class ObservationFingerprint:
    """SHA-256 content digest + novelty metrics for a single tool result."""

    iteration: int
    content_hash: str
    content_size: int
    novel_token_ratio: float
    timestamp: datetime = field(default_factory=now_utc)


# =============================================================================
# Task Context
# =============================================================================


@dataclass
class TaskContext:
    """Context for the current task execution."""

    task_id: str
    description: str
    started_at: datetime = field(default_factory=now_utc)
    iteration_count: int = 0
    tools_executed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    user_messages: list[str] = field(default_factory=list)
    think_history: list[ThinkResult] = field(default_factory=list)
    plan_id: str | None = None
    current_step_id: str | None = None
    metadata: dict = field(default_factory=dict)
    # Repetitive tool-call detection: maps content-hash -> call count (#3255)
    tool_call_hashes: dict[str, int] = field(default_factory=dict)
    # Semantic stagnation detection: ordered fingerprints (#6627)
    observation_fingerprints: list[ObservationFingerprint] = field(default_factory=list)
    # Accumulated token vocabulary for novelty scoring
    _seen_tokens: set[str] = field(default_factory=set, repr=False)

    def record_observation(self, content: Any, iteration: int) -> "ObservationFingerprint":
        """Fingerprint a tool result and append it to observation_fingerprints.

        Returns the new fingerprint.  Mutates _seen_tokens in place.
        Issue #6627.
        """
        from agent_loop.fingerprint import (
            compute_novel_token_ratio,
        )
        from agent_loop.fingerprint import content_hash as _hash
        from agent_loop.fingerprint import (
            normalize_content,
        )

        normalized = normalize_content(content)
        ratio = compute_novel_token_ratio(content, self._seen_tokens)
        fp = ObservationFingerprint(
            iteration=iteration,
            content_hash=_hash(content),
            content_size=len(normalized),
            novel_token_ratio=ratio,
        )
        self.observation_fingerprints.append(fp)
        return fp

    def add_tool(self, tool_name: str) -> None:
        """Record tool execution."""
        self.tools_executed.append(tool_name)

    def record_tool_call_hash(self, call_hash: str) -> int:
        """Increment call count for a content hash and return the new count.

        Issue #3255: Used by AgentLoop repetition detection.
        """
        count = self.tool_call_hashes.get(call_hash, 0) + 1
        self.tool_call_hashes[call_hash] = count
        return count

    def add_error(self, error: str) -> None:
        """Record an error."""
        self.errors.append(error)

    def add_think(self, result: ThinkResult) -> None:
        """Record a think result."""
        self.think_history.append(result)

    def get_duration_ms(self) -> float:
        """Get task duration in milliseconds."""
        return (now_utc() - self.started_at).total_seconds() * 1000

    def to_dict(self) -> dict:
        """Convert to dictionary for events/logging."""
        return {
            "task_id": self.task_id,
            "description": self.description,
            "started_at": self.started_at.isoformat(),
            "iteration_count": self.iteration_count,
            "tools_executed_count": len(self.tools_executed),
            "errors_count": len(self.errors),
            "duration_ms": self.get_duration_ms(),
            "plan_id": self.plan_id,
            "current_step_id": self.current_step_id,
        }
