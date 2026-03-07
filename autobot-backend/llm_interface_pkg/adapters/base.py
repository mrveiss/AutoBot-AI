# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Adapter Base - Abstract base class for pluggable LLM backend adapters.

Issue #1403: Formal adapter registry for LLM backends.
Each adapter implements execute, test_environment, list_models,
and optionally session_codec for persistent conversations.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from ..models import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)


class DiagnosticLevel(str, Enum):
    """Severity level for environment diagnostics."""

    INFO = "info"
    WARN = "warn"
    ERROR = "error"


@dataclass
class DiagnosticMessage:
    """A single diagnostic finding from test_environment."""

    level: DiagnosticLevel
    message: str
    details: Optional[Dict[str, Any]] = None


@dataclass
class EnvironmentTestResult:
    """Result of adapter self-diagnosis."""

    healthy: bool
    adapter_type: str
    diagnostics: List[DiagnosticMessage] = field(default_factory=list)
    models_available: List[str] = field(default_factory=list)
    response_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize for API responses."""
        return {
            "healthy": self.healthy,
            "adapter_type": self.adapter_type,
            "diagnostics": [
                {
                    "level": d.level.value,
                    "message": d.message,
                    "details": d.details or {},
                }
                for d in self.diagnostics
            ],
            "models_available": self.models_available,
            "response_time": self.response_time,
            "metadata": self.metadata,
        }


@dataclass
class AdapterConfig:
    """Configuration for an adapter instance."""

    adapter_type: str
    enabled: bool = True
    priority: int = 0
    settings: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class SessionCodec(Protocol):
    """Optional protocol for session state serialization."""

    def serialize(self, session_state: Dict[str, Any]) -> bytes:
        """Serialize session state to bytes."""
        ...

    def deserialize(self, data: bytes) -> Dict[str, Any]:
        """Deserialize bytes back to session state."""
        ...


class AdapterBase(ABC):
    """
    Abstract base class for LLM backend adapters.

    Each backend (Ollama, AI Stack, OpenAI, etc.) implements this
    interface for execution, health checking, model discovery,
    and optional session management.
    """

    def __init__(self, adapter_type: str, config: Optional[AdapterConfig] = None):
        self.adapter_type = adapter_type
        self.config = config or AdapterConfig(adapter_type=adapter_type)
        self._session_codec: Optional[SessionCodec] = None

    @abstractmethod
    async def execute(self, request: LLMRequest) -> LLMResponse:
        """Execute an LLM call with full context."""

    @abstractmethod
    async def test_environment(self) -> EnvironmentTestResult:
        """Self-diagnose connectivity, auth, and model availability."""

    @abstractmethod
    async def list_models(self) -> List[str]:
        """Discover available models dynamically."""

    @property
    def session_codec(self) -> Optional[SessionCodec]:
        """Optional session state codec for persistent conversations."""
        return self._session_codec

    @session_codec.setter
    def session_codec(self, codec: Optional[SessionCodec]) -> None:
        self._session_codec = codec

    @property
    def is_enabled(self) -> bool:
        """Whether this adapter is enabled."""
        return self.config.enabled

    async def cleanup(self) -> None:
        """Release resources held by this adapter. Override if needed."""


__all__ = [
    "AdapterBase",
    "AdapterConfig",
    "DiagnosticLevel",
    "DiagnosticMessage",
    "EnvironmentTestResult",
    "SessionCodec",
]
