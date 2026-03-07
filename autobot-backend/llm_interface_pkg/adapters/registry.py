# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Adapter Registry - Central registry for LLM backend adapters.

Issue #1403: Provides registration, lookup by type, fallback behavior,
and runtime adapter switching per agent/task.
"""

import logging
from typing import Dict, List, Optional

from .base import AdapterBase, EnvironmentTestResult

logger = logging.getLogger(__name__)


class AdapterRegistry:
    """
    Singleton registry for LLM backend adapters.

    Manages adapter registration, lookup, fallback chains,
    and per-agent adapter configuration.
    """

    _instance: Optional["AdapterRegistry"] = None

    def __new__(cls) -> "AdapterRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._adapters: Dict[str, AdapterBase] = {}
        self._fallback_chain: List[str] = []
        self._agent_overrides: Dict[str, str] = {}
        self._initialized = True
        logger.info("AdapterRegistry initialized")

    def register(self, adapter: AdapterBase) -> None:
        """Register an adapter by its type name."""
        name = adapter.adapter_type
        if name in self._adapters:
            logger.warning("Overwriting existing adapter: %s", name)
        self._adapters[name] = adapter
        logger.info("Registered adapter: %s", name)

    def unregister(self, adapter_type: str) -> None:
        """Remove an adapter from the registry."""
        if adapter_type in self._adapters:
            del self._adapters[adapter_type]
            logger.info("Unregistered adapter: %s", adapter_type)

    def get(self, adapter_type: str) -> Optional[AdapterBase]:
        """Look up an adapter by type name."""
        return self._adapters.get(adapter_type)

    def get_for_agent(self, agent_id: str) -> Optional[AdapterBase]:
        """Get the adapter configured for a specific agent."""
        override_type = self._agent_overrides.get(agent_id)
        if override_type:
            adapter = self.get(override_type)
            if adapter and adapter.is_enabled:
                return adapter
            logger.warning(
                "Agent %s override '%s' unavailable, using fallback",
                agent_id,
                override_type,
            )
        return self.get_with_fallback()

    def get_with_fallback(
        self, preferred: Optional[str] = None
    ) -> Optional[AdapterBase]:
        """Get an adapter with fallback behavior."""
        if preferred:
            adapter = self.get(preferred)
            if adapter and adapter.is_enabled:
                return adapter

        for adapter_type in self._fallback_chain:
            adapter = self.get(adapter_type)
            if adapter and adapter.is_enabled:
                return adapter

        for adapter in self._adapters.values():
            if adapter.is_enabled:
                return adapter

        return None

    def set_fallback_chain(self, chain: List[str]) -> None:
        """Set the adapter fallback priority order."""
        self._fallback_chain = chain
        logger.info("Fallback chain set: %s", chain)

    def set_agent_override(self, agent_id: str, adapter_type: str) -> None:
        """Configure a specific adapter for an agent."""
        self._agent_overrides[agent_id] = adapter_type
        logger.info(
            "Agent %s override set to adapter: %s",
            agent_id,
            adapter_type,
        )

    def clear_agent_override(self, agent_id: str) -> None:
        """Remove per-agent adapter override."""
        self._agent_overrides.pop(agent_id, None)

    def list_adapters(self) -> List[Dict[str, object]]:
        """List all registered adapters with status."""
        return [
            {
                "type": name,
                "enabled": adapter.is_enabled,
                "priority": adapter.config.priority,
            }
            for name, adapter in self._adapters.items()
        ]

    async def test_all(self) -> Dict[str, EnvironmentTestResult]:
        """Run test_environment on all registered adapters."""
        results = {}
        for name, adapter in self._adapters.items():
            try:
                results[name] = await adapter.test_environment()
            except Exception as e:
                logger.error("Adapter %s test failed: %s", name, e)
                results[name] = EnvironmentTestResult(
                    healthy=False,
                    adapter_type=name,
                    diagnostics=[],
                    metadata={"error": str(e)},
                )
        return results

    async def cleanup_all(self) -> None:
        """Release resources for all adapters."""
        for name, adapter in self._adapters.items():
            try:
                await adapter.cleanup()
            except Exception as e:
                logger.warning("Cleanup failed for %s: %s", name, e)

    @classmethod
    def reset(cls) -> None:
        """Reset singleton (for testing)."""
        cls._instance = None


def get_adapter_registry() -> AdapterRegistry:
    """Get the global AdapterRegistry singleton."""
    return AdapterRegistry()


__all__ = [
    "AdapterRegistry",
    "get_adapter_registry",
]
