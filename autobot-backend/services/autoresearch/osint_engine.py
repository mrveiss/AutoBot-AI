# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Native OSINT Intelligence Sweep Engine

Issue #1949: Parallel sweep of open-source intelligence feeds with per-source
timeout enforcement, Redis result caching for RAG consumption, and a
correlation engine that surfaces cross-domain signal convergence.

Architecture:
  OSINTSource (ABC) ─── concrete sources ──► OSINTEngine.sweep_all()
                                                    │
                                              asyncio.gather
                                                    │
                                       List[SourceResult] ──► Redis cache
                                                    │
                                        correlate() ──► List[CorrelatedSignal]
"""

from __future__ import annotations

import asyncio
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List

import httpx

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_mixin import AsyncRedisClientMixin

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class SourceResult:
    """Result returned by a single OSINT source sweep."""

    source_name: str
    data: Any
    timestamp: float = field(default_factory=time.time)
    success: bool = True
    error: str | None = None
    latency_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_name": self.source_name,
            "data": self.data,
            "timestamp": self.timestamp,
            "success": self.success,
            "error": self.error,
            "latency_seconds": self.latency_seconds,
        }

    @classmethod
    def failure(cls, source_name: str, error: str, latency: float = 0.0) -> "SourceResult":
        """Convenience constructor for a failed result."""
        return cls(
            source_name=source_name,
            data=None,
            success=False,
            error=error,
            latency_seconds=latency,
        )


@dataclass
class CorrelatedSignal:
    """Signal produced when multiple independent OSINT domains converge."""

    description: str
    matching_sources: List[str]
    confidence: float  # 0.0–1.0
    domains: List[str]
    raw_excerpt: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "matching_sources": self.matching_sources,
            "confidence": self.confidence,
            "domains": self.domains,
            "raw_excerpt": self.raw_excerpt,
        }


@dataclass
class CorrelationRule:
    """Declarative rule that triggers when enough independent domains match."""

    domains: List[str]
    keywords: List[str]
    threshold: int  # min domain count that must match
    description: str

    def evaluate(self, results: List[SourceResult]) -> CorrelatedSignal | None:
        """Return a CorrelatedSignal if this rule fires, else None."""
        matching: List[str] = []
        excerpts: List[str] = []

        for result in results:
            if not result.success or result.data is None:
                continue
            domain = _infer_domain(result.source_name)
            if domain not in self.domains:
                continue
            text = _extract_text(result.data)
            hit_keywords = [kw for kw in self.keywords if kw.lower() in text.lower()]
            if hit_keywords:
                matching.append(result.source_name)
                excerpts.append(f"[{result.source_name}] {text[:120]}")

        if len(matching) < self.threshold:
            return None

        confidence = min(1.0, len(matching) / len(self.domains))
        return CorrelatedSignal(
            description=self.description,
            matching_sources=matching,
            confidence=confidence,
            domains=self.domains,
            raw_excerpt=" | ".join(excerpts[:3]),
        )


# ---------------------------------------------------------------------------
# Abstract base source
# ---------------------------------------------------------------------------


class OSINTSource(ABC):
    """Abstract base class for all OSINT sweep sources."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique source identifier."""

    @abstractmethod
    async def sweep(self, client: httpx.AsyncClient) -> SourceResult:
        """Perform the sweep and return a SourceResult.

        Args:
            client: Shared httpx.AsyncClient (caller owns lifecycle).

        Returns:
            SourceResult with populated data or failure details.
        """


# ---------------------------------------------------------------------------
# Built-in sources (no API key required)
# ---------------------------------------------------------------------------


class FREDSource(OSINTSource):
    """Federal Reserve Economic Data — FRED observations for a series.

    Docs: https://fred.stlouisfed.org/docs/api/fred/
    No API key required for the freely-available series endpoints.
    """

    # GDP growth (quarterly, SAAR) as a lightweight economic pulse signal
    _URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=A191RL1Q225SBEA&vintage_date="

    @property
    def name(self) -> str:
        return "fred_gdp"

    async def sweep(self, client: httpx.AsyncClient) -> SourceResult:
        start = time.monotonic()
        try:
            resp = await client.get(
                "https://fred.stlouisfed.org/graph/fredgraph.csv?id=A191RL1Q225SBEA",
                timeout=20.0,
            )
            resp.raise_for_status()
            lines = resp.text.strip().splitlines()
            # CSV: DATE,VALUE — take the last 4 rows (1 year of quarterly data)
            recent = [line for line in lines[1:] if line.strip()][-4:]
            parsed = []
            for row in recent:
                parts = row.split(",")
                if len(parts) == 2:
                    parsed.append({"date": parts[0].strip(), "gdp_growth_pct": parts[1].strip()})
            latency = time.monotonic() - start
            logger.info("FREDSource sweep succeeded: %d records", len(parsed))
            return SourceResult(source_name=self.name, data=parsed, latency_seconds=latency)
        except Exception as exc:
            latency = time.monotonic() - start
            logger.warning("FREDSource sweep failed: %s", exc)
            return SourceResult.failure(self.name, str(exc), latency)


class GDELTSource(OSINTSource):
    """GDELT Project — global news event stream (last 15 min, no key required).

    Docs: https://blog.gdeltproject.org/gdelt-2-0-our-global-world-in-realtime/
    Uses the GKG (Global Knowledge Graph) summary endpoint.
    """

    _URL = "https://data.gdeltproject.org/gdeltv2/lastupdate.txt"

    @property
    def name(self) -> str:
        return "gdelt_events"

    async def sweep(self, client: httpx.AsyncClient) -> SourceResult:
        start = time.monotonic()
        try:
            resp = await client.get(self._URL, timeout=20.0)
            resp.raise_for_status()
            # lastupdate.txt lines: "<bytes> <md5> <url>"
            lines = [line.strip() for line in resp.text.strip().splitlines() if line.strip()]
            urls = [line.split()[-1] for line in lines if line.split()]
            latency = time.monotonic() - start
            logger.info("GDELTSource sweep succeeded: %d dataset URLs", len(urls))
            return SourceResult(
                source_name=self.name,
                data={"latest_dataset_urls": urls, "record_count": len(lines)},
                latency_seconds=latency,
            )
        except Exception as exc:
            latency = time.monotonic() - start
            logger.warning("GDELTSource sweep failed: %s", exc)
            return SourceResult.failure(self.name, str(exc), latency)


class NASAFIRMSSource(OSINTSource):
    """NASA FIRMS — active fire/thermal anomaly counts via the public map API.

    Uses the worldview CSV summary (no key for aggregate counts).
    Docs: https://firms.modaps.eosdis.nasa.gov/api/
    """

    _URL = (
        "https://firms.modaps.eosdis.nasa.gov/api/country/csv"
        "/c3a9f14e93f0fb65b5e6e47f1d9b4f28/VIIRS_SNPP_NRT/World/1"
    )

    @property
    def name(self) -> str:
        return "nasa_firms_fire"

    async def sweep(self, client: httpx.AsyncClient) -> SourceResult:
        start = time.monotonic()
        try:
            resp = await client.get(self._URL, timeout=25.0)
            resp.raise_for_status()
            lines = resp.text.strip().splitlines()
            header = lines[0] if lines else ""
            fire_count = max(0, len(lines) - 1)
            latency = time.monotonic() - start
            logger.info("NASAFIRMSSource sweep: %d active fire detections", fire_count)
            return SourceResult(
                source_name=self.name,
                data={"active_fire_detections": fire_count, "fields": header},
                latency_seconds=latency,
            )
        except Exception as exc:
            latency = time.monotonic() - start
            logger.warning("NASAFIRMSSource sweep failed: %s", exc)
            return SourceResult.failure(self.name, str(exc), latency)


class NOAASource(OSINTSource):
    """NOAA Weather Alerts — active US NWS alerts via the public API (no key).

    Docs: https://www.weather.gov/documentation/services-web-api
    """

    _URL = "https://api.weather.gov/alerts/active?status=actual&message_type=alert"

    @property
    def name(self) -> str:
        return "noaa_weather_alerts"

    async def sweep(self, client: httpx.AsyncClient) -> SourceResult:
        start = time.monotonic()
        try:
            resp = await client.get(
                self._URL,
                headers={"Accept": "application/json", "User-Agent": "AutoBot/1.0"},
                timeout=20.0,
            )
            resp.raise_for_status()
            payload = resp.json()
            features = payload.get("features", [])
            # Extract lightweight summary: event type + area description
            alerts = [
                {
                    "event": f.get("properties", {}).get("event", ""),
                    "area": f.get("properties", {}).get("areaDesc", "")[:80],
                    "severity": f.get("properties", {}).get("severity", ""),
                }
                for f in features[:20]  # cap at 20 for Redis storage
            ]
            latency = time.monotonic() - start
            logger.info("NOAASource sweep: %d active alerts", len(features))
            return SourceResult(
                source_name=self.name,
                data={"total_alerts": len(features), "alerts": alerts},
                latency_seconds=latency,
            )
        except Exception as exc:
            latency = time.monotonic() - start
            logger.warning("NOAASource sweep failed: %s", exc)
            return SourceResult.failure(self.name, str(exc), latency)


# ---------------------------------------------------------------------------
# OSINT Engine
# ---------------------------------------------------------------------------


class OSINTEngine(AsyncRedisClientMixin):
    """Parallel OSINT intelligence sweep engine.

    Registers named sources, sweeps them concurrently with per-source timeout
    enforcement, caches results in Redis for RAG consumption, and runs
    correlation rules to detect cross-domain signal convergence.

    Usage::

        engine = OSINTEngine()
        engine.register_source(FREDSource())
        engine.register_source(NOAASource())
        results = await engine.sweep_all()
        signals = engine.correlate(results)
    """

    _REDIS_PREFIX = "osint"
    _RESULT_TTL = 3600  # 1 hour cache
    _redis_database = "main"

    def __init__(self) -> None:
        self._sources: Dict[str, OSINTSource] = {}
        self._rules: List[CorrelationRule] = []
        self._last_sweep: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_source(self, source: OSINTSource) -> None:
        """Register an OSINT source by its unique name."""
        if source.name in self._sources:
            logger.warning("OSINTEngine: replacing existing source '%s'", source.name)
        self._sources[source.name] = source
        logger.info("OSINTEngine: registered source '%s'", source.name)

    def register_rule(self, rule: CorrelationRule) -> None:
        """Register a correlation rule."""
        self._rules.append(rule)
        logger.info("OSINTEngine: registered correlation rule '%s'", rule.description)

    # ------------------------------------------------------------------
    # Sweep
    # ------------------------------------------------------------------

    async def sweep_all(self, timeout_per_source: float = 30.0) -> List[SourceResult]:
        """Run all registered sources in parallel with per-source timeout.

        Args:
            timeout_per_source: Seconds before an individual source is
                cancelled and a failure result is emitted.

        Returns:
            List of SourceResult — one per registered source, success or failure.
        """
        if not self._sources:
            logger.warning("OSINTEngine.sweep_all called with no registered sources")
            return []

        async with httpx.AsyncClient(follow_redirects=True) as client:
            tasks = [self._sweep_with_timeout(source, client, timeout_per_source) for source in self._sources.values()]
            results: List[SourceResult] = await asyncio.gather(*tasks, return_exceptions=False)

        await self._cache_results(results)
        logger.info(
            "OSINTEngine sweep complete: %d/%d sources succeeded",
            sum(1 for r in results if r.success),
            len(results),
        )
        return results

    async def _sweep_with_timeout(
        self,
        source: OSINTSource,
        client: httpx.AsyncClient,
        timeout: float,
    ) -> SourceResult:
        """Wrap a single source sweep with asyncio timeout handling."""
        start = time.monotonic()
        try:
            result = await asyncio.wait_for(source.sweep(client), timeout=timeout)
            self._last_sweep[source.name] = time.time()
            return result
        except asyncio.TimeoutError:
            latency = time.monotonic() - start
            logger.warning("OSINTEngine: source '%s' timed out after %.1fs", source.name, latency)
            return SourceResult.failure(
                source.name,
                f"Source timed out after {timeout}s",
                latency,
            )
        except Exception as exc:
            latency = time.monotonic() - start
            logger.exception("OSINTEngine: source '%s' raised exception", source.name)
            return SourceResult.failure(source.name, str(exc), latency)

    # ------------------------------------------------------------------
    # Correlation
    # ------------------------------------------------------------------

    def correlate(self, results: List[SourceResult]) -> List[CorrelatedSignal]:
        """Evaluate all registered correlation rules against sweep results.

        Args:
            results: Output from sweep_all().

        Returns:
            List of CorrelatedSignal for every rule that fired.
        """
        signals: List[CorrelatedSignal] = []
        for rule in self._rules:
            signal = rule.evaluate(results)
            if signal is not None:
                signals.append(signal)
                logger.info(
                    "CorrelationRule fired: '%s' (confidence=%.2f, sources=%s)",
                    signal.description,
                    signal.confidence,
                    signal.matching_sources,
                )
        return signals

    # ------------------------------------------------------------------
    # Source status
    # ------------------------------------------------------------------

    def get_source_status(self) -> Dict[str, Dict[str, Any]]:
        """Return health/last-run info for all registered sources.

        Returns:
            Dict mapping source_name → {"registered": bool, "last_sweep_at": float|None}
        """
        status: Dict[str, Dict[str, Any]] = {}
        for name in self._sources:
            status[name] = {
                "registered": True,
                "last_sweep_at": self._last_sweep.get(name),
            }
        return status

    # ------------------------------------------------------------------
    # Redis caching
    # ------------------------------------------------------------------

    async def _cache_results(self, results: List[SourceResult]) -> None:
        """Persist each SourceResult to Redis for RAG consumption."""
        try:
            redis = await self._get_redis()
            pipe = redis.pipeline()
            for result in results:
                key = f"{self._REDIS_PREFIX}:result:{result.source_name}"
                pipe.setex(key, self._RESULT_TTL, json.dumps(result.to_dict()))
            # Store sweep index with source names and sweep time
            index_key = f"{self._REDIS_PREFIX}:last_sweep"
            pipe.setex(
                index_key,
                self._RESULT_TTL,
                json.dumps(
                    {
                        "swept_at": time.time(),
                        "sources": [r.source_name for r in results],
                        "success_count": sum(1 for r in results if r.success),
                    }
                ),
            )
            await pipe.execute()
            logger.info("OSINTEngine: cached %d results in Redis", len(results))
        except Exception:
            logger.exception("OSINTEngine: failed to cache results in Redis")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _infer_domain(source_name: str) -> str:
    """Map a source name to a broad domain string for correlation matching."""
    _DOMAIN_MAP = {
        "fred_gdp": "economics",
        "gdelt_events": "geopolitics",
        "nasa_firms_fire": "environment",
        "noaa_weather_alerts": "environment",
    }
    return _DOMAIN_MAP.get(source_name, source_name)


def _extract_text(data: Any) -> str:
    """Best-effort text extraction from arbitrary data for keyword matching."""
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        return " ".join(str(v) for v in data.values())
    if isinstance(data, list):
        return " ".join(str(item) for item in data[:10])
    return str(data)


# ---------------------------------------------------------------------------
# Default engine factory
# ---------------------------------------------------------------------------


def build_default_engine() -> OSINTEngine:
    """Return an OSINTEngine pre-loaded with all built-in sources and rules.

    Issue #1949: This is the canonical entry point for production use.
    """
    engine = OSINTEngine()

    # Register built-in sources
    for source in (FREDSource(), GDELTSource(), NASAFIRMSSource(), NOAASource()):
        engine.register_source(source)

    # Register sample correlation rules
    engine.register_rule(
        CorrelationRule(
            domains=["environment", "geopolitics"],
            keywords=["fire", "wildfire", "disaster", "emergency", "extreme"],
            threshold=2,
            description="Concurrent environmental emergency + global event coverage",
        )
    )
    engine.register_rule(
        CorrelationRule(
            domains=["economics", "geopolitics"],
            keywords=["recession", "contraction", "conflict", "sanction", "crisis"],
            threshold=2,
            description="Economic contraction coinciding with geopolitical stress",
        )
    )

    return engine
