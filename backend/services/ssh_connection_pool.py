"""
SSH Connection Pool Implementation
Manages SSH connections to multiple hosts with connection pooling and health monitoring

Features:
- Connection pooling (max 5 connections per host)
- Connection reuse and lifecycle management
- Health checks (60s intervals)
- Timeouts (300s idle, 30s connect)
- Exponential backoff retry logic
- Graceful connection cleanup
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

import paramiko

from src.constants.network_constants import NetworkConstants

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """SSH connection states"""

    IDLE = "idle"
    ACTIVE = "active"
    UNHEALTHY = "unhealthy"
    CLOSED = "closed"


@dataclass
class SSHConnection:
    """Represents a single SSH connection in the pool"""

    client: paramiko.SSHClient
    host: str
    port: int
    username: str
    state: ConnectionState
    created_at: datetime
    last_used: datetime
    last_health_check: datetime
    use_count: int

    def is_idle_timeout(self, idle_timeout: int = 300) -> bool:
        """Check if connection has exceeded idle timeout"""
        idle_seconds = (datetime.now() - self.last_used).total_seconds()
        return idle_seconds > idle_timeout

    def needs_health_check(self, check_interval: int = 60) -> bool:
        """Check if connection needs health check"""
        seconds_since_check = (datetime.now() - self.last_health_check).total_seconds()
        return seconds_since_check > check_interval


class SSHConnectionPool:
    """
    Manages a pool of SSH connections to multiple hosts

    Features:
    - Max 5 connections per host
    - Connection reuse
    - Health monitoring
    - Timeout management
    - Graceful cleanup
    """

    def __init__(
        self,
        max_connections_per_host: int = 5,
        connect_timeout: int = 30,
        idle_timeout: int = 300,
        health_check_interval: int = 60,
        retry_max_attempts: int = 3,
        retry_base_delay: float = 1.0,
    ):
        """
        Initialize SSH connection pool

        Args:
            max_connections_per_host: Maximum connections per host (default: 5)
            connect_timeout: Connection timeout in seconds (default: 30)
            idle_timeout: Idle connection timeout in seconds (default: 300)
            health_check_interval: Health check interval in seconds (default: 60)
            retry_max_attempts: Maximum retry attempts for failed connections (default: 3)
            retry_base_delay: Base delay for exponential backoff in seconds (default: 1.0)
        """
        self.max_connections_per_host = max_connections_per_host
        self.connect_timeout = connect_timeout
        self.idle_timeout = idle_timeout
        self.health_check_interval = health_check_interval
        self.retry_max_attempts = retry_max_attempts
        self.retry_base_delay = retry_base_delay

        # Connection pools per host
        self.pools: Dict[str, List[SSHConnection]] = {}

        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

        # Health check task
        self._health_check_task: Optional[asyncio.Task] = None
        self._running = False

        logger.info(
            f"SSH connection pool initialized: max_per_host={max_connections_per_host}, "
            f"connect_timeout={connect_timeout}s, idle_timeout={idle_timeout}s"
        )

    async def start(self):
        """Start the connection pool and health monitoring"""
        if self._running:
            logger.warning("Connection pool already running")
            return

        self._running = True
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        logger.info("SSH connection pool started with health monitoring")

    async def stop(self):
        """Stop the connection pool and cleanup all connections"""
        self._running = False

        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        await self.cleanup_all()
        logger.info("SSH connection pool stopped")

    def _get_pool_key(self, host: str, port: int, username: str) -> str:
        """Generate unique key for host connection pool"""
        return f"{username}@{host}:{port}"

    async def get_connection(
        self,
        host: str,
        port: int = 22,
        username: str = "autobot",
        key_path: str = "~/.ssh/autobot_key",
        passphrase: Optional[str] = None,
    ) -> paramiko.SSHClient:
        """
        Get an SSH connection from the pool

        Args:
            host: Target host IP or hostname
            port: SSH port (default: 22)
            username: SSH username (default: autobot)
            key_path: Path to SSH private key (default: ~/.ssh/autobot_key)
            passphrase: Key passphrase if needed (default: None)

        Returns:
            paramiko.SSHClient instance ready for use

        Raises:
            ConnectionError: If connection cannot be established
        """
        pool_key = self._get_pool_key(host, port, username)

        async with self._lock:
            # Initialize pool for this host if needed
            if pool_key not in self.pools:
                self.pools[pool_key] = []

            pool = self.pools[pool_key]

            # Try to find an idle, healthy connection
            for conn in pool:
                if conn.state == ConnectionState.IDLE:
                    # Check if connection is still healthy
                    if await self._check_connection_health(conn):
                        conn.state = ConnectionState.ACTIVE
                        conn.last_used = datetime.now()
                        conn.use_count += 1
                        logger.debug(
                            f"Reusing connection to {pool_key} "
                            f"(use_count={conn.use_count})"
                        )
                        return conn.client
                    else:
                        # Connection unhealthy, mark for cleanup
                        conn.state = ConnectionState.UNHEALTHY

            # No idle connection available, create new if under limit
            if (
                len([c for c in pool if c.state != ConnectionState.CLOSED])
                < self.max_connections_per_host
            ):
                client = await self._create_connection(
                    host, port, username, key_path, passphrase
                )

                conn = SSHConnection(
                    client=client,
                    host=host,
                    port=port,
                    username=username,
                    state=ConnectionState.ACTIVE,
                    created_at=datetime.now(),
                    last_used=datetime.now(),
                    last_health_check=datetime.now(),
                    use_count=1,
                )
                pool.append(conn)

                logger.info(
                    f"Created new SSH connection to {pool_key} "
                    f"(pool_size={len(pool)})"
                )
                return client

            # Pool exhausted, wait and retry
            logger.warning(
                f"Connection pool exhausted for {pool_key}, "
                f"max={self.max_connections_per_host}"
            )
            raise ConnectionError(
                f"Connection pool exhausted for {pool_key}. "
                f"Maximum {self.max_connections_per_host} connections allowed."
            )

    async def release_connection(
        self,
        client: paramiko.SSHClient,
        host: str,
        port: int = 22,
        username: str = "autobot",
    ):
        """
        Release a connection back to the pool

        Args:
            client: SSH client to release
            host: Target host
            port: SSH port (default: 22)
            username: SSH username (default: autobot)
        """
        pool_key = self._get_pool_key(host, port, username)

        async with self._lock:
            if pool_key not in self.pools:
                logger.warning(
                    f"Attempted to release connection for unknown pool {pool_key}"
                )
                return

            pool = self.pools[pool_key]
            for conn in pool:
                if conn.client == client and conn.state == ConnectionState.ACTIVE:
                    conn.state = ConnectionState.IDLE
                    conn.last_used = datetime.now()
                    logger.debug(f"Released connection to {pool_key} back to pool")
                    return

            logger.warning(f"Connection not found in pool {pool_key}")

    async def _create_connection(
        self,
        host: str,
        port: int,
        username: str,
        key_path: str,
        passphrase: Optional[str],
    ) -> paramiko.SSHClient:
        """
        Create a new SSH connection with retry logic

        Args:
            host: Target host
            port: SSH port
            username: SSH username
            key_path: Path to SSH private key
            passphrase: Key passphrase if needed

        Returns:
            paramiko.SSHClient instance

        Raises:
            ConnectionError: If connection fails after retries
        """
        last_error = None

        for attempt in range(self.retry_max_attempts):
            try:
                client = paramiko.SSHClient()

                # Load host keys for security
                client.load_system_host_keys()
                # Auto-add new hosts (consider security implications)
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

                # Load private key
                key_path_expanded = os.path.expanduser(key_path)
                if not os.path.exists(key_path_expanded):
                    raise FileNotFoundError(f"SSH key not found: {key_path_expanded}")

                private_key = paramiko.RSAKey.from_private_key_file(
                    key_path_expanded, password=passphrase
                )

                # Connect with timeout
                logger.debug(
                    f"Connecting to {username}@{host}:{port} "
                    f"(attempt {attempt + 1}/{self.retry_max_attempts})"
                )

                client.connect(
                    hostname=host,
                    port=port,
                    username=username,
                    pkey=private_key,
                    timeout=self.connect_timeout,
                    allow_agent=False,
                    look_for_keys=False,
                )

                logger.info(f"SSH connection established to {username}@{host}:{port}")
                return client

            except Exception as e:
                last_error = e
                logger.warning(
                    f"Connection attempt {attempt + 1} failed for {username}@{host}:{port}: {e}"
                )

                if attempt < self.retry_max_attempts - 1:
                    # Exponential backoff
                    delay = self.retry_base_delay * (2**attempt)
                    logger.debug(f"Retrying in {delay}s...")
                    await asyncio.sleep(delay)

        # All attempts failed
        error_msg = f"Failed to connect to {username}@{host}:{port} after {self.retry_max_attempts} attempts: {last_error}"
        logger.error(error_msg)
        raise ConnectionError(error_msg)

    async def _check_connection_health(self, conn: SSHConnection) -> bool:
        """
        Check if a connection is healthy

        Args:
            conn: SSH connection to check

        Returns:
            True if healthy, False otherwise
        """
        try:
            # Simple health check: execute 'echo' command
            transport = conn.client.get_transport()
            if not transport or not transport.is_active():
                logger.debug(f"Transport inactive for connection to {conn.host}")
                return False

            # Execute simple command
            stdin, stdout, stderr = conn.client.exec_command(
                "echo health_check", timeout=5
            )
            output = stdout.read().decode().strip()

            if output == "health_check":
                conn.last_health_check = datetime.now()
                conn.state = ConnectionState.IDLE
                return True
            else:
                logger.warning(
                    f"Unexpected health check response from {conn.host}: {output}"
                )
                return False

        except Exception as e:
            logger.warning(f"Health check failed for connection to {conn.host}: {e}")
            return False

    async def _health_check_loop(self):
        """Background task for periodic health checks"""
        logger.info("Starting health check loop")

        while self._running:
            try:
                await asyncio.sleep(self.health_check_interval)
                await self._perform_health_checks()
                await self._cleanup_idle_connections()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")

        logger.info("Health check loop stopped")

    async def _perform_health_checks(self):
        """Perform health checks on all connections"""
        async with self._lock:
            for pool_key, pool in self.pools.items():
                for conn in pool:
                    if conn.state in [ConnectionState.IDLE, ConnectionState.ACTIVE]:
                        if conn.needs_health_check(self.health_check_interval):
                            if not await self._check_connection_health(conn):
                                conn.state = ConnectionState.UNHEALTHY
                                logger.warning(
                                    f"Connection to {pool_key} marked unhealthy"
                                )

    async def _cleanup_idle_connections(self):
        """Clean up idle and unhealthy connections"""
        async with self._lock:
            for pool_key, pool in self.pools.items():
                connections_to_remove = []

                for conn in pool:
                    # Remove unhealthy connections
                    if conn.state == ConnectionState.UNHEALTHY:
                        self._close_connection(conn)
                        connections_to_remove.append(conn)
                        logger.info(f"Removed unhealthy connection to {pool_key}")

                    # Remove idle timeout connections
                    elif conn.state == ConnectionState.IDLE and conn.is_idle_timeout(
                        self.idle_timeout
                    ):
                        self._close_connection(conn)
                        connections_to_remove.append(conn)
                        logger.info(
                            f"Removed idle timeout connection to {pool_key} "
                            f"(idle for {(datetime.now() - conn.last_used).total_seconds()}s)"
                        )

                # Remove from pool
                for conn in connections_to_remove:
                    pool.remove(conn)

    def _close_connection(self, conn: SSHConnection):
        """Close a single SSH connection"""
        try:
            conn.client.close()
            conn.state = ConnectionState.CLOSED
        except Exception as e:
            logger.error(f"Error closing connection to {conn.host}: {e}")

    async def cleanup_all(self):
        """Clean up all connections in the pool"""
        async with self._lock:
            logger.info("Cleaning up all SSH connections...")

            for pool_key, pool in self.pools.items():
                for conn in pool:
                    self._close_connection(conn)
                logger.info(f"Closed all connections for {pool_key}")

            self.pools.clear()
            logger.info("All SSH connections cleaned up")

    async def get_pool_stats(self) -> Dict[str, Dict[str, int]]:
        """Get statistics about connection pools"""
        async with self._lock:
            stats = {}

            for pool_key, pool in self.pools.items():
                stats[pool_key] = {
                    "total": len(pool),
                    "idle": len([c for c in pool if c.state == ConnectionState.IDLE]),
                    "active": len(
                        [c for c in pool if c.state == ConnectionState.ACTIVE]
                    ),
                    "unhealthy": len(
                        [c for c in pool if c.state == ConnectionState.UNHEALTHY]
                    ),
                    "closed": len(
                        [c for c in pool if c.state == ConnectionState.CLOSED]
                    ),
                }

            return stats
