# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Configuration Bootstrap Client for Windows NPU Worker

Fetches runtime configuration from the main AutoBot backend on startup.
This eliminates the need to hardcode credentials (Redis, etc.) in workers.

Issue #68: NPU worker configuration bootstrap
"""

import asyncio
import logging
import socket
from typing import Any, Dict

from utils.http_retry import aiohttp_with_backoff

logger = logging.getLogger(__name__)

# =============================================================================
# Constants (Issue #68 - Code smells fix: Extract magic numbers)
# Note: No hardcoded IPs - backend host comes from config/environment
# =============================================================================
DEFAULT_WORKER_PORT = 8082
DEFAULT_BOOTSTRAP_TIMEOUT = 10
DEFAULT_BOOTSTRAP_RETRIES = 3
LOCAL_IP_FALLBACK = "127.0.0.1"

# =============================================================================
# Thread-safe global state (Issue #68 - Race condition fix)
# =============================================================================
_bootstrap_lock = asyncio.Lock()
_bootstrap_config: Dict[str, Any] | None = None
_worker_id: str | None = None
_local_ip_cache: str | None = None  # Cache to avoid repeated socket calls


def get_local_ip(backend_host: str) -> str:
    """
    Get the local IP address that can reach the backend.

    Uses caching to avoid repeated socket operations (efficiency fix).

    Args:
        backend_host: Backend server hostname/IP

    Returns:
        Local IP address string
    """
    global _local_ip_cache

    # Return cached value if available (efficiency improvement)
    if _local_ip_cache is not None:
        return _local_ip_cache

    sock = None
    try:
        # Create UDP socket (doesn't actually send data)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect((backend_host, 80))
        local_ip = sock.getsockname()[0]
        _local_ip_cache = local_ip  # Cache the result
        return local_ip
    except Exception:
        return LOCAL_IP_FALLBACK
    finally:
        # Proper socket cleanup (Issue #68 - unclosed socket fix)
        if sock is not None:
            try:
                sock.close()
            except Exception:
                logger.debug("Suppressed exception in try block", exc_info=True)


async def fetch_bootstrap_config(
    backend_host: str,
    backend_port: int,
    worker_port: int = DEFAULT_WORKER_PORT,
    platform: str = "windows",
    timeout: int = DEFAULT_BOOTSTRAP_TIMEOUT,
    retries: int = DEFAULT_BOOTSTRAP_RETRIES,
    worker_id: str | None = None,
) -> Dict[str, Any] | None:
    """
    Fetch configuration from the backend bootstrap endpoint.

    Thread-safe with lock to prevent race conditions on global state.

    Issue #640: Pass existing worker_id to prevent duplicate registrations.
    If worker_id is provided, backend will reuse it instead of generating new.

    Args:
        backend_host: Backend server hostname/IP
        backend_port: Backend server port
        worker_port: This worker's port
        platform: Worker platform (windows, linux, macos)
        timeout: Request timeout in seconds
        retries: Number of retry attempts
        worker_id: Existing worker ID (if None, backend generates new)

    Returns:
        Configuration dictionary or None if failed
    """
    global _bootstrap_config, _worker_id

    # Fast path: check without lock first (double-check locking pattern)
    if _bootstrap_config is not None:
        return _bootstrap_config

    # Acquire lock for thread-safe initialization (Issue #68 - race condition fix)
    async with _bootstrap_lock:
        # Double-check after acquiring lock
        if _bootstrap_config is not None:
            return _bootstrap_config

        local_ip = get_local_ip(backend_host)
        worker_url = f"http://{local_ip}:{worker_port}"

        # Issue #640: Send existing worker_id to prevent duplicate registrations
        bootstrap_request = {
            "worker_id": worker_id if worker_id else "auto",
            "platform": platform,
            "url": worker_url,
            "capabilities": ["npu", "embeddings", "inference"],
        }

        backend_url = f"http://{backend_host}:{backend_port}/api/npu/workers/bootstrap"

        data = await aiohttp_with_backoff(
            backend_url,
            method="POST",
            json_body=bootstrap_request,
            max_attempts=retries,
            initial_delay=1.0,
            timeout_s=float(timeout),
            logger=logger,
        )

        if data is None:
            logger.error("Failed to fetch bootstrap config after %d attempts", retries)
            return None

        if data.get("success"):
            _bootstrap_config = data.get("config", {})
            _worker_id = data.get("worker_id")
            logger.info(
                "Bootstrap config received from %s - worker_id: %s",
                backend_url,
                _worker_id,
            )
            return _bootstrap_config

        logger.warning("Bootstrap failed: %s", data.get("message"))
        return None


# =============================================================================
# Fallback defaults for bootstrap config sections
# =============================================================================
DEFAULT_REDIS_CONFIG: Dict[str, Any] = {}
DEFAULT_BACKEND_CONFIG: Dict[str, Any] = {}
DEFAULT_MODELS_CONFIG: Dict[str, Any] = {
    "autoload_defaults": True,
    "default_embedding": "nomic-embed-text",
    "default_llm": "llama3.2:1b-instruct-q4_K_M",
}


def get_bootstrap_config_section(section: str, default: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Return the named section from the cached bootstrap config, or default.

    Args:
        section: Top-level key to look up in the cached bootstrap config.
        default: Fallback returned when bootstrap is unavailable or missing
            the section. An empty dict is used if ``default`` is ``None``.

    Returns:
        The section dict from bootstrap config, or the provided default.
    """
    if _bootstrap_config and section in _bootstrap_config:
        return _bootstrap_config[section]
    if default is None:
        return {}
    return default


def get_cached_config() -> Dict[str, Any] | None:
    """Get the cached bootstrap configuration."""
    return _bootstrap_config


def get_worker_id() -> str | None:
    """Get the assigned worker ID from bootstrap."""
    return _worker_id


def get_redis_config() -> Dict[str, Any]:
    """Get Redis configuration from bootstrap or fallback."""
    if not _bootstrap_config or "redis" not in _bootstrap_config:
        logger.warning("No bootstrap config available, Redis will not be configured")
    return get_bootstrap_config_section("redis", DEFAULT_REDIS_CONFIG)


def get_backend_config() -> Dict[str, Any]:
    """Get backend configuration from bootstrap or fallback.

    Note: No hardcoded IPs - backend config must come from YAML or bootstrap.
    """
    if not _bootstrap_config or "backend" not in _bootstrap_config:
        logger.warning("No bootstrap config available, using config from YAML file")
    return get_bootstrap_config_section("backend", DEFAULT_BACKEND_CONFIG)


def get_models_config() -> Dict[str, Any]:
    """Get models configuration from bootstrap or fallback."""
    return get_bootstrap_config_section("models", DEFAULT_MODELS_CONFIG)
