"""
Redis Database Manager for AutoBot
Provides centralized database selection and connection management
Ensures proper data isolation across different Redis databases
"""

import logging
import os
from enum import Enum
from typing import Any, Dict, Optional

import redis
import redis.asyncio as aioredis
import yaml

from src.config_helper import cfg
from .service_registry import get_service_registry
from src.constants.network_constants import NetworkConstants

logger = logging.getLogger(__name__)


class RedisDatabase(Enum):
    """Enumeration of Redis databases for type safety"""

    MAIN = cfg.get("redis.databases.main", 0)
    KNOWLEDGE = cfg.get("redis.databases.knowledge", 1)
    PROMPTS = cfg.get("redis.databases.prompts", 2)
    AGENTS = cfg.get("redis.databases.agents", 3)
    METRICS = cfg.get("redis.databases.metrics", 4)
    LOGS = cfg.get("redis.databases.logs", 5)
    SESSIONS = cfg.get("redis.databases.sessions", 6)
    WORKFLOWS = cfg.get("redis.databases.workflows", 7)
    VECTORS = cfg.get("redis.databases.vectors", 8)
    MODELS = cfg.get("redis.databases.models", 9)
    TESTING = cfg.get("redis.databases.testing", 15)


class RedisDatabaseManager:
    """
    Centralized Redis database connection manager
    Eliminates duplicate Redis configuration patterns across components
    """

    def __init__(self, config_path: Optional[str] = None):
        # PERFORMANCE FIX: Use correct config path for host-based backend
        default_config_path = "/app/config/redis-databases.yaml"  # Container path
        host_config_path = (
            "config/redis-databases.yaml"  # Host path (relative to project root)
        )

        # Auto-detect if we're running on host vs container
        if os.path.exists(host_config_path):
            default_config_path = host_config_path
        elif os.path.exists("/home/kali/Desktop/AutoBot/config/redis-databases.yaml"):
            default_config_path = (
                "/home/kali/Desktop/AutoBot/config/redis-databases.yaml"
            )

        self.config_path = (
            config_path or cfg.get_path("config", "redis") or default_config_path
        )
        self.config = self._load_config()
        self._connections: Dict[str, redis.Redis] = {}
        self._async_connections: Dict[str, aioredis.Redis] = {}

        # Redis connection settings using service registry
        registry = get_service_registry()
        redis_config = registry.get_service_config("redis")

        self.host = redis_config.host if redis_config else cfg.get_host("redis")
        self.port = redis_config.port if redis_config else cfg.get_port("redis")
        self.password = cfg.get("redis.password")
        self.max_connections = cfg.get("redis.connection.max_connections", 20)
        self.socket_timeout = cfg.get("redis.connection.socket_timeout", 30)
        self.socket_keepalive = cfg.get("redis.connection.socket_keepalive", True)

    def _load_config(self) -> Dict[str, Any]:
        """Load Redis database configuration"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r") as f:
                    return yaml.safe_load(f)
            else:
                logger.warning(f"Redis config file not found: {self.config_path}")
                return self._get_default_config()
        except Exception as e:
            logger.error(f"Error loading Redis config: {e}")
            return self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """Default configuration if config file is not available"""
        return {
            "redis_databases": {
                "main": {
                    "db": cfg.get("redis.databases.main", 0),
                    "description": "Main application data",
                },
                "knowledge": {
                    "db": cfg.get("redis.databases.knowledge", 1),
                    "description": "Knowledge base documents",
                },
                "prompts": {
                    "db": cfg.get("redis.databases.prompts", 2),
                    "description": "Prompt templates",
                },
                "agents": {
                    "db": cfg.get("redis.databases.agents", 3),
                    "description": "Agent communication",
                },
                "metrics": {
                    "db": cfg.get("redis.databases.metrics", 4),
                    "description": "Performance metrics",
                },
                "logs": {
                    "db": cfg.get("redis.databases.logs", 5),
                    "description": "Structured logs",
                },
                "sessions": {
                    "db": cfg.get("redis.databases.sessions", 6),
                    "description": "User sessions",
                },
                "workflows": {
                    "db": cfg.get("redis.databases.workflows", 7),
                    "description": "Workflow state",
                },
                "vectors": {
                    "db": cfg.get("redis.databases.vectors", 8),
                    "description": "Vector embeddings",
                },
                "models": {
                    "db": cfg.get("redis.databases.models", 9),
                    "description": "Model metadata",
                },
                "testing": {
                    "db": cfg.get("redis.databases.testing", 15),
                    "description": "Test data",
                },
            }
        }

    def get_database_number(self, database_name: str) -> int:
        """Get the database number for a given database name"""
        databases = self.config.get("redis_databases", {})
        if database_name in databases:
            return databases[database_name]["db"]

        # Fallback to environment variables
        env_var = f"REDIS_DB_{database_name.upper()}"
        if env_var in os.environ:
            return int(os.environ[env_var])

        # Default to main database
        logger.warning(
            f"Database '{database_name}' not configured, using main database"
        )
        return 0

    def get_connection(
        self, database: str, decode_responses: bool = True, **kwargs
    ) -> redis.Redis:
        """
        Get a Redis connection for a specific database

        Args:
            database: Database name (e.g., 'knowledge', 'prompts', 'main')
            decode_responses: Whether to decode responses to strings
            **kwargs: Additional Redis connection parameters

        Returns:
            Redis connection instance
        """
        connection_key = f"{database}_{decode_responses}"

        if connection_key not in self._connections:
            db_number = self.get_database_number(database)

            connection_params = {
                "host": self.host,
                "port": self.port,
                "db": db_number,
                "decode_responses": decode_responses,
                "socket_timeout": self.socket_timeout,
                "socket_keepalive": self.socket_keepalive,
                "max_connections": self.max_connections,
                **kwargs,
            }

            if self.password:
                connection_params["password"] = self.password

            try:
                self._connections[connection_key] = redis.Redis(
                    connection_pool=redis.ConnectionPool(**connection_params)
                )

                # Test connection asynchronously to avoid blocking
                try:
                    # Use a very short timeout to avoid blocking the event loop
                    self._connections[connection_key].ping()
                except Exception as ping_error:
                    logger.warning(
                        f"Redis ping failed for '{database}', but continuing: {ping_error}"
                    )
                    # Don't raise - allow connection to be established even if ping fails
                logger.info(
                    f"Connected to Redis database '{database}' (DB {db_number})"
                )

            except Exception as e:
                logger.error(f"Failed to connect to Redis database '{database}': {e}")
                raise

        return self._connections[connection_key]

    async def get_async_connection(
        self, database: str, decode_responses: bool = True, **kwargs
    ) -> aioredis.Redis:
        """
        Get an async Redis connection for a specific database

        Args:
            database: Database name (e.g., 'knowledge', 'prompts', 'main')
            decode_responses: Whether to decode responses to strings
            **kwargs: Additional Redis connection parameters

        Returns:
            Async Redis connection instance
        """
        connection_key = f"{database}_{decode_responses}"

        if connection_key not in self._async_connections:
            db_number = self.get_database_number(database)

            connection_params = {
                "host": self.host,
                "port": self.port,
                "db": db_number,
                "decode_responses": decode_responses,
                "socket_timeout": self.socket_timeout,
                "socket_keepalive": self.socket_keepalive,
                **kwargs,
            }

            if self.password:
                connection_params["password"] = self.password

            try:
                self._async_connections[connection_key] = aioredis.Redis(
                    **connection_params
                )

                # Test connection
                await self._async_connections[connection_key].ping()
                logger.info(
                    f"Connected to async Redis database '{database}' (DB {db_number})"
                )

            except Exception as e:
                logger.error(
                    f"Failed to connect to async Redis database '{database}': {e}"
                )
                raise

        return self._async_connections[connection_key]

    def get_knowledge_base_connection(self, **kwargs) -> redis.Redis:
        """Get Redis connection for knowledge base data"""
        return self.get_connection("knowledge", **kwargs)

    def get_prompts_connection(self, **kwargs) -> redis.Redis:
        """Get Redis connection for prompt templates"""
        return self.get_connection("prompts", **kwargs)

    def get_agents_connection(self, **kwargs) -> redis.Redis:
        """Get Redis connection for agent communication"""
        return self.get_connection("agents", **kwargs)

    def get_metrics_connection(self, **kwargs) -> redis.Redis:
        """Get Redis connection for performance metrics"""
        return self.get_connection("metrics", **kwargs)

    def get_main_connection(self, **kwargs) -> redis.Redis:
        """Get Redis connection for main application data"""
        return self.get_connection("main", **kwargs)

    async def get_async_knowledge_base_connection(self, **kwargs) -> aioredis.Redis:
        """Get async Redis connection for knowledge base data"""
        return await self.get_async_connection("knowledge", **kwargs)

    async def get_async_prompts_connection(self, **kwargs) -> aioredis.Redis:
        """Get async Redis connection for prompt templates"""
        return await self.get_async_connection("prompts", **kwargs)

    async def get_async_agents_connection(self, **kwargs) -> aioredis.Redis:
        """Get async Redis connection for agent communication"""
        return await self.get_async_connection("agents", **kwargs)

    def close_all_connections(self):
        """Close all Redis connections"""
        for connection in self._connections.values():
            try:
                connection.close()
            except Exception as e:
                logger.error(f"Error closing Redis connection: {e}")

        self._connections.clear()

    async def close_all_async_connections(self):
        """Close all async Redis connections"""
        for connection in self._async_connections.values():
            try:
                await connection.close()
            except Exception as e:
                logger.error(f"Error closing async Redis connection: {e}")

        self._async_connections.clear()

    def get_database_info(self) -> Dict[str, Any]:
        """Get information about all configured databases"""
        return self.config.get("redis_databases", {})

    def validate_database_separation(self) -> bool:
        """Validate that databases are properly separated"""
        databases = self.config.get("redis_databases", {})
        db_numbers = set()

        for db_name, db_config in databases.items():
            db_num = db_config.get("db")
            if db_num in db_numbers:
                logger.error(
                    f"Database number {db_num} is used by multiple databases including '{db_name}'"
                )
                return False
            db_numbers.add(db_num)

        logger.info("Database separation validation passed")
        return True


# Global instance for easy access
redis_db_manager = RedisDatabaseManager()


# Convenience functions for backward compatibility
def get_redis_client(database: str = "main", async_client: bool = False, **kwargs):
    """
    Get Redis client for specified database

    Args:
        database: Database name ('main', 'knowledge', 'prompts', etc.)
        async_client: Whether to return async client
        **kwargs: Additional connection parameters

    Returns:
        Redis client instance
    """
    if async_client:
        # For async, we need to handle this differently
        # Return a coroutine that can be awaited
        async def get_async_client():
            return await redis_db_manager.get_async_connection(database, **kwargs)

        return get_async_client()
    else:
        return redis_db_manager.get_connection(database, **kwargs)


# Migration helper for existing code
def get_knowledge_base_redis(**kwargs) -> redis.Redis:
    """Get Redis connection specifically for knowledge base"""
    return redis_db_manager.get_knowledge_base_connection(**kwargs)


def get_prompts_redis(**kwargs) -> redis.Redis:
    """Get Redis connection specifically for prompts"""
    return redis_db_manager.get_prompts_connection(**kwargs)


def get_agents_redis(**kwargs) -> redis.Redis:
    """Get Redis connection specifically for agent communication"""
    return redis_db_manager.get_agents_connection(**kwargs)
