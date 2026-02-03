# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Client for Backend Agent Configuration

This client communicates with the SLM (Service Lifecycle Manager) server
to fetch and cache agent LLM configurations. It provides:

1. In-memory caching with TTL to reduce network load
2. HTTP client for fetching configurations
3. WebSocket client for real-time configuration updates
4. Graceful fallback chain when SLM is unavailable

Fallback chain:
1. Cache (if not expired)
2. HTTP fetch from SLM
3. Default agent config from SLM
4. Hardcoded ultimate fallback

Related to Issue #760 Phase 2.
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional

import aiohttp
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

logger = logging.getLogger(__name__)

# Default SLM server URL (can be overridden via init)
DEFAULT_SLM_URL = "http://172.16.168.19:8000"

# Ultimate fallback configuration
ULTIMATE_FALLBACK_CONFIG = {
    "llm_provider": "ollama",
    "llm_endpoint": "http://localhost:11434",
    "llm_model": "mistral:7b-instruct",
    "llm_timeout": 30,
    "llm_temperature": 0.7,
    "llm_max_tokens": None,
    "llm_api_key": None,
}


@dataclass
class CacheEntry:
    """Cache entry with expiration tracking."""

    config: dict
    expires_at: float

    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        return time.time() > self.expires_at


class ServiceDiscoveryCache:
    """Cache for discovered service URLs with TTL."""

    def __init__(self, ttl_seconds: int = 60):
        """
        Initialize service discovery cache.

        Args:
            ttl_seconds: Time-to-live for cache entries (default: 60)
        """
        self._cache: Dict[str, CacheEntry] = {}
        self._ttl = ttl_seconds

    def get(self, service_name: str) -> Optional[str]:
        """
        Get cached URL for service.

        Args:
            service_name: Service identifier

        Returns:
            Cached URL or None if not found/expired
        """
        entry = self._cache.get(service_name)
        if entry and not entry.is_expired():
            logger.debug("Service discovery cache hit for %s", service_name)
            return entry.config.get("url")
        elif entry:
            logger.debug("Service discovery cache expired for %s", service_name)
            del self._cache[service_name]
        return None

    def set(self, service_name: str, discovery_data: dict) -> None:
        """
        Store discovery data in cache.

        Args:
            service_name: Service identifier
            discovery_data: Dict with url, healthy, etc.
        """
        expires_at = time.time() + self._ttl
        self._cache[service_name] = CacheEntry(
            config=discovery_data, expires_at=expires_at
        )
        logger.debug(
            "Cached service discovery for %s (TTL: %ds)", service_name, self._ttl
        )

    def clear(self) -> None:
        """Clear entire cache."""
        self._cache.clear()
        logger.debug("Cleared service discovery cache")


class ServiceNotConfiguredError(Exception):
    """Raised when a service is not configured in SLM or environment."""


# Service name to environment variable mapping
ENV_VAR_MAP = {
    "autobot-backend": "AUTOBOT_BACKEND_URL",
    "redis": "REDIS_URL",
    "ollama": "OLLAMA_URL",
    "slm-server": "SLM_URL",
    "npu-worker": "NPU_WORKER_URL",
    "ai-stack": "AI_STACK_URL",
    "browser-service": "BROWSER_SERVICE_URL",
}


class AgentConfigCache:
    """In-memory cache for agent configurations with TTL."""

    def __init__(self, ttl_seconds: int = 300):
        """
        Initialize cache with specified TTL.

        Args:
            ttl_seconds: Time-to-live for cache entries in seconds (default: 300)
        """
        self._cache: Dict[str, CacheEntry] = {}
        self._ttl = ttl_seconds
        self._default_config: Optional[dict] = None
        self._lock = asyncio.Lock()

    def get(self, agent_id: str) -> Optional[dict]:
        """
        Get cached config for agent.

        Args:
            agent_id: Agent identifier

        Returns:
            Cached config dict or None if not found/expired
        """
        entry = self._cache.get(agent_id)
        if entry and not entry.is_expired():
            logger.debug("Cache hit for agent %s", agent_id)
            return entry.config
        elif entry:
            logger.debug("Cache expired for agent %s", agent_id)
            del self._cache[agent_id]
        return None

    def set(self, agent_id: str, config: dict) -> None:
        """
        Store config in cache with TTL.

        Args:
            agent_id: Agent identifier
            config: Configuration dictionary
        """
        expires_at = time.time() + self._ttl
        self._cache[agent_id] = CacheEntry(config=config, expires_at=expires_at)
        logger.debug("Cached config for agent %s (TTL: %ds)", agent_id, self._ttl)

    def update(self, agent_id: str, config: dict) -> None:
        """
        Update existing cache entry (alias for set).

        Args:
            agent_id: Agent identifier
            config: Configuration dictionary
        """
        self.set(agent_id, config)

    def remove(self, agent_id: str) -> None:
        """
        Remove agent from cache.

        Args:
            agent_id: Agent identifier
        """
        if agent_id in self._cache:
            del self._cache[agent_id]
            logger.debug("Removed agent %s from cache", agent_id)

    def set_default(self, config: dict) -> None:
        """
        Set default agent configuration.

        Args:
            config: Default configuration dictionary
        """
        self._default_config = config
        logger.debug("Set default agent config")

    def get_default(self) -> Optional[dict]:
        """
        Get default agent configuration.

        Returns:
            Default config dict or None
        """
        return self._default_config

    def clear(self) -> None:
        """Clear entire cache."""
        self._cache.clear()
        self._default_config = None
        logger.debug("Cleared agent config cache")


class SLMClient:
    """HTTP and WebSocket client for SLM server communication."""

    def __init__(
        self,
        slm_url: str = DEFAULT_SLM_URL,
        auth_token: Optional[str] = None,
        cache_ttl: int = 300,
    ):
        """
        Initialize SLM client.

        Args:
            slm_url: Base URL of SLM server
            auth_token: Optional JWT token for authentication
            cache_ttl: Cache TTL in seconds (default: 300)
        """
        self.slm_url = slm_url.rstrip("/")
        self.auth_token = auth_token
        self.cache = AgentConfigCache(ttl_seconds=cache_ttl)

        # WebSocket state
        self._ws_task: Optional[asyncio.Task] = None
        self._ws_connected = False
        self._reconnect_delay = 1.0  # Start with 1 second
        self._max_reconnect_delay = 60.0  # Max 60 seconds
        self._callbacks: list[Callable] = []
        self._shutdown = False

        # HTTP session
        self._http_session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._http_session is None or self._http_session.closed:
            headers = {}
            if self.auth_token:
                headers["Authorization"] = f"Bearer {self.auth_token}"
            self._http_session = aiohttp.ClientSession(headers=headers)
        return self._http_session

    async def connect(self) -> None:
        """
        Connect to SLM server and start WebSocket listener.

        This method:
        1. Fetches all agents via HTTP
        2. Caches them
        3. Starts WebSocket connection for real-time updates
        """
        logger.info("Connecting to SLM server at %s", self.slm_url)

        # Fetch initial agent configs
        try:
            await self._fetch_all_agents()
        except Exception as e:
            logger.warning("Failed to fetch initial agents: %s", e)

        # Start WebSocket listener in background
        self._ws_task = asyncio.create_task(self._ws_listener())
        logger.info("SLM client connected and listening for updates")

    async def disconnect(self) -> None:
        """Disconnect from SLM server and cleanup resources."""
        logger.info("Disconnecting from SLM server")
        self._shutdown = True

        # Cancel WebSocket task
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass

        # Close HTTP session
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()

        logger.info("SLM client disconnected")

    async def _fetch_all_agents(self) -> None:
        """Fetch all agents from SLM and populate cache."""
        try:
            session = await self._get_session()
            url = f"{self.slm_url}/api/agents"

            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    agents = data.get("agents", [])

                    for agent in agents:
                        agent_id = agent.get("agent_id")
                        if agent_id:
                            # Store full agent config in cache
                            config = {
                                "llm_provider": agent.get("llm_provider"),
                                "llm_endpoint": agent.get("llm_endpoint"),
                                "llm_model": agent.get("llm_model"),
                                "llm_timeout": agent.get("llm_timeout", 30),
                                "llm_temperature": agent.get("llm_temperature", 0.7),
                                "llm_max_tokens": agent.get("llm_max_tokens"),
                            }
                            self.cache.set(agent_id, config)

                            # Store default agent config
                            if agent.get("is_default"):
                                self.cache.set_default(config)

                    logger.info("Cached %d agents from SLM", len(agents))
                else:
                    logger.error("Failed to fetch agents: HTTP %d", response.status)
        except Exception as e:
            logger.error("Error fetching agents: %s", e)
            raise

    async def _fetch_agent_llm_config(self, agent_id: str) -> Optional[dict]:
        """
        Fetch LLM config for specific agent via HTTP.

        Args:
            agent_id: Agent identifier

        Returns:
            Config dict or None on failure
        """
        try:
            session = await self._get_session()
            url = f"{self.slm_url}/api/agents/{agent_id}/llm"

            async with session.get(url) as response:
                if response.status == 200:
                    config = await response.json()
                    logger.debug("Fetched LLM config for agent %s", agent_id)
                    return config
                elif response.status == 404:
                    logger.warning("Agent %s not found in SLM", agent_id)
                    return None
                else:
                    logger.error(
                        "Failed to fetch agent %s config: HTTP %d",
                        agent_id,
                        response.status,
                    )
                    return None
        except Exception as e:
            logger.error("Error fetching agent %s config: %s", agent_id, e)
            return None

    async def get_agent_config(self, agent_id: str) -> dict:
        """
        Get agent configuration with fallback chain.

        Fallback order:
        1. Cache (if not expired)
        2. HTTP fetch from SLM
        3. Default agent config from cache
        4. Ultimate hardcoded fallback

        Args:
            agent_id: Agent identifier

        Returns:
            Configuration dictionary (never None)
        """
        # Try cache first
        cached = self.cache.get(agent_id)
        if cached:
            return cached

        # Try fetching from SLM
        fetched = await self._fetch_agent_llm_config(agent_id)
        if fetched:
            self.cache.set(agent_id, fetched)
            return fetched

        # Try default agent config
        default = self.cache.get_default()
        if default:
            logger.warning("Agent %s not found, using default config", agent_id)
            return default

        # Ultimate fallback
        logger.warning(
            "Agent %s not found and no default, using hardcoded fallback",
            agent_id,
        )
        return ULTIMATE_FALLBACK_CONFIG.copy()

    def on_config_change(self, callback: Callable[[str, dict], None]) -> None:
        """
        Register callback for config change events.

        Callback signature: callback(agent_id: str, config: dict)

        Args:
            callback: Function to call when config changes
        """
        self._callbacks.append(callback)
        logger.debug("Registered config change callback")

    async def _notify_callbacks(self, agent_id: str, config: dict) -> None:
        """Notify all registered callbacks of config change."""
        for callback in self._callbacks:
            try:
                result = callback(agent_id, config)
                # Support both sync and async callbacks
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error("Error in config change callback: %s", e)

    async def _ws_listener(self) -> None:
        """Background task that maintains WebSocket connection."""
        while not self._shutdown:
            try:
                await self._ws_connect_and_listen()
            except asyncio.CancelledError:
                logger.debug("WebSocket listener cancelled")
                break
            except Exception as e:
                logger.error("WebSocket listener error: %s", e)

            if not self._shutdown:
                # Exponential backoff for reconnection
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2, self._max_reconnect_delay
                )
                logger.info("Reconnecting to WebSocket in %.1fs", self._reconnect_delay)

    async def _ws_connect_and_listen(self) -> None:
        """Connect to WebSocket and listen for events."""
        ws_url = self.slm_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/api/ws/events"

        logger.info("Connecting to WebSocket at %s", ws_url)

        try:
            async with websockets.connect(
                ws_url,
                extra_headers=(
                    {"Authorization": f"Bearer {self.auth_token}"}
                    if self.auth_token
                    else {}
                ),
            ) as websocket:
                self._ws_connected = True
                self._reconnect_delay = 1.0  # Reset backoff on successful connect
                logger.info("WebSocket connected")

                async for message in websocket:
                    if self._shutdown:
                        break

                    try:
                        import json

                        data = json.loads(message)
                        await self._handle_ws_message(data)
                    except Exception as e:
                        logger.error("Error handling WebSocket message: %s", e)

        except ConnectionClosed:
            logger.warning("WebSocket connection closed")
            self._ws_connected = False
        except WebSocketException as e:
            logger.error("WebSocket error: %s", e)
            self._ws_connected = False
        except Exception as e:
            logger.error("Unexpected WebSocket error: %s", e)
            self._ws_connected = False

    async def _handle_ws_message(self, data: dict) -> None:
        """
        Handle incoming WebSocket message.

        Message types:
        - agent_config_changed: Agent config updated
        - agent_created: New agent created
        - agent_deleted: Agent deleted

        Args:
            data: Message data dictionary
        """
        msg_type = data.get("type")
        msg_data = data.get("data", {})

        if msg_type == "agent_config_changed":
            agent_id = msg_data.get("agent_id")
            if agent_id:
                logger.info("Agent config changed: %s", agent_id)
                # Fetch fresh config and update cache
                config = await self._fetch_agent_llm_config(agent_id)
                if config:
                    self.cache.update(agent_id, config)
                    await self._notify_callbacks(agent_id, config)

        elif msg_type == "agent_created":
            agent_id = msg_data.get("agent_id")
            if agent_id:
                logger.info("New agent created: %s", agent_id)
                # Fetch and cache new agent
                config = await self._fetch_agent_llm_config(agent_id)
                if config:
                    self.cache.set(agent_id, config)
                    await self._notify_callbacks(agent_id, config)

        elif msg_type == "agent_deleted":
            agent_id = msg_data.get("agent_id")
            if agent_id:
                logger.info("Agent deleted: %s", agent_id)
                self.cache.remove(agent_id)

        elif msg_type == "ping":
            # Keepalive ping - ignore
            pass

        elif msg_type == "connected":
            logger.debug("WebSocket connection confirmed")

        else:
            logger.debug("Ignoring WebSocket message type: %s", msg_type)

    def is_connected(self) -> bool:
        """
        Check if WebSocket is currently connected.

        Returns:
            True if connected, False otherwise
        """
        return self._ws_connected


# Module-level singleton instance
_slm_client: Optional[SLMClient] = None

# Module-level service discovery cache
_discovery_cache = ServiceDiscoveryCache(ttl_seconds=60)


def get_slm_client() -> Optional[SLMClient]:
    """
    Get the global SLM client instance.

    Returns:
        SLMClient instance or None if not initialized
    """
    return _slm_client


async def init_slm_client(
    slm_url: str = DEFAULT_SLM_URL,
    auth_token: Optional[str] = None,
    cache_ttl: int = 300,
) -> SLMClient:
    """
    Initialize global SLM client.

    Args:
        slm_url: Base URL of SLM server
        auth_token: Optional JWT token for authentication
        cache_ttl: Cache TTL in seconds

    Returns:
        Initialized SLMClient instance
    """
    global _slm_client

    if _slm_client:
        logger.warning("SLM client already initialized, disconnecting old instance")
        await _slm_client.disconnect()

    _slm_client = SLMClient(slm_url=slm_url, auth_token=auth_token, cache_ttl=cache_ttl)
    await _slm_client.connect()
    logger.info("SLM client initialized and connected")

    return _slm_client


async def shutdown_slm_client() -> None:
    """Shutdown and cleanup global SLM client."""
    global _slm_client

    if _slm_client:
        await _slm_client.disconnect()
        _slm_client = None
        logger.info("SLM client shutdown complete")


# =============================================================================
# Service Discovery Functions (Issue #760 Phase 3)
# =============================================================================


async def _fetch_from_slm(service_name: str) -> Optional[str]:
    """
    Fetch service URL from SLM discovery API.

    Args:
        service_name: Service identifier

    Returns:
        Service URL or None on failure
    """
    client = get_slm_client()
    if not client:
        logger.debug("SLM client not initialized, cannot discover %s", service_name)
        return None

    try:
        session = await client._get_session()
        url = f"{client.slm_url}/api/discover/{service_name}"

        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                return data.get("url")
            elif response.status == 404:
                logger.debug("Service %s not found in SLM", service_name)
            else:
                logger.warning(
                    "SLM discovery failed for %s: HTTP %d",
                    service_name,
                    response.status,
                )
    except Exception as e:
        logger.warning("Error discovering service %s from SLM: %s", service_name, e)

    return None


def _get_env_fallback(service_name: str) -> Optional[str]:
    """
    Get service URL from environment variable.

    Args:
        service_name: Service identifier

    Returns:
        URL from environment or None
    """
    env_var = ENV_VAR_MAP.get(service_name)
    if env_var:
        return os.environ.get(env_var)
    return None


async def discover_service(service_name: str) -> str:
    """
    Discover service URL with fallback chain.

    Fallback order:
    1. Cache (60s TTL)
    2. SLM /api/discover/{service_name}
    3. Environment variable
    4. Error (service must be configured)

    Args:
        service_name: Service identifier

    Returns:
        Service URL

    Raises:
        ServiceNotConfiguredError: When service not found anywhere
    """
    # 1. Check cache
    cached = _discovery_cache.get(service_name)
    if cached:
        return cached

    # 2. Try SLM
    url = await _fetch_from_slm(service_name)
    if url:
        _discovery_cache.set(service_name, {"url": url})
        return url

    # 3. Env var fallback
    env_url = _get_env_fallback(service_name)
    if env_url:
        logger.info(
            "Service %s discovered via env var fallback: %s",
            service_name,
            ENV_VAR_MAP.get(service_name),
        )
        return env_url

    # 4. Error - not configured
    raise ServiceNotConfiguredError(
        f"Service '{service_name}' not found in SLM or environment"
    )
