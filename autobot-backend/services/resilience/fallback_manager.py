# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Fallback Manager Module

Issue #4342: Manages fallback chains for critical paths.
Primary service → secondary service → minimal-feature mode.
Ensures core functions work even when peripherals fail.
"""

from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable, Dict, List

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


@dataclass
class Fallback:
    """A fallback option in the chain."""

    name: str
    handler: Callable[..., Any]
    is_async: bool = False


class FallbackChain:
    """Chain of fallbacks to try in sequence."""

    def __init__(self, name: str, fallbacks: List[Fallback] | None = None) -> None:
        """Initialize fallback chain."""
        self.name = name
        self.fallbacks = fallbacks or []
        self.attempted = 0
        self.succeeded = False

    def add(self, name: str, handler: Callable, is_async: bool = False) -> None:
        """Add fallback to chain."""
        self.fallbacks.append(Fallback(name, handler, is_async))

    def clear_stats(self) -> None:
        """Reset statistics."""
        self.attempted = 0
        self.succeeded = False

    def execute(self, *args, **kwargs) -> Any:
        """
        Execute fallback chain until one succeeds.

        Returns:
            Result from first successful fallback

        Raises:
            Exception: If all fallbacks fail
        """
        self.clear_stats()

        for fallback in self.fallbacks:
            self.attempted += 1
            try:
                logger.info(
                    "Trying fallback %s (step %d/%d) for %s",
                    fallback.name,
                    self.attempted,
                    len(self.fallbacks),
                    self.name,
                )

                if fallback.is_async:
                    raise ValueError(f"Sync execute called on async fallback {fallback.name}")

                result = fallback.handler(*args, **kwargs)
                self.succeeded = True
                logger.info(
                    "Fallback %s succeeded for %s",
                    fallback.name,
                    self.name,
                )
                return result
            except Exception as e:
                logger.warning(
                    "Fallback %s failed for %s: %s",
                    fallback.name,
                    self.name,
                    type(e).__name__,
                )
                continue

        raise RuntimeError(f"All fallbacks exhausted for {self.name} " f"({self.attempted} attempts)")

    async def execute_async(self, *args, **kwargs) -> Any:
        """
        Execute async fallback chain until one succeeds.

        Returns:
            Result from first successful fallback

        Raises:
            Exception: If all fallbacks fail
        """
        self.clear_stats()

        for fallback in self.fallbacks:
            self.attempted += 1
            try:
                logger.info(
                    "Trying fallback %s (step %d/%d) for %s",
                    fallback.name,
                    self.attempted,
                    len(self.fallbacks),
                    self.name,
                )

                if fallback.is_async:
                    result = await fallback.handler(*args, **kwargs)
                else:
                    result = fallback.handler(*args, **kwargs)

                self.succeeded = True
                logger.info(
                    "Fallback %s succeeded for %s",
                    fallback.name,
                    self.name,
                )
                return result
            except Exception as e:
                logger.warning(
                    "Fallback %s failed for %s: %s",
                    fallback.name,
                    self.name,
                    type(e).__name__,
                )
                continue

        raise RuntimeError(f"All fallbacks exhausted for {self.name} " f"({self.attempted} attempts)")


class FallbackManager:
    """Manages fallback chains for different critical paths."""

    def __init__(self) -> None:
        """Initialize fallback manager."""
        self.chains: Dict[str, FallbackChain] = {}
        self._lock = Lock()

    def create_chain(self, name: str) -> FallbackChain:
        """Create new fallback chain."""
        with self._lock:
            if name in self.chains:
                raise ValueError(f"Chain {name} already exists")
            chain = FallbackChain(name)
            self.chains[name] = chain
            return chain

    def get_chain(self, name: str) -> FallbackChain | None:
        """Get existing fallback chain."""
        with self._lock:
            return self.chains.get(name)

    def execute(self, chain_name: str, *args, **kwargs) -> Any:
        """
        Execute fallback chain.

        Args:
            chain_name: Name of fallback chain
            *args: Arguments to pass to fallbacks
            **kwargs: Keyword arguments to pass to fallbacks

        Returns:
            Result from successful fallback
        """
        chain = self.get_chain(chain_name)
        if not chain:
            raise ValueError(f"Fallback chain {chain_name} not found")
        return chain.execute(*args, **kwargs)

    async def execute_async(self, chain_name: str, *args, **kwargs) -> Any:
        """
        Execute async fallback chain.

        Args:
            chain_name: Name of fallback chain
            *args: Arguments to pass to fallbacks
            **kwargs: Keyword arguments to pass to fallbacks

        Returns:
            Result from successful fallback
        """
        chain = self.get_chain(chain_name)
        if not chain:
            raise ValueError(f"Fallback chain {chain_name} not found")
        return await chain.execute_async(*args, **kwargs)

    def get_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all fallback chains."""
        with self._lock:
            return {
                name: {
                    "fallback_count": len(chain.fallbacks),
                    "succeeded": chain.succeeded,
                    "last_attempted": chain.attempted,
                }
                for name, chain in self.chains.items()
            }


_global_manager = None
_manager_lock = Lock()


def get_fallback_manager() -> FallbackManager:
    """Get global fallback manager instance (singleton)."""
    global _global_manager
    if _global_manager is None:
        with _manager_lock:
            if _global_manager is None:
                _global_manager = FallbackManager()
    return _global_manager
