# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Hello Plugin - Simple Example

Demonstrates basic plugin structure and lifecycle.
Issue #730 - Plugin SDK example.
"""

import logging
from typing import Dict, Optional

from plugin_sdk.base import BasePlugin, PluginManifest

logger = logging.getLogger(__name__)


class HelloPlugin(BasePlugin):
    """Simple hello world plugin."""

    def __init__(self, manifest: PluginManifest, config: Optional[Dict] = None):
        """Initialize hello plugin."""
        super().__init__(manifest, config)
        self.greeting = (
            config.get("greeting", "Hello from plugin!")
            if config
            else "Hello from plugin!"
        )

    async def initialize(self) -> None:
        """Initialize plugin resources."""
        self._logger.info("Hello Plugin initializing...")
        self._logger.info("Greeting message: %s", self.greeting)
        self._logger.info("Hello Plugin initialized successfully!")

    async def shutdown(self) -> None:
        """Clean up plugin resources."""
        self._logger.info("Hello Plugin shutting down...")
        self._logger.info("Goodbye from Hello Plugin!")

    async def enable(self) -> None:
        """Enable plugin."""
        await super().enable()
        self._logger.info("Hello Plugin enabled with greeting: %s", self.greeting)

    async def disable(self) -> None:
        """Disable plugin."""
        await super().disable()
        self._logger.info("Hello Plugin disabled")

    def say_hello(self) -> str:
        """Public method for saying hello."""
        return self.greeting


# Export plugin class
Plugin = HelloPlugin
