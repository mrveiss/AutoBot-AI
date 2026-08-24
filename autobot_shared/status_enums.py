# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Centralized Status and Category Enums

Issue #670: Consolidate duplicate string literals into type-safe enums.
This module provides shared enums to replace hardcoded status strings
throughout the codebase.

Usage:
    from constants.status_enums import TaskStatus, Severity, Priority

    status = TaskStatus.PENDING
    if status == TaskStatus.COMPLETED:
        ...

    # String comparison still works
    if status.value == "completed":
        ...
"""

from enum import Enum
from typing import Iterable


class TaskStatus(Enum):
    """
    Task execution status enumeration.

    Used across orchestration, workflows, tools, and agent systems.
    Replaces hardcoded strings: "pending", "active", "completed", "failed", etc.
    """

    PENDING = "pending"
    QUEUED = "queued"  # Alias for PENDING with explicit queue semantics (#6973)
    SCHEDULED = "scheduled"  # Pending with future-execution time (#6973: WorkflowStatus)
    ACTIVE = "active"  # Alias for IN_PROGRESS in some contexts
    IN_PROGRESS = "in_progress"
    RUNNING = "running"  # Alias for IN_PROGRESS
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    PAUSED = "paused"
    RETRYING = "retrying"
    RETRY = "retry"  # Alias for RETRYING (#6520: utils/task_queue used RETRY)
    BLOCKED = "blocked"
    WAITING = "waiting"
    TIMEOUT = "timeout"  # #6520: services/agent_analytics + subagent_manager use TIMEOUT
    PARKED = "parked"  # #11586: dead-letter terminal state — retries exhausted, awaiting operator review

    @classmethod
    def is_terminal(cls, status: "TaskStatus") -> bool:
        """Check if status is a terminal state (no further transitions)."""
        return status in {cls.COMPLETED, cls.FAILED, cls.CANCELLED, cls.PARKED}

    @classmethod
    def is_active(cls, status: "TaskStatus") -> bool:
        """Check if status indicates active work."""
        return status in {cls.ACTIVE, cls.IN_PROGRESS, cls.RUNNING, cls.RETRYING}


# Job/Workflow lifecycle alias — semantic shortcut for callers reasoning
# about generic job execution rather than agent tasks (#6973). Canonically
# the same enum as TaskStatus; use whichever name reads clearer at the call
# site. Replaces ad-hoc per-module *Status enums (WorkflowStatus, etc.).
JobStatus = TaskStatus
WorkflowStatus = TaskStatus


class Severity(Enum):
    """
    Severity / risk-level enumeration.

    Canonical enum for severity, risk, and impact concepts across the
    codebase. Used in security, analytics, code-intelligence, logging,
    and threat detection.

    Replaces hardcoded strings ("low", "medium", "high", "critical",
    "unknown", "info", "minimal") and consolidates 10+ duplicate enums
    (#6689): Severity, IssueSeverity, DFASeverity, ImpactLevel, CostLevel,
    DebtSeverity, RiskLevel — all collapse to this enum.

    #14956 added WARNING, DEGRADED and ERROR. They are not synonyms of an
    existing rung and were NOT folded into one, because each is a value the
    platform already emits across a boundary that would change if it moved:

    * ``warning`` is a Prometheus label value — ``PerformanceMonitor``
      publishes ``update_active_alerts("warning", ...)`` and the shipped
      alert rules carry ``severity: warning``. Mapping it to ``medium``
      would rename a scraped label.
    * ``degraded`` is serialised into the causal-analysis API response and
      grades partial impact between ``warning`` and ``critical``.
    * ``error`` is the rung the capability audit grades findings at, kept
      distinct from ``warning`` because the two are counted separately.

    So this enum is the severity *vocabulary*. Numeric risk grading uses the
    narrower ``score_ladder()`` — see that method for why the distinction is
    load-bearing rather than cosmetic.
    """

    UNKNOWN = "unknown"
    INFO = "info"
    MINIMAL = "minimal"
    LOW = "low"
    WARNING = "warning"  # #14956: monitoring/log-level rung, a Prometheus label
    MEDIUM = "medium"
    DEGRADED = "degraded"  # #14956: partial impact, emitted by causal analysis
    HIGH = "high"
    ERROR = "error"  # #14956: audit-finding rung, graded above "warning"
    CRITICAL = "critical"

    @classmethod
    def score_ladder(cls) -> tuple["Severity", ...]:
        """The rungs ``from_score`` can produce, in ascending order.

        The enum is the whole severity *vocabulary*; this is the subset that
        numeric risk grading maps onto. Distributions keyed by severity
        (``{level.value: 0 for level in RiskLevel}``) iterate this rather
        than the enum, so #14956 adding vocabulary members did not silently
        add three always-zero keys to a shipped API response.
        """
        return (
            cls.UNKNOWN,
            cls.INFO,
            cls.MINIMAL,
            cls.LOW,
            cls.MEDIUM,
            cls.HIGH,
            cls.CRITICAL,
        )

    @classmethod
    def from_score(cls, score: float) -> "Severity":
        """
        Convert numeric score (0.0-1.0) to severity level.

        Args:
            score: Risk/severity score between 0.0 and 1.0

        Returns:
            Corresponding Severity enum value
        """
        if score >= 0.9:
            return cls.CRITICAL
        elif score >= 0.7:
            return cls.HIGH
        elif score >= 0.5:
            return cls.MEDIUM
        elif score >= 0.3:
            return cls.LOW
        elif score > 0:
            return cls.INFO
        return cls.UNKNOWN

    @classmethod
    def to_score(cls, severity: "Severity") -> float:
        """Convert severity to representative score."""
        scores = {
            cls.UNKNOWN: 0.0,
            cls.INFO: 0.1,
            cls.MINIMAL: 0.2,
            cls.LOW: 0.3,
            cls.WARNING: 0.4,
            cls.MEDIUM: 0.5,
            cls.DEGRADED: 0.6,
            cls.HIGH: 0.7,
            cls.ERROR: 0.8,
            cls.CRITICAL: 0.9,
        }
        return scores.get(severity, 0.0)


# Risk-level alias — semantic shortcut for callers reasoning about "risk"
# rather than "severity"; canonically the same enum (#6689). Use whichever
# name reads clearer at the call site.
RiskLevel = Severity


class CommandRisk(Enum):
    """Risk classification for a shell command, for policy decisions (#13845).

    Canonical union of two forks that modelled the same concept under
    different names, so neither side's tail is lost:

    * ``secure_command_executor.CommandRisk`` — SAFE / MODERATE / HIGH /
      CRITICAL / FORBIDDEN, used for executor policy decisions.
    * ``api.schemas_terminal.CommandRiskLevel`` — SAFE / MODERATE / HIGH /
      DANGEROUS, the wire schema for the *same* subsystem.

    Three members matched; the tails did not. A command the executor rated
    ``FORBIDDEN`` had no faithful representation in its own wire schema, and
    ``DANGEROUS`` — already serialized by ``POST /terminal/command`` and by
    the terminal WebSocket — existed nowhere in the executor's vocabulary.
    Both tails are kept here rather than one being picked as the survivor.

    ``DANGEROUS`` and ``FORBIDDEN`` are distinct *reasons* that reach the same
    verdict: DANGEROUS means the command matched a destructive pattern
    (``RISKY_COMMAND_PATTERNS``), FORBIDDEN means the base command is on the
    executor's deny list (``FORBIDDEN_COMMANDS``). They keep separate values
    because ``"dangerous"`` is already on the wire; ask ``.blocks`` rather
    than comparing against one of them, or a blocking verdict raised by the
    other producer reads as permitted.

    Not to be confused with ``Severity``/``RiskLevel`` above, which grades how
    bad an *outcome* is. This grades what a *command* is allowed to do.
    """

    SAFE = "safe"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"
    DANGEROUS = "dangerous"
    FORBIDDEN = "forbidden"

    @property
    def rank(self) -> int:
        """Strictness rank, ascending. Declaration order is the ordering.

        Derived from the enum itself so a member added later cannot be missed
        by a hand-written rank table — which is exactly how ``DANGEROUS`` was
        absent from both of the ones this replaces.
        """
        return _COMMAND_RISK_RANK[self]

    @property
    def blocks(self) -> bool:
        """True when the verdict is "do not run this", whatever the reason."""
        return self in _COMMAND_RISK_BLOCKING

    @classmethod
    def strictest(cls, risks: "Iterable[CommandRisk]") -> "CommandRisk | None":
        """Highest-ranked risk in ``risks``, or None when empty."""
        ranked = sorted(risks, key=lambda risk: risk.rank)
        return ranked[-1] if ranked else None


# Rank table derived from declaration order — never hand-written, so it cannot
# narrow silently when a member is added (#13845).
_COMMAND_RISK_RANK: "dict[CommandRisk, int]" = {member: index for index, member in enumerate(CommandRisk)}

# The verdicts that mean "refuse". DANGEROUS blocks because the command matched
# a destructive pattern; FORBIDDEN because the base command is denied outright.
# CRITICAL is deliberately not here: the approval layer grants it under
# ``allow_dangerous`` rather than refusing it.
_COMMAND_RISK_BLOCKING: "frozenset[CommandRisk]" = frozenset({CommandRisk.DANGEROUS, CommandRisk.FORBIDDEN})


class SecretType(str, Enum):
    """What kind of credential a secret is (#13846).

    Canonical union of three definitions that classified the same thing under
    two names, in three layers:

    * ``models.secret.SecretType`` — the persisted classification on the
      ``secrets`` row. Had all nine concrete kinds.
    * ``api.schemas_system.SecretType`` — the request/response vocabulary.
      Had eight: no ``OAUTH_REFRESH_TOKEN``, so ``POST /secrets`` could not
      accept the one kind the row could already store.
    * ``services.agent_secrets_integration.SecretRequirement`` — what an agent
      type may request. Had six of the nine, duplicated verbatim down to the
      identical ``# nosec B105`` / ``# nosemgrep`` comments, plus ``ANY``.
      With no ``OAUTH_REFRESH_TOKEN`` member, an ``AgentSecretMapping`` could
      only describe an OAuth-authenticating agent as ``ANY`` — the blanket
      "every available secret" grant standing in for the most specific one.

    Every member of every side is here. ``str`` subclass so the persisted
    ``secrets.type`` column, which stores these values, keeps comparing and
    serializing exactly as before.

    ``ANY`` is the odd one out: a wildcard *quantifier* over the taxonomy, not
    a kind of credential. It is legal in a requirement (an agent that may use
    any secret) and illegal at rest — nothing may be stored with type "any".
    Use :meth:`concrete` for every persistence or presentation surface, and
    :meth:`expand` to resolve a requirement set into concrete kinds.
    """

    SSH_KEY = "ssh_key"
    # nosemgrep: autobot-hardcoded-secret-key
    PASSWORD = "password"  # nosec B105  # enum value, not actual password
    # nosemgrep: autobot-hardcoded-secret-key
    API_KEY = "api_key"
    # nosemgrep: autobot-hardcoded-secret-key
    TOKEN = "token"  # nosec B105  # enum value, not actual token
    OAUTH_REFRESH_TOKEN = "oauth_refresh_token"  # nosec B105  # enum value
    # nosemgrep: autobot-hardcoded-secret-key
    # #13846: the OAuth bundle the knowledge connectors persist. It was a bare
    # string in credential_store.py, commented "SecretType label" while being
    # absent from every SecretType there was. The value is unchanged so rows
    # already written keep resolving.
    CONNECTOR_OAUTH_TOKEN = "connector_oauth_token"  # nosec B105  # enum value
    CERTIFICATE = "certificate"
    DATABASE_URL = "database_url"
    INFRASTRUCTURE_HOST = "infrastructure_host"
    OTHER = "other"
    ANY = "any"  # Wildcard: "any available secret". Never persisted.

    @classmethod
    def concrete(cls) -> "tuple[SecretType, ...]":
        """Every real credential kind — the taxonomy without the wildcard.

        Derived by excluding ``ANY`` rather than by listing the members, so a
        kind added later is included here without a second edit.
        """
        return tuple(member for member in cls if member is not cls.ANY)

    @classmethod
    def expand(cls, requirements: "Iterable[SecretType]") -> "frozenset[SecretType]":
        """Resolve a requirement set into the concrete kinds it asks for.

        ``ANY`` expands to the whole taxonomy; everything else maps to itself.
        Without this, a requirement of ``{ANY}`` would be looked up as the
        literal type ``"any"`` and match nothing at all.
        """
        wanted = set(requirements)
        if cls.ANY in wanted:
            return frozenset(cls.concrete())
        return frozenset(wanted)


class Priority(Enum):
    """
    Priority level enumeration.

    Used for task scheduling, workflow ordering, and resource allocation.
    Replaces hardcoded strings: "low", "medium", "high", "normal", "critical".
    """

    LOW = "low"
    NORMAL = "normal"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    URGENT = "urgent"

    @classmethod
    def from_numeric(cls, value: int) -> "Priority":
        """
        Convert numeric priority (1-5) to Priority enum.

        Args:
            value: Priority value 1-5 (1=low, 5=critical)

        Returns:
            Corresponding Priority enum value
        """
        mapping = {
            1: cls.LOW,
            2: cls.NORMAL,
            3: cls.MEDIUM,
            4: cls.HIGH,
            5: cls.CRITICAL,
        }
        return mapping.get(value, cls.NORMAL)

    @classmethod
    def to_numeric(cls, priority: "Priority") -> int:
        """Convert priority to numeric value (1-5)."""
        values = {
            cls.LOW: 1,
            cls.NORMAL: 2,
            cls.MEDIUM: 3,
            cls.HIGH: 4,
            cls.CRITICAL: 5,
            cls.URGENT: 5,
        }
        return values.get(priority, 2)


class LLMProvider(Enum):
    """
    LLM provider enumeration.

    Used in ssot_config and throughout LLM integration code.
    Replaces hardcoded strings: "ollama", "openai", "anthropic", "custom".

    Single canonical source of truth (#12661): this enum was previously
    triplicated — ``autobot-backend/llm_shared/types.py::ProviderType`` and
    ``autobot-backend/services/llm_cost_tracker.py::LLMProvider`` are now
    thin aliases of this class. The member set below is the UNION of all
    three historical forks; every ``.value`` string is preserved exactly as
    it was serialized by its origin fork — no provider was renamed or
    dropped, per the #12645 consolidation contract.

    Semantic-mapping notes (kept distinct, not merged):
    - ``VERTEX_AI`` (GCP Vertex AI / ``google-cloud-aiplatform`` SDK, GH#9009,
      real usage in ``llm_shared/providers/vertexai.py``) and ``GOOGLE``
      (from the cost-tracker fork, unused by any call site) are kept as two
      separate values — they can represent different access paths to
      Google's models (direct Gemini API vs. enterprise Vertex SDK) and the
      contract forbids merging two potentially-distinct providers.
    - ``CUSTOM`` (generic custom-endpoint provider, ``ssot_config.custom_endpoint``)
      and ``PROCESS`` (subprocess-based local inference adapter, Issue #1403)
      are semantically different providers, kept separate.
    """

    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    AZURE = "azure"
    CUSTOM = "custom"
    LOCAL = "local"
    # -- union additions from llm_shared/types.py::ProviderType --
    VLLM = "vllm"
    HUGGINGFACE = "huggingface"
    TRANSFORMERS = "transformers"
    MOCK = "mock"
    AI_STACK = "ai_stack"  # Issue #1403
    PROCESS = "process"  # Issue #1403
    LAYER_INFERENCE = "layer_inference"  # Issue #3104
    GROQ = "groq"  # Issue #4096
    MISTRAL = "mistral"  # Issue #10549
    VERTEX_AI = "vertexai"  # GH#9009
    BEDROCK = "bedrock"  # GH#9010
    # -- union additions from services/llm_cost_tracker.py::LLMProvider --
    GOOGLE = "google"  # cost-tracker fork; unused by any provider call site
    OPENROUTER = "openrouter"  # cost-tracker fork; ProviderType lacked this
    # (llm_shared/providers/openrouter.py had a defensive hasattr() guard
    # against ProviderType.OPENROUTER not existing — a real symptom of the
    # triplication bug this consolidation fixes)

    @classmethod
    def supports_streaming(cls, provider: "LLMProvider") -> bool:
        """Check if provider supports streaming responses."""
        return provider in {cls.OLLAMA, cls.OPENAI, cls.ANTHROPIC, cls.AZURE}

    @classmethod
    def requires_api_key(cls, provider: "LLMProvider") -> bool:
        """Check if provider requires API key authentication."""
        return provider in {cls.OPENAI, cls.ANTHROPIC, cls.AZURE}


class OperationOutcome(Enum):
    """
    Generic operation outcome enumeration.

    Used for tool results, API responses, and operation tracking.
    """

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"
    ERROR = "error"
    PENDING = "pending"


class HealthStatus(Enum):
    """
    Service/component health status.

    Used in monitoring, health checks, and service discovery.
    """

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
    STARTING = "starting"
    STOPPING = "stopping"


class AgentStatus(Enum):
    """
    Canonical operational health state of a running agent (#7504).

    Replaces the local class in agents/base_agent.py. Distinct from
    AgentLifecycleStatus which tracks registry/DB lifecycle.
    """

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    OFFLINE = "offline"


class AgentLifecycleStatus(str, Enum):
    """
    Registry/lifecycle state of an agent record (#7504, #1754).

    Replaces the local AgentStatus class in models/agent.py. str-subclass
    so SQLAlchemy can coerce directly to/from the column string value.
    """

    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class ConnectionStatus(str, Enum):
    """
    Client-side reachability state of an external service connection (#10008).

    Canonical states for AIStackClient.connection_status and sibling client
    status fields. str-subclass so existing ``== "connected"`` comparisons and
    JSON serialization keep working while the states become type-checked and
    greppable. Replaces the bare literals "unknown"/"connected"/"error"/
    "disabled" that drifted when #9782 added the 4th value.
    """

    UNKNOWN = "unknown"
    CONNECTED = "connected"
    ERROR = "error"
    DISABLED = "disabled"


# Task priority — canonical alias for Priority covering agent/task scheduling.
# Replaces local TaskPriority classes in services/agents/subagent_task.py,
# utils/task_queue.py, and orchestrator.py (#7504).
TaskPriority = Priority

__all__ = [
    "TaskStatus",
    "JobStatus",
    "WorkflowStatus",
    "Severity",
    "RiskLevel",
    "CommandRisk",
    "SecretType",
    "Priority",
    "TaskPriority",
    "LLMProvider",
    "OperationOutcome",
    "HealthStatus",
    "AgentStatus",
    "AgentLifecycleStatus",
    "ConnectionStatus",
]
