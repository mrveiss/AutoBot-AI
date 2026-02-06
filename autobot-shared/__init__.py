# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""AutoBot shared utilities - deployed with each backend component."""

from .redis_client import get_redis_client
from .ssot_config import config

__all__ = ["get_redis_client", "config"]
