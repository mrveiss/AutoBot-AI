# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""AutoBot shared utilities - deployed with each backend component."""

import sys
from pathlib import Path

# Add backend directory to Python path for imports (Issue #781 folder reorganization)
_backend_path = Path(__file__).parent.parent / "backend"
if _backend_path.exists() and str(_backend_path) not in sys.path:
    sys.path.insert(0, str(_backend_path))

from .redis_client import get_redis_client
from .ssot_config import config
from .tracing import get_tracer, init_tracing

__all__ = ["get_redis_client", "config", "get_tracer", "init_tracing"]
