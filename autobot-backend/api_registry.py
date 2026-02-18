#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Simple API Registry for tracking registered routers and endpoints.
"""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter

logger = logging.getLogger(__name__)


class APIRegistry:
    """Simple registry to track API routers and endpoints."""

    def __init__(self):
        """Initialize API registry with empty router storage."""
        self.routers: Dict[str, Dict[str, Any]] = {}
        logger.debug("APIRegistry initialized")

    def register_router(self, name: str, router: APIRouter, prefix: str) -> None:
        """Register a router with its metadata."""
        self.routers[name] = {
            "router": router,
            "prefix": prefix,
            "routes": len(router.routes) if hasattr(router, "routes") else 0,
        }
        logger.debug(
            f"Registered router: {name} at {prefix} with {self.routers[name]['routes']} routes"
        )

    def get_registry(self) -> Dict[str, Dict[str, Any]]:
        """Get the complete registry."""
        return self.routers.copy()

    def get_router_names(self) -> List[str]:
        """Get list of registered router names."""
        return list(self.routers.keys())

    def get_router_count(self) -> int:
        """Get total number of registered routers."""
        return len(self.routers)

    def get_total_routes(self) -> int:
        """Get total number of routes across all routers."""
        return sum(
            router_info.get("routes", 0) for router_info in self.routers.values()
        )
