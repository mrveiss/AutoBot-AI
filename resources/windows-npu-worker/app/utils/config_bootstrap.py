# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
from typing import Any, Dict, Optional

import aiohttp

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
_bootstrap_config: Optional[Dict[str, Any]] = None
_worker_id: Optional[str] = None
_local_ip_cache: Optional[str] = None  # Cache to avoid repeated socket calls


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
                pass


async def fetch_bootstrap_config(
    backend_host: str,
    backend_port: int,
    worker_port: int = DEFAULT_WORKER_PORT,
    platform: str = "windows",
    timeout: int = DEFAULT_BOOTSTRAP_TIMEOUT,
    retries: int = DEFAULT_BOOTSTRAP_RETRIES,
    worker_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
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

        # Reuse single session for all retries (efficiency improvement)
        session_timeout = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(timeout=session_timeout) as session:
            for attempt in range(retries):
                try:
                    async with session.post(backend_url, json=bootstrap_request) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data.get("success"):
                                _bootstrap_config = data.get("config", {})
                                _worker_id = data.get("worker_id")
                                logger.info(
                                    "Bootstrap config received from %s - worker_id: %s",
                                    backend_url,
                                    _worker_id,
                                )
                                return _bootstrap_config
                            else:
                                logger.warning("Bootstrap failed: %s", data.get("message"))
                        else:
                            text = await response.text()
                            logger.warning(
                                "Bootstrap request failed: status=%d, response=%s",
                                response.status,
                                text[:200],
                            )

                except aiohttp.ClientConnectorError:
                    logger.warning(
                        "Cannot connect to backend at %s (attempt %d/%d)",
                        backend_url,
                        attempt + 1,
                        retries,
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "Bootstrap request timeout to %s (attempt %d/%d)",
                        backend_url,
                        attempt + 1,
                        retries,
                    )
                except Exception as e:
                    logger.error("Bootstrap error: %s", e)

                # Wait before retry (exponential backoff)
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)

        logger.error("Failed to fetch bootstrap config after %d attempts", retries)
        return None


def get_cached_config() -> Optional[Dict[str, Any]]:
    """Get the cached bootstrap configuration."""
    return _bootstrap_config


def get_worker_id() -> Optional[str]:
    """Get the assigned worker ID from bootstrap."""
    return _worker_id


def get_redis_config() -> Dict[str, Any]:
    """
    Get Redis configuration from bootstrap or fallback.

    Returns:
        Redis configuration dictionary
    """
    if _bootstrap_config and "redis" in _bootstrap_config:
        return _bootstrap_config["redis"]

    # Fallback - standalone mode (no Redis)
    logger.warning("No bootstrap config available, Redis will not be configured")
    return {}


def get_backend_config() -> Dict[str, Any]:
    """
    Get backend configuration from bootstrap or fallback.

    Note: No hardcoded IPs - backend config must come from YAML or bootstrap.

    Returns:
        Backend configuration dictionary (may be empty if not bootstrapped)
    """
    if _bootstrap_config and "backend" in _bootstrap_config:
        return _bootstrap_config["backend"]

    # No hardcoded fallbacks - return empty dict for standalone mode
    # Backend host/port must be in npu_worker.yaml config file
    logger.warning("No bootstrap config available, using config from YAML file")
    return {}


def get_models_config() -> Dict[str, Any]:
    """
    Get models configuration from bootstrap or fallback.

    Returns:
        Models configuration dictionary
    """
    if _bootstrap_config and "models" in _bootstrap_config:
        return _bootstrap_config["models"]

    # Fallback defaults
    return {
        "autoload_defaults": True,
        "default_embedding": "nomic-embed-text",
        "default_llm": "llama3.2:1b-instruct-q4_K_M",
    }
