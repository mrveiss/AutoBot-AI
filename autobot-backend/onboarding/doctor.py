# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Onboarding Doctor (Issue #5061)

Hardware scan, service reachability checks, and LLM-tier recommendation
for the first-run onboarding wizard.

Public API:
    run_doctor() -> dict  — full async doctor report
    _hardware_scan() -> dict  — sync hardware metrics (testable without mocks)
    _recommend_tier(ram_gb, cpu_cores) -> str  — pure tier recommender
"""

from __future__ import annotations

from typing import Any

import psutil

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config

logger = get_logger(__name__)

# LLM tier constants
TIER_POWERFUL = "powerful"
TIER_BALANCED = "balanced"
TIER_FAST = "fast"

# Tier thresholds (GiB RAM)
_POWERFUL_RAM_GIB = 24.0
_BALANCED_RAM_GIB = 8.0


def _hardware_scan() -> dict[str, Any]:
    """Collect RAM, disk, and CPU info via psutil (synchronous, no I/O)."""
    vmem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    cpu_cores: int = psutil.cpu_count(logical=True) or 1
    return {
        "ram_gb": round(vmem.total / (1024**3), 1),
        "ram_available_gb": round(vmem.available / (1024**3), 1),
        "disk_total_gb": round(disk.total / (1024**3), 1),
        "disk_free_gb": round(disk.free / (1024**3), 1),
        "cpu_cores": cpu_cores,
    }


def _recommend_tier(ram_gb: float, cpu_cores: int) -> str:
    """Return the recommended LLM tier based on available hardware."""
    if ram_gb >= _POWERFUL_RAM_GIB:
        return TIER_POWERFUL
    if ram_gb >= _BALANCED_RAM_GIB:
        return TIER_BALANCED
    return TIER_FAST


async def _probe_http(url: str, timeout: float = 3.0) -> tuple[bool, str]:
    """Attempt an HTTP GET to *url*; return (reachable, detail)."""
    try:
        import aiohttp  # optional dependency — graceful degradation if absent

        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(connect=timeout, total=timeout)) as resp:
                return (resp.status < 500, f"HTTP {resp.status}")
    except ImportError:
        return (False, "aiohttp not installed")
    except Exception as exc:  # noqa: BLE001
        return (False, str(exc))


async def _probe_redis() -> tuple[bool, str]:
    """Ping the main Redis instance via the shared async client."""
    try:
        from autobot_shared.redis_client import get_async_redis_client

        client = await get_async_redis_client(database="main")
        if client is None:
            return (False, "client unavailable")
        await client.ping()
        return (True, "PONG")
    except Exception as exc:  # noqa: BLE001
        return (False, str(exc))


async def run_doctor() -> dict[str, Any]:
    """
    Run the full onboarding doctor scan.

    Returns a structured dict with:
        hardware  — psutil metrics
        services  — reachability of Ollama, Redis, ChromaDB
        recommendation  — suggested LLM tier + preset
    """
    hardware = _hardware_scan()

    # Build service probe targets from env / defaults (no hardcoded IPs)
    ollama_base = config.ollama_url
    chromadb_host = config.vm.chromadb
    chromadb_port = config.port.chromadb

    ollama_reachable, ollama_detail = await _probe_http(f"{ollama_base}/api/tags")
    chromadb_reachable, chromadb_detail = await _probe_http(f"http://{chromadb_host}:{chromadb_port}/api/v1/heartbeat")
    redis_reachable, redis_detail = await _probe_redis()

    services = {
        "ollama": {"reachable": ollama_reachable, "detail": ollama_detail, "url": ollama_base},
        "redis": {"reachable": redis_reachable, "detail": redis_detail},
        "chromadb": {
            "reachable": chromadb_reachable,
            "detail": chromadb_detail,
            "url": f"http://{chromadb_host}:{chromadb_port}",
        },
    }

    tier = _recommend_tier(hardware["ram_gb"], hardware["cpu_cores"])

    # Suggest a starter preset based on tier
    tier_to_preset = {
        TIER_POWERFUL: "deep-research",
        TIER_BALANCED: "sysadmin-copilot",
        TIER_FAST: "chat-simple",
    }
    suggested_preset = tier_to_preset[tier]

    # Supplement provider recommendation text
    if ollama_reachable:
        provider_note = "Ollama detected — local models available without API keys."
    else:
        provider_note = "Ollama not detected — configure an API key for a cloud provider (OpenAI, Anthropic, etc.)."

    recommendation = {
        "llm_tier": tier,
        "suggested_preset": suggested_preset,
        "provider_note": provider_note,
    }

    return {
        "hardware": hardware,
        "services": services,
        "recommendation": recommendation,
    }
