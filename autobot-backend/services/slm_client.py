# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
import os
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable, Dict

import aiohttp
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from autobot_shared.auth.jwt_core import encode_jwt
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from constants.ttl_constants import TTL_5_MINUTES

logger = get_logger(__name__)

# TTL for minted service JWTs — short enough to limit exposure, long enough to
# survive a container restart followed by SLM reconnect backoff (max 60 s).
_SERVICE_JWT_TTL_HOURS: float = 1.0


def _get_slm_signing_secret() -> str | None:
    """Return the shared HS256 secret used to sign service JWTs for the SLM.

    Priority mirrors auth_middleware._get_jwt_secret:
    1. AUTOBOT_JWT_SECRET
    2. SECRET_KEY

    Returns None when neither is set (compose deployment not yet initialised
    or operator deliberately cleared the vars).
    """
    secret = config.jwt_secret or config.secret_key
    return secret if secret else None


def _mint_service_jwt(secret: str) -> str:
    """Mint a short-lived HS256 service JWT accepted by the SLM's auth_service.

    The SLM's ``auth_service.decode_token`` calls ``decode_jwt_or_none(token,
    settings.secret_key)``, which requires a structurally valid, non-expired
    HS256 token signed with ``SLM_SECRET_KEY``.  The ``with-secrets.sh``
    entrypoint now maps ``SLM_SECRET_KEY`` from the same ``_GEN_SECRET_KEY``
    value as ``SECRET_KEY`` / ``AUTOBOT_JWT_SECRET``, so the key is shared
    across the backend and SLM containers (GH#9852, GH#9905).

    Claims mirror the user-token shape produced by
    ``AuthService.create_token_response`` so no special-casing is needed in
    the SLM WebSocket handler.  The ``sub`` identifies the calling service.

    Transport note: the existing ``_ws_connect_and_listen`` passes the token
    via ``?token=`` query param, matching the ``_extract_ws_token`` fallback
    in the SLM's websocket.py.  Moving to the ``Sec-WebSocket-Protocol``
    subprotocol header (the preferred path per project memory) is out of scope
    for this fix (#9852) and is tracked separately.

    Args:
        secret: Shared HS256 signing secret (``AUTOBOT_JWT_SECRET`` /
            ``SECRET_KEY`` / ``SLM_SECRET_KEY``).

    Returns:
        Signed JWT string, valid for ``_SERVICE_JWT_TTL_HOURS`` hours.
    """
    return encode_jwt(
        {
            "sub": "service:backend",
            "admin": True,
            "role": "admin",
            "service": True,
        },
        secret=secret,
        expiry_hours=_SERVICE_JWT_TTL_HOURS,
    )

# SLM server URL from environment.  On co-located deployments (backend and SLM
# share the same host) the env var is often not set, so default to localhost.
# An explicit env var always wins.
_COLOCATED_DEFAULT = "http://127.0.0.1:8000"
DEFAULT_SLM_URL: str = config.slm_url or _COLOCATED_DEFAULT

# Warn at most once per process — the module is imported by several packages
# simultaneously, which previously caused the same warning to fire 3×.
_slm_url_warned: bool = False


def _warn_slm_url_once(url: str) -> None:
    """Emit the SLM_URL diagnostic warning exactly once per process."""
    global _slm_url_warned
    if _slm_url_warned:
        return
    _slm_url_warned = True
    if not config.slm_url:
        logger.warning(
            "SLM_URL not set — defaulting to co-located address %s. "
            "Set SLM_URL explicitly for non-co-located deployments.",
            url,
        )


# Ultimate fallback configuration (uses env vars where available)
ULTIMATE_FALLBACK_CONFIG = {
    "llm_provider": config.llm_provider,
    "llm_endpoint": config.ollama_url,
    "llm_model": config.default_llm_model,
    "llm_timeout": int(config.llm_timeout),
    "llm_temperature": float(config.llm_temperature),
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

    def __init__(self, ttl_seconds: int = 60) -> None:
        """
        Initialize service discovery cache.

        Args:
            ttl_seconds: Time-to-live for cache entries (default: 60)
        """
        self._cache: Dict[str, CacheEntry] = {}
        self._ttl = ttl_seconds

    def get(self, service_name: str) -> str | None:
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
        self._cache[service_name] = CacheEntry(config=discovery_data, expires_at=expires_at)
        logger.debug("Cached service discovery for %s (TTL: %ds)", service_name, self._ttl)

    def clear(self) -> None:
        """Clear entire cache."""
        self._cache.clear()
        logger.debug("Cleared service discovery cache")


# #6702: SSL context creation moved to autobot_shared/tls.py — single canonical
# implementation shared across slm_client, dag_executor, celery_app, and
# notification_service. Re-exported here for one-cycle backward compatibility.
from autobot_shared.tls import get_internal_tls_context as _create_permissive_ssl_context


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

    def __init__(self, ttl_seconds: int = TTL_5_MINUTES) -> None:
        """
        Initialize cache with specified TTL.

        Args:
            ttl_seconds: Time-to-live for cache entries in seconds (default: 300)
        """
        self._cache: Dict[str, CacheEntry] = {}
        self._ttl = ttl_seconds
        self._default_config: dict | None = None
        self._lock = asyncio.Lock()

    def get(self, agent_id: str) -> dict | None:
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

    def get_default(self) -> dict | None:
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
        auth_token: str | None = None,
        cache_ttl: int = TTL_5_MINUTES,
    ) -> None:
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
        self._ws_task: asyncio.Task | None = None
        self._ws_connected = False
        self._reconnect_delay = 1.0  # Start with 1 second
        self._max_reconnect_delay = 60.0  # Max 60 seconds
        self._callbacks: list[Callable] = []
        self._shutdown = False

        # HTTP session
        self._http_session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._http_session is None or self._http_session.closed:
            headers = {}
            if self.auth_token:
                headers["Authorization"] = f"Bearer {self.auth_token}"
            # Accept self-signed certs for internal HTTPS (#1048, #6654)
            connector = aiohttp.TCPConnector(ssl=_create_permissive_ssl_context(self.slm_url))
            self._http_session = aiohttp.ClientSession(headers=headers, connector=connector)
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

    async def _fetch_agent_llm_config(self, agent_id: str) -> dict | None:
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
                self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)
                logger.info("Reconnecting to WebSocket in %.1fs", self._reconnect_delay)

    async def _ws_connect_and_listen(self) -> None:
        """Connect to WebSocket and listen for events."""
        ws_url = self.slm_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/api/ws/events"

        # Resolve the auth token for this connection attempt.
        # Operator-provided SLM_AUTH_TOKEN takes precedence; when absent, mint a
        # short-lived service JWT from the shared HS256 secret so the SLM's
        # auth_service.decode_token can verify it (GH#9852).
        # A fresh token is minted on every reconnect so an expired token never
        # causes a permanent authentication failure.
        token = self.auth_token
        if not token:
            secret = _get_slm_signing_secret()
            if secret:
                token = _mint_service_jwt(secret)
                logger.debug("Minted service JWT for SLM WebSocket connection")
            else:
                logger.warning(
                    "No SLM auth token and no signing secret available "
                    "(AUTOBOT_JWT_SECRET / SECRET_KEY unset); "
                    "skipping WebSocket connection to SLM"
                )
                return

        # SLM backend authenticates via ?token= query param, not Authorization
        # header (#6839).  The preferred Sec-WebSocket-Protocol subprotocol path
        # is tracked as a follow-up (see project memory: WebSocket JWT must NOT
        # go in URL).
        ws_url = f"{ws_url}?token={token}"

        logger.info("Connecting to WebSocket at %s", ws_url.split("?")[0])  # don't log token

        try:
            # Accept self-signed certs for wss:// connections (#1048, #6654)
            ws_ssl = _create_permissive_ssl_context(ws_url) if ws_url.startswith("wss://") else None
            async with websockets.connect(
                ws_url,
                ssl=ws_ssl,
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

    # -------------------------------------------------------------------------
    # Deployment API methods (Issue #3407)
    # -------------------------------------------------------------------------

    async def create_deployment(self, payload: dict) -> dict:
        """
        Create a new deployment via POST /api/deployments.

        Args:
            payload: Dict with node_id, roles, and optional extra_data.

        Returns:
            Raw SLM response dict with deployment_id, node_id, status, etc.

        Raises:
            aiohttp.ClientResponseError: On non-2xx HTTP responses.
        """
        session = await self._get_session()
        url = f"{self.slm_url}/api/deployments"
        async with session.post(url, json=payload) as response:
            response.raise_for_status()
            data = await response.json()
        logger.info(
            "SLM deployment created: %s on node %s",
            data.get("deployment_id"),
            data.get("node_id"),
        )
        return data

    async def get_deployment(self, deployment_id: str) -> dict:
        """
        Fetch a deployment by ID via GET /api/deployments/{deployment_id}.

        Args:
            deployment_id: SLM deployment identifier.

        Returns:
            Raw SLM response dict.

        Raises:
            aiohttp.ClientResponseError: On non-2xx HTTP responses.
        """
        session = await self._get_session()
        url = f"{self.slm_url}/api/deployments/{deployment_id}"
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.json()

    async def list_deployments(self, node_id: str | None = None) -> dict:
        """
        List deployments via GET /api/deployments, optionally filtered by node.

        Args:
            node_id: Optional node identifier filter.

        Returns:
            Raw SLM response dict with a ``deployments`` key.

        Raises:
            aiohttp.ClientResponseError: On non-2xx HTTP responses.
        """
        session = await self._get_session()
        params = {}
        if node_id is not None:
            params["node_id"] = node_id
        url = f"{self.slm_url}/api/deployments"
        async with session.get(url, params=params) as response:
            response.raise_for_status()
            return await response.json()


# Module-level singleton instance
_slm_client: SLMClient | None = None

# Module-level service discovery cache
_discovery_cache = ServiceDiscoveryCache(ttl_seconds=60)


def get_slm_client() -> SLMClient | None:
    """
    Get the global SLM client instance.

    Returns:
        SLMClient instance or None if not initialized
    """
    return _slm_client


async def init_slm_client(
    slm_url: str = DEFAULT_SLM_URL,
    auth_token: str | None = None,
    cache_ttl: int = TTL_5_MINUTES,
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

    _warn_slm_url_once(slm_url)

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


async def _fetch_from_slm(service_name: str) -> str | None:
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


def _get_env_fallback(service_name: str) -> str | None:
    """
    Get service URL from environment variable.

    Args:
        service_name: Service identifier

    Returns:
        URL from environment or None
    """
    env_var = ENV_VAR_MAP.get(service_name)
    if env_var:
        return os.environ.get(env_var)  # ssot-config-exempt: dynamic env var name
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
    raise ServiceNotConfiguredError(f"Service '{service_name}' not found in SLM or environment")
