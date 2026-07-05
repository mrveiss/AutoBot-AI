# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""ContentSourceRegistry — probe-cached, circuit-breaker-guarded chain execution (#10932)."""

from __future__ import annotations

import time

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from circuit_breaker import CircuitBreakerOpenError, get_circuit_breaker_manager
from content_reach.base import ContentRequest, ContentResult
from content_reach.chain import ContentSourceChain
from source_attribution import SourceType, track_source

logger = get_logger(__name__)

# Liveness-probe cache TTL, matching provider_registry's 30s convention.
_PROBE_TTL_S = 30.0


class ContentSourceRegistry:
    """Maps content sources to fallback chains and executes them resiliently."""

    def __init__(self) -> None:
        self._chains: dict[str, ContentSourceChain] = {}
        self._probe_cache: dict[str, tuple[float, bool]] = {}

    def register_chain(self, chain: ContentSourceChain) -> None:
        """Register (or overwrite) the chain for a source."""
        self._chains[chain.source] = chain

    def get_chain(self, source: str) -> ContentSourceChain | None:
        """Return the chain for a source, or None."""
        return self._chains.get(source)

    def list_sources(self) -> dict[str, list[str]]:
        """Return {source: [backend names in order]} for all registered sources."""
        return {source: chain.backend_names() for source, chain in self._chains.items()}

    def clear(self) -> None:
        """Remove all chains and cached probes (test helper)."""
        self._chains.clear()
        self._probe_cache.clear()

    async def _is_live(self, backend) -> bool:
        cached = self._probe_cache.get(backend.name)
        now = time.monotonic()
        if cached is not None and now - cached[0] < _PROBE_TTL_S:
            return cached[1]
        try:
            live = await backend.probe()
        except Exception as exc:  # a probe must never crash the registry
            logger.warning("content_reach probe %s raised %s: %s", backend.name, type(exc).__name__, exc)
            live = False
        self._probe_cache[backend.name] = (now, live)
        return live

    async def probe_all(self) -> dict[str, list[str]]:
        """Return {source: [live backend names]} — powers the health probe."""
        result: dict[str, list[str]] = {}
        for source, chain in self._chains.items():
            result[source] = [b.name for b in chain.backends if await self._is_live(b)]
        return result

    async def fetch(self, source: str, request: ContentRequest) -> ContentResult:
        """Run the source's chain primary->fallback and return the first success."""
        chain = self.get_chain(source)
        if chain is None:
            return ContentResult.failure(SourceType.WEB_SEARCH, f"unknown source: {source}")

        chain = chain.reordered()
        request.source = source
        manager = get_circuit_breaker_manager()
        last_detail = "no backend attempted"

        for backend in chain.backends:
            if not await self._is_live(backend):
                last_detail = f"{backend.name}: probe failed"
                continue

            breaker = manager.get_breaker(f"content_reach:{backend.name}")
            try:
                result = await breaker.call_async(backend.fetch, request)
            except CircuitBreakerOpenError:
                last_detail = f"{backend.name}: circuit open"
                continue
            except Exception as exc:
                last_detail = f"{backend.name}: {type(exc).__name__}: {exc}"
                self._probe_cache.pop(backend.name, None)  # force re-probe after a live failure
                continue

            if result.success:
                track_source(
                    chain.source_type,
                    (result.text or "")[:500],
                    reliability=result.reliability,
                    metadata={
                        "backend": backend.name,
                        "url": result.url,
                        "source": source,
                        **result.metadata,
                    },
                )
                return result

            last_detail = f"{backend.name}: unsuccessful result"

        return ContentResult.failure(chain.source_type, f"all backends failed ({last_detail})")


get_content_source_registry = lazy_singleton(ContentSourceRegistry)
