# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Centralized Status and Category Enums

Issue #670: Consolidate duplicate string literals into type-safe enums.
This module provides shared enums to replace hardcoded status strings
throughout the codebase.

Usage:
    from src.constants.status_enums import TaskStatus, Severity, Priority

    status = TaskStatus.PENDING
    if status == TaskStatus.COMPLETED:
        ...

    # String comparison still works
    if status.value == "completed":
        ...
"""

from enum import Enum


class TaskStatus(Enum):
    """
    Task execution status enumeration.

    Used across orchestration, workflows, tools, and agent systems.
    Replaces hardcoded strings: "pending", "active", "completed", "failed", etc.
    """

    PENDING = "pending"
    ACTIVE = "active"  # Alias for IN_PROGRESS in some contexts
    IN_PROGRESS = "in_progress"
    RUNNING = "running"  # Alias for IN_PROGRESS
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"
    BLOCKED = "blocked"
    WAITING = "waiting"

    @classmethod
    def is_terminal(cls, status: "TaskStatus") -> bool:
        """Check if status is a terminal state (no further transitions)."""
        return status in {cls.COMPLETED, cls.FAILED, cls.CANCELLED}

    @classmethod
    def is_active(cls, status: "TaskStatus") -> bool:
        """Check if status indicates active work."""
        return status in {cls.ACTIVE, cls.IN_PROGRESS, cls.RUNNING, cls.RETRYING}


class Severity(Enum):
    """
    Severity/risk level enumeration.

    Used in security, analytics, logging, and threat detection.
    Replaces hardcoded strings: "low", "medium", "high", "critical", "unknown".
    """

    UNKNOWN = "unknown"
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

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
            cls.LOW: 0.3,
            cls.MEDIUM: 0.5,
            cls.HIGH: 0.7,
            cls.CRITICAL: 0.9,
        }
        return scores.get(severity, 0.0)


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
    """

    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    AZURE = "azure"
    CUSTOM = "custom"
    LOCAL = "local"

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


__all__ = [
    "TaskStatus",
    "Severity",
    "Priority",
    "LLMProvider",
    "OperationOutcome",
    "HealthStatus",
]
