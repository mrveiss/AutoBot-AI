# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
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
"""

import asyncio
import logging
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Type

from knowledge.connectors.models import ConnectorConfig
from autobot_shared.time_utils import now_utc

logger = logging.getLogger(__name__)


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
    def create(cls, config: ConnectorConfig) -> "object":
        """Instantiate a connector from a :class:`ConnectorConfig`.

        Raises:
            ValueError: If ``config.connector_type`` is not registered.
        """
        klass = cls._connectors.get(config.connector_type)
        if klass is None:
            registered = list(cls._connectors.keys())
            raise ValueError("Unknown connector type '%s'. Registered types: %s" % (config.connector_type, registered))
        instance = klass(config)
        logger.info(
            "Created connector instance: id=%s type=%s",
            config.connector_id,
            config.connector_type,
        )
        return instance

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
    def get(cls, connector_id: str) -> Optional["object"]:
        """Return a running connector by ID, or None if not found."""
        return cls._instances.get(connector_id)

    @classmethod
    def list_types(cls) -> List[str]:
        """Return all registered connector type strings."""
        return list(cls._connectors.keys())

    @classmethod
    def registered_types(cls) -> Mapping[str, Type["AbstractConnector"]]:
        """Immutable view of all registered connector classes by type name (Issue #5057).

        Callers iterating over the type→class mapping should use this method
        instead of reading the private ``_connectors`` dict so internal storage
        can be refactored without breaking them.
        """
        return MappingProxyType(cls._connectors)

    @classmethod
    def get_registered_class(cls, type_name: str) -> Optional[Type["AbstractConnector"]]:
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
