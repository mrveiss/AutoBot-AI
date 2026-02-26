# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""AutoBot shared utilities - deployed with each backend component.

Issue #1196: Lazy imports via __getattr__ to break circular import:
  autobot_shared.__init__ → redis_client → utils.redis_management
  → monitoring.prometheus_metrics → autobot_shared (CIRCULAR)
"""

import sys
from pathlib import Path

# Add backend directory to Python path for imports (Issue #781 folder reorganization)
_backend_path = Path(__file__).parent.parent / "backend"
if _backend_path.exists() and str(_backend_path) not in sys.path:
    sys.path.insert(0, str(_backend_path))

__all__ = ["get_redis_client", "config", "get_tracer", "init_tracing"]

# Lazy import map — module attribute → (submodule, name)
_LAZY_IMPORTS = {
    "get_redis_client": (".redis_client", "get_redis_client"),
    "config": (".ssot_config", "config"),
    "get_tracer": (".tracing", "get_tracer"),
    "init_tracing": (".tracing", "init_tracing"),
}


def __getattr__(name):
    if name in _LAZY_IMPORTS:
        module_path, attr_name = _LAZY_IMPORTS[name]
        import importlib

        mod = importlib.import_module(module_path, __name__)
        val = getattr(mod, attr_name)
        # Cache on module so __getattr__ isn't called again
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
