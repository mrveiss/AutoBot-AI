# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Onboarding Doctor (Issue #5061)

Hardware scan, service reachability checks, and LLM-tier recommendation
for the first-run onboarding wizard.

Public API:
    run_doctor() -> dict  — full async doctor report
    _hardware_scan() -> dict  — sync hardware metrics (testable without mocks)
    _recommend_tier(ram_gb, cpu_cores) -> str  — pure tier recommender

Also the production call site of ``startup_validator.validate_startup_dependencies``
(#13780) — see :func:`_validate_dependencies` for why it lives here and not in
the lifespan.
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

        from autobot_shared.http_client import get_http_client

        async with get_http_client().tracked_request(
            "GET", url, timeout=aiohttp.ClientTimeout(connect=timeout, total=timeout), suppress_error_log=True
        ) as resp:
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


async def _validate_dependencies() -> dict[str, Any]:
    """Run the startup dependency validator on demand, off the boot path (#13780).

    ``validate_startup_dependencies`` was complete and uncalled: :mod:`startup_validator`
    defined it, its own docstring showed it being awaited in app startup, and nothing
    in the tree awaited it. #13738 had already decided it must NOT go in the lifespan —
    steps 4 and 5 are live round trips, and making Ollama a boot dependency turns a
    degraded-capability condition into a refusal to start.

    This endpoint is where it belongs, and the choice is a measurement rather than a
    preference:

    * ``GET /api/onboarding/doctor`` is an **existing** deep-check endpoint, which is
      what #13780's last acceptance criterion asks for — no new health surface when one
      can host it. It is registered, authenticated, and invoked on demand by a human.
    * It already pays for a Redis ping and an Ollama ``/api/tags`` GET, so the two round
      trips #13738 refused to put in front of every boot are already paid on this path.
      They are **not free**: the validator runs its OWN Redis ping and its own Ollama
      GET (``startup_validator.py:334-338``, 5s timeout), so a ``/doctor`` call makes
      each round trip twice, sequentially. An earlier revision of this docstring
      claimed it "cost nothing new", which was wrong. The duplication is accepted
      because ``/doctor`` is an operator-invoked diagnostic and reading the validator's
      own view is the point of calling it — see the note at the ``dependencies`` key
      for the condition under which that should be revisited.
    * It is **not** the ``/api/system/health`` aggregator. That one is unauthenticated
      and polled by the frontend before login, so a 5-second Ollama timeout registered
      there would land on a hot public path — the precise cost #13780 rules out.
    * ``cli/doctor.py`` reads as the better name and is not the better home: nothing
      outside its own tests invokes it, so wiring a dormant function into a dormant CLI
      would leave the chain exactly as unreached as it started.

    The result is reported in full — ``errors``, ``warnings`` and ``details`` — rather
    than reduced to ``success``, because an operator asking "is this host wired
    correctly?" needs the failing name, not a boolean. A validator that raises is
    reported as a failed run with its exception type rather than taking the whole
    onboarding report down with it; every message the validator produces is already
    sanitised to a type name or a fixed string at its source.
    """
    try:
        from startup_validator import validate_startup_dependencies

        result = await validate_startup_dependencies()
    except Exception as exc:  # noqa: BLE001 — reported below, never discarded
        logger.error("Startup dependency validation could not run: %s", type(exc).__name__, exc_info=True)
        return {"ran": False, "failure": type(exc).__name__, "errors": [], "warnings": [], "details": {}}

    return {
        "ran": True,
        "success": result.success,
        "errors": list(result.errors),
        "warnings": list(result.warnings),
        "details": dict(result.details),
    }


async def run_doctor() -> dict[str, Any]:
    """
    Run the full onboarding doctor scan.

    Returns a structured dict with:
        hardware  — psutil metrics
        services  — reachability of Ollama, Redis, ChromaDB
        recommendation  — suggested LLM tier + preset
        dependencies  — startup dependency validation (#13780)
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
        # #13780: the startup validator's one production call site.
        #
        # Being last in this literal delays nothing: the dict is one response,
        # so the caller waits for this await regardless of where it sits. An
        # earlier revision of this comment claimed the opposite.
        #
        # It is not free, either. `validate_startup_dependencies` runs its OWN
        # Redis ping and its own Ollama `GET /api/tags` (startup_validator.py,
        # 5s timeout), and this handler has already probed both above -- so a
        # /doctor call pays each twice, sequentially. That is accepted here
        # because /doctor is an operator-invoked diagnostic, not a hot path,
        # and the duplicate probe is the honest reading of the validator's own
        # view rather than a cached one. Collapse the two only if /doctor ever
        # becomes something polled.
        "dependencies": await _validate_dependencies(),
    }
