# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Pipeline Profiler — measure stage-by-stage latency in async pipelines.

Inspired by flash-moe's per-layer timing breakdown (4.28ms avg, 6 stages).

Usage:
    profiler = PipelineProfiler("rag-pipeline")
    async with profiler.stage("embedding"):
        embedding = await generate_embedding(query)
    async with profiler.stage("retrieval"):
        results = await chromadb.query(embedding)
    profiler.log_report()
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


class PipelineProfiler:
    """Profile async pipeline stages with precise timing."""

    def __init__(self, name: str):
        self._name = name
        self._stages: Dict[str, Dict[str, Any]] = {}
        self._order: List[str] = []

    @asynccontextmanager
    async def stage(self, name: str):
        """Time a pipeline stage as an async context manager."""
        start = time.perf_counter_ns()
        error_msg = None
        try:
            yield
        except Exception as e:
            error_msg = str(e)
            raise
        finally:
            elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
            entry: Dict[str, Any] = {"duration_ms": elapsed_ms}
            if error_msg:
                entry["error"] = error_msg
            self._stages[name] = entry
            self._order.append(name)

    def report(self) -> Dict[str, Any]:
        """Generate timing report for all recorded stages."""
        total = sum(s["duration_ms"] for s in self._stages.values())
        return {
            "pipeline": self._name,
            "stages": dict(self._stages),
            "stage_order": list(self._order),
            "total_ms": total,
        }

    def log_report(self, level: int = logging.INFO) -> None:
        """Log the timing report."""
        r = self.report()
        parts = [f"{self._name}: {r['total_ms']:.1f}ms total"]
        for name in self._order:
            stg = self._stages[name]
            parts.append(f"  {name}: {stg['duration_ms']:.1f}ms")
        logger.log(level, " | ".join(parts))
