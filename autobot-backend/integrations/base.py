# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Base Integration Framework (Issue #61)

Provides abstract base class and common utilities for all external
tool integrations. Each integration extends BaseIntegration and
implements connection testing, health checks, and tool-specific methods.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class IntegrationStatus(str, Enum):
    """Status of an integration connection."""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    CONFIGURING = "configuring"
    UNAUTHORIZED = "unauthorized"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"


class IntegrationConfig(BaseModel):
    """Configuration for an external integration."""

    name: str = Field(..., description="Integration name")
    provider: str = Field(..., description="Provider identifier")
    enabled: bool = Field(True, description="Whether integration is active")
    base_url: Optional[str] = Field(None, description="Base URL for the service")
    api_key: Optional[str] = Field(None, description="API key (stored encrypted)")
    api_secret: Optional[str] = Field(None, description="API secret (stored encrypted)")
    token: Optional[str] = Field(None, description="Auth token (stored encrypted)")
    username: Optional[str] = Field(None, description="Username for basic auth")
    password: Optional[str] = Field(None, description="Password (stored encrypted)")
    extra: Dict[str, Any] = Field(
        default_factory=dict, description="Provider-specific config"
    )


class IntegrationHealth(BaseModel):
    """Health status response for an integration."""

    provider: Optional[str] = None
    status: IntegrationStatus
    latency_ms: Optional[float] = None
    message: Optional[str] = None
    last_checked: datetime = Field(default_factory=datetime.utcnow)
    details: Dict[str, Any] = Field(default_factory=dict)


class IntegrationAction(BaseModel):
    """Describes an available action for an integration."""

    name: str
    description: str
    method: str = "GET"
    parameters: Dict[str, str] = Field(default_factory=dict)


class BaseIntegration(ABC):
    """Abstract base for all external tool integrations.

    Subclasses must implement:
    - test_connection() - verify credentials and connectivity
    - get_available_actions() - list supported operations
    - execute_action() - run a named action with parameters
    """

    def __init__(self, config: IntegrationConfig):
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{config.provider}")
        self._status = IntegrationStatus.DISCONNECTED

    @property
    def status(self) -> IntegrationStatus:
        """Current connection status."""
        return self._status

    @property
    def provider(self) -> str:
        """Provider identifier."""
        return self.config.provider

    @abstractmethod
    async def test_connection(self) -> IntegrationHealth:
        """Test connectivity and return health status."""
        ...

    @abstractmethod
    def get_available_actions(self) -> List[IntegrationAction]:
        """Return list of actions this integration supports."""
        ...

    @abstractmethod
    async def execute_action(
        self, action: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a named action with given parameters."""
        ...

    async def _make_request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        """Make an HTTP request to the external service.

        Helper for test_connection and execute_action.
        """
        import aiohttp

        merged_headers = headers or {}
        if self.config.api_key:
            merged_headers.setdefault("Authorization", f"Bearer {self.config.api_key}")

        try:
            timeout_obj = aiohttp.ClientTimeout(total=timeout)
            async with aiohttp.ClientSession(timeout=timeout_obj) as session:
                async with session.request(
                    method, url, headers=merged_headers, json=json_data
                ) as resp:
                    body = await resp.json()
                    return {
                        "status_code": resp.status,
                        "body": body,
                        "headers": dict(resp.headers),
                    }
        except aiohttp.ClientError as exc:
            self.logger.warning("Request to %s failed: %s", url, exc)
            return {"status_code": 0, "body": {}, "error": str(exc)}
