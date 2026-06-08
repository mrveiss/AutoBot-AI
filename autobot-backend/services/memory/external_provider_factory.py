# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""External Provider Factory (Issue #4344)"""

from enum import Enum

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config

logger = get_logger(__name__)


class ProviderType(str, Enum):
    """Enum for supported external provider types."""

    REDIS = "redis"
    MILVUS = "milvus"


class ExternalProviderFactory:
    """Factory for creating and managing external memory providers."""

    _instance = None
    _external_provider = None
    _provider_type: ProviderType | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    async def get_provider(cls, provider_type: ProviderType = None):
        """Get or create the configured external provider."""
        if provider_type is None:
            provider_type = cls._get_configured_provider()

        if provider_type is None:
            logger.info("No external provider configured")
            return None

        if cls._provider_type and cls._provider_type != provider_type:
            raise ValueError(
                f"Cannot switch from {cls._provider_type} to {provider_type}. "
                "At most one external provider allowed at a time."
            )

        if cls._external_provider is None:
            cls._external_provider = cls._create_provider(provider_type)
            cls._provider_type = provider_type
            await cls._external_provider.initialize()
            logger.info(f"Initialized external provider: {provider_type}")

        return cls._external_provider

    @classmethod
    def _get_configured_provider(cls) -> ProviderType | None:
        try:
            provider_name = getattr(config, "external_memory_provider", None)
            if provider_name:
                return ProviderType(provider_name.lower())
        except (ValueError, AttributeError):
            logger.debug("No external memory provider configured")
        return None

    @classmethod
    def _create_provider(cls, provider_type: ProviderType):
        if provider_type == ProviderType.REDIS:
            from .redis_provider import RedisMemoryProvider

            return RedisMemoryProvider()
        elif provider_type == ProviderType.MILVUS:
            from .milvus_provider import MilvusMemoryProvider

            return MilvusMemoryProvider(
                host=getattr(config, "milvus_host", "localhost"),
                port=getattr(config, "milvus_port", 19530),
            )
        else:
            raise ValueError(f"Unsupported provider type: {provider_type}")

    @classmethod
    async def close(cls) -> None:
        if cls._external_provider:
            try:
                await cls._external_provider.close()
                cls._external_provider = None
                cls._provider_type = None
                logger.info("External provider closed")
            except Exception as e:
                logger.error(f"Error closing external provider: {e}")

    @classmethod
    async def health_check(cls) -> bool:
        provider = await cls.get_provider()
        if provider is None:
            return True
        try:
            return await provider.health_check()
        except Exception as e:
            logger.error(f"External provider health check failed: {e}")
            return False
