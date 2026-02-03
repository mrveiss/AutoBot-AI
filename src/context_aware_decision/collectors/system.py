# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
System Context Collector

Specialized collector for system state context information.

Part of Issue #381 - God Class Refactoring
"""

import logging
from typing import Any, Dict, List, Optional

from ..models import ContextElement
from ..time_provider import TimeProvider
from ..types import ContextType

logger = logging.getLogger(__name__)


class SystemContextCollector:
    """Specialized collector for system state context information."""

    def __init__(self):
        """Initialize system context collector with time provider."""
        self.time_provider = TimeProvider()

    async def collect(self) -> List[ContextElement]:
        """Collect system state context."""
        try:
            from src.takeover_manager import takeover_manager

            system_elements = []

            # Takeover system status
            system_elements.append(self._create_takeover_status_context())

            # Active takeovers
            active_takeovers = takeover_manager.get_active_sessions()
            if active_takeovers:
                system_elements.append(
                    self._create_active_takeovers_context(active_takeovers)
                )

            # System resource information
            resource_context = self._create_resource_context()
            if resource_context:
                system_elements.append(resource_context)

            return system_elements

        except Exception as e:
            logger.debug("System context collection failed: %s", e)
            return []

    def _create_takeover_status_context(self) -> ContextElement:
        """Create context element for takeover system status."""
        from src.takeover_manager import takeover_manager

        takeover_status = takeover_manager.get_system_status()
        return ContextElement(
            context_id=f"takeover_status_{self.time_provider.current_timestamp_millis()}",
            context_type=ContextType.SYSTEM_STATE,
            content=takeover_status,
            confidence=1.0,
            relevance_score=0.8,
            timestamp=self.time_provider.current_timestamp(),
            source="takeover_manager",
            metadata={"type": "takeover_status"},
        )

    def _create_active_takeovers_context(
        self, active_takeovers: List[Dict[str, Any]]
    ) -> ContextElement:
        """Create context element for active takeovers."""
        return ContextElement(
            context_id=f"active_takeovers_{self.time_provider.current_timestamp_millis()}",
            context_type=ContextType.SYSTEM_STATE,
            content=active_takeovers,
            confidence=1.0,
            relevance_score=0.95,
            timestamp=self.time_provider.current_timestamp(),
            source="takeover_manager",
            metadata={"type": "active_takeovers", "count": len(active_takeovers)},
        )

    def _create_resource_context(self) -> Optional[ContextElement]:
        """Create context element for system resources."""
        try:
            import psutil

            resource_info = {
                "cpu_percent": psutil.cpu_percent(),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_usage": psutil.disk_usage("/").percent,
            }

            return ContextElement(
                context_id=f"system_resources_{self.time_provider.current_timestamp_millis()}",
                context_type=ContextType.ENVIRONMENTAL,
                content=resource_info,
                confidence=1.0,
                relevance_score=0.6,
                timestamp=self.time_provider.current_timestamp(),
                source="system_monitor",
                metadata={"type": "resource_usage"},
            )

        except ImportError:
            logger.debug("psutil not available for system resource monitoring")
            return None
