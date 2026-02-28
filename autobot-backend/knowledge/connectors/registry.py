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

import logging
from typing import Dict, List, Optional, Type

from knowledge.connectors.models import ConnectorConfig

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
            raise ValueError(
                "Unknown connector type '%s'. Registered types: %s"
                % (config.connector_type, registered)
            )
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
    def list_instances(cls) -> List[str]:
        """Return IDs of all currently registered instances."""
        return list(cls._instances.keys())
