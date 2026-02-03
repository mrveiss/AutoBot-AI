# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Base classes and data structures for provider health checking
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ProviderStatus(str, Enum):
    """Provider health status enumeration"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"  # Provider available but experiencing issues
    UNAVAILABLE = "unavailable"
    NOT_CONFIGURED = "not_configured"
    UNKNOWN = "unknown"


@dataclass
class ProviderHealthResult:
    """
    Standardized provider health check result

    Attributes:
        status: Overall health status
        available: Whether provider can be used
        message: Human-readable status message
        response_time: Health check response time in seconds
        provider: Provider name (ollama, openai, anthropic, google)
        details: Additional provider-specific details
    """

    status: ProviderStatus
    available: bool
    message: str
    response_time: float
    provider: str
    details: Optional[dict] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "status": self.status.value,
            "available": self.available,
            "message": self.message,
            "response_time": self.response_time,
            "provider": self.provider,
            "details": self.details or {},
        }


class BaseProviderHealth(ABC):
    """
    Abstract base class for provider health checkers

    All provider implementations must inherit from this class and implement
    the check_health() method.
    """

    def __init__(self, provider_name: str):
        """
        Initialize provider health checker

        Args:
            provider_name: Name of the provider (e.g., "ollama", "openai")
        """
        self.provider_name = provider_name

    @abstractmethod
    async def check_health(self, timeout: float = 5.0) -> ProviderHealthResult:
        """
        Check provider health status

        Args:
            timeout: Maximum time to wait for health check (seconds)

        Returns:
            ProviderHealthResult with health status information
        """

    def _create_result(
        self,
        status: ProviderStatus,
        available: bool,
        message: str,
        response_time: float,
        details: Optional[dict] = None,
    ) -> ProviderHealthResult:
        """
        Helper to create standardized health result

        Args:
            status: Provider status
            available: Whether provider is available
            message: Status message
            response_time: Response time in seconds
            details: Additional details

        Returns:
            ProviderHealthResult instance
        """
        return ProviderHealthResult(
            status=status,
            available=available,
            message=message,
            response_time=response_time,
            provider=self.provider_name,
            details=details,
        )
