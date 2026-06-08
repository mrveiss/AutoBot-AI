# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
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

__all__ = [
    "get_redis_client",
    "config",
    "get_tracer",
    "init_tracing",
    "ServiceMessage",
    "ServiceName",
    "MessageType",
    "serialize_message",
    "deserialize_message",
    "create_reply",
    "get_client_ip",
    # Feature flags — issue #3017
    "is_feature_enabled",
    "get_enabled_features",
    "require_feature",
    "FeatureDisabledError",
    # Singleton factory — issue #5423
    "lazy_singleton",
    # HTTP safety helpers — issue #5680
    "safe_http_detail",
    "user_facing_detail",
    # Async Redis mixin — issue #5671
    "AsyncRedisClientMixin",
    "AsyncRedisClientLockedMixin",
]

# Lazy import map — module attribute → (submodule, name)
_LAZY_IMPORTS = {
    "get_redis_client": (".redis_client", "get_redis_client"),
    "config": (".ssot_config", "config"),
    "get_tracer": (".tracing", "get_tracer"),
    "init_tracing": (".tracing", "init_tracing"),
    "ServiceMessage": (".models.service_message", "ServiceMessage"),
    "ServiceName": (".models.service_message", "ServiceName"),
    "MessageType": (".models.service_message", "MessageType"),
    "serialize_message": (".models.service_message", "serialize_message"),
    "deserialize_message": (".models.service_message", "deserialize_message"),
    "create_reply": (".models.service_message", "create_reply"),
    "get_client_ip": (".proxy_utils", "get_client_ip"),
    # Feature flags — issue #3017
    "is_feature_enabled": (".feature_flags", "is_feature_enabled"),
    "get_enabled_features": (".feature_flags", "get_enabled_features"),
    "require_feature": (".feature_flags", "require_feature"),
    "FeatureDisabledError": (".feature_flags", "FeatureDisabledError"),
    # Singleton factory — issue #5423
    "lazy_singleton": (".singleton_factory", "lazy_singleton"),
    # HTTP safety helpers — issue #5680
    "safe_http_detail": (".error_utils", "safe_http_detail"),
    "user_facing_detail": (".error_utils", "user_facing_detail"),
    # Async Redis mixin — issue #5671
    "AsyncRedisClientMixin": (".redis_mixin", "AsyncRedisClientMixin"),
    "AsyncRedisClientLockedMixin": (".redis_mixin", "AsyncRedisClientLockedMixin"),
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
