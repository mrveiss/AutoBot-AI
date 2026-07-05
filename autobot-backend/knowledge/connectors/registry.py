# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Connector Registry

Issue #1254: Singleton registry that maps connector type strings to their
implementation classes and manages live connector instances.

Usage:
    # Register a connector class (decorator):
    @ConnectorRegistry.register("my_source")
    class MySourceConnector(AbstractConnector):
        connector_type = "my_source"

    # Create and manage instances:
    instance = ConnectorRegistry.create(config)
    ConnectorRegistry.add_instance(instance)
    running = ConnectorRegistry.get("my-connector-id")

Issue #8152: create() now async with migration support.
"""

from __future__ import annotations

import asyncio
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Type

if TYPE_CHECKING:
    from .base import AbstractConnector  # noqa: F401  # forward-ref for string annotations

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc
from knowledge.connectors.models import ConnectorConfig

logger = get_logger(__name__)

# Issue #10539: Category → connector type list.
# Maps a logical capability category (lowercase, normalised) to the list of
# registered connector type strings that satisfy it.  Only connector types
# that are actually implemented in this codebase are listed here.
CATEGORY_MAP: Dict[str, List[str]] = {
    "cloud storage": ["gdrive", "onedrive", "nextcloud"],
    "source control": ["gitlab", "gitea"],
    "wiki": ["notion"],
    "knowledge base": ["notion", "file_server", "web_crawler"],
    "file system": ["file_server"],
    "database": ["database"],
    "web": ["web_crawler"],
    "audio": ["audio"],
    "external": ["external_adapter"],
}


class ConnectorRegistry:
    """Class-level registry for connector types and running instances."""

    # type string → connector class
    _connectors: Dict[str, "Type"] = {}
    # connector_id → live instance
    _instances: Dict[str, "object"] = {}

    @classmethod
    def register(cls, connector_type: str):
        """Class decorator that registers a connector class under *connector_type*.

        Example::

            @ConnectorRegistry.register("file_server")
            class FileServerConnector(AbstractConnector):
                connector_type = "file_server"
        """

        def decorator(klass):
            cls._connectors[connector_type] = klass
            logger.debug("Registered connector type: %s -> %s", connector_type, klass)
            return klass

        return decorator

    @classmethod
    async def create(cls, config: ConnectorConfig) -> "object":
        """Instantiate a connector from a :class:`ConnectorConfig`.

        If the stored config version differs from the connector class's
        ``config_version``, calls ``migrate_config()`` before instantiation
        and persists the updated config back to Redis (Issue #8152).

        Raises:
            ValueError: If ``config.connector_type`` is not registered or
                        migration raises an exception.
        """

        klass = cls._connectors.get(config.connector_type)
        if klass is None:
            registered = list(cls._connectors.keys())
            raise ValueError("Unknown connector type '%s'. Registered types: %s" % (config.connector_type, registered))

        stored_version = config.config.get("_version", 1)
        current_version = getattr(klass, "config_version", 1)
        if stored_version != current_version:
            try:
                config.config = klass.migrate_config(stored_version, dict(config.config))
                config.config["_version"] = current_version
                logger.info(
                    "Migrated connector %s config from v%d to v%d",
                    config.connector_id,
                    stored_version,
                    current_version,
                )
                await cls._persist_config(config)
            except Exception as exc:
                logger.error(
                    "Config migration failed for connector %s (v%d→v%d): %s",
                    config.connector_id,
                    stored_version,
                    current_version,
                    exc,
                )
                raise ValueError("Config migration failed for connector '%s': %s" % (config.connector_id, exc)) from exc

        instance = klass(config)
        logger.info(
            "Created connector instance: id=%s type=%s",
            config.connector_id,
            config.connector_type,
        )
        return instance

    @classmethod
    async def _persist_config(cls, config: "ConnectorConfig") -> None:
        """Persist the migrated config dict back to Redis (Issue #8152).

        Reads the existing blob, patches the ``config`` field, and writes it
        back.  Failures are logged at WARNING and never propagate — a failed
        persist means the migration runs again on next load, which is safe.
        """
        import json

        try:
            from autobot_shared.redis_client import get_async_redis_client

            redis = await get_async_redis_client(database="knowledge")
            if redis is None:
                return
            key = "connector:%s" % config.connector_id
            raw = await redis.get(key)
            if raw is None:
                return
            data = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
            data["config"] = config.config
            await redis.set(key, json.dumps(data, ensure_ascii=False))
            logger.debug("Persisted migrated config for connector %s", config.connector_id)
        except Exception as exc:
            logger.warning("Failed to persist migrated config for %s: %s", config.connector_id, exc)

    @classmethod
    def add_instance(cls, instance: "object") -> None:
        """Register a live connector instance so it can be retrieved by ID."""
        connector_id = instance.config.connector_id
        cls._instances[connector_id] = instance
        logger.debug("Added connector instance: %s", connector_id)

    @classmethod
    def remove_instance(cls, connector_id: str) -> None:
        """Remove a connector instance from the registry."""
        cls._instances.pop(connector_id, None)
        logger.debug("Removed connector instance: %s", connector_id)

    @classmethod
    def get(cls, connector_id: str) -> object | None:
        """Return a running connector by ID, or None if not found."""
        return cls._instances.get(connector_id)

    @classmethod
    def list_types(cls) -> List[str]:
        """Return all registered connector type strings."""
        return list(cls._connectors.keys())

    @classmethod
    def resolve_by_category(cls, category: str) -> List[object]:
        """Return live instances whose connector type belongs to *category*.

        Issue #10539: Category resolution lets skills/workflows request a
        capability (e.g. "cloud storage", "source control") rather than naming
        a specific vendor connector.  Only instances that are already
        registered (i.e. configured and started via ``add_instance``) are
        returned — unconfigured connector types are silently excluded.

        The lookup is case-insensitive and strips surrounding whitespace so
        callers may pass ``"Cloud Storage"`` or ``"cloud storage"`` equally.

        Args:
            category: A category label from ``CATEGORY_MAP`` (case-insensitive).

        Returns:
            List of live connector instances matching the category; empty list
            if the category is unknown or no matching instance is configured.
        """
        key = category.strip().lower()
        type_ids = CATEGORY_MAP.get(key, [])
        if not type_ids:
            logger.debug("resolve_by_category: unknown category %r", category)
            return []
        matched = [
            instance
            for instance in cls._instances.values()
            if getattr(getattr(instance, "config", None), "connector_type", None) in type_ids
        ]
        logger.debug(
            "resolve_by_category(%r): types=%r matched=%d instance(s)",
            category,
            type_ids,
            len(matched),
        )
        return matched

    @classmethod
    def registered_types(cls) -> Mapping[str, Type["AbstractConnector"]]:
        """Immutable view of all registered connector classes by type name (Issue #5057).

        Callers iterating over the type→class mapping should use this method
        instead of reading the private ``_connectors`` dict so internal storage
        can be refactored without breaking them.
        """
        return MappingProxyType(cls._connectors)

    @classmethod
    def get_registered_class(cls, type_name: str) -> Type["AbstractConnector"] | None:
        """Return the registered connector class for *type_name*, or None (Issue #5057).

        Public accessor that replaces ``ConnectorRegistry._connectors.get(...)``
        at call sites outside the registry module.
        """
        return cls._connectors.get(type_name)

    @classmethod
    def list_instances(cls) -> List[str]:
        """Return IDs of all currently registered instances."""
        return list(cls._instances.keys())

    @classmethod
    async def health_check_all(cls) -> Dict[str, Any]:
        """Aggregate ``test_connection()`` results across all live instances (Issue #4420).

        Runs every connector's ``test_connection()`` concurrently so one slow
        or failing connector never blocks the rest.  Exceptions are caught
        per-connector and surfaced in the ``errors`` map.

        Returns:
            Dict with keys:
                healthy: sorted list of instance labels whose test_connection() returned truthy
                unavailable: sorted list of labels that returned falsy or raised
                errors: map of label -> error string (only for those that raised)
                checked_at: UTC ISO-8601 timestamp of the check
        """
        instances = list(cls._instances.values())
        if not instances:
            return {
                "healthy": [],
                "unavailable": [],
                "errors": {},
                "checked_at": now_utc().isoformat(),
            }

        results = await asyncio.gather(
            *[cls._check_one(instance) for instance in instances],
            return_exceptions=False,
        )

        healthy: List[str] = []
        unavailable: List[str] = []
        errors: Dict[str, str] = {}
        for label, ok, err in results:
            if ok:
                healthy.append(label)
            else:
                unavailable.append(label)
                if err is not None:
                    errors[label] = err

        return {
            "healthy": sorted(healthy),
            "unavailable": sorted(unavailable),
            "errors": errors,
            "checked_at": now_utc().isoformat(),
        }

    @classmethod
    async def _check_one(cls, instance: Any) -> tuple:
        """Run test_connection() on a single instance, never raising (Issue #4420)."""
        label = cls._label_for(instance)
        try:
            ok = await instance.test_connection()
            return label, bool(ok), None
        except Exception as exc:
            logger.warning("Connector %s health check raised: %s", label, exc)
            return label, False, str(exc)

    @staticmethod
    def _label_for(instance: Any) -> str:
        """Build a human-readable label ``{connector_type}:{name}`` (Issue #4420).

        Falls back to connector_id if type or name is missing.
        """
        cfg = getattr(instance, "config", None)
        if cfg is None:
            return "unknown"
        connector_type = getattr(cfg, "connector_type", "") or "unknown"
        name = getattr(cfg, "name", "") or getattr(cfg, "connector_id", "unknown")
        return "%s:%s" % (connector_type, name)
