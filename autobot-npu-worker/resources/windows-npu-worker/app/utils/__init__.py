# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Windows NPU Worker Utilities Package
"""
from .redis_client import get_redis_client
from .backend_telemetry import (
    BackendTelemetryClient,
    get_telemetry_client,
    stop_telemetry_client,
)
from .config_bootstrap import (
    fetch_bootstrap_config,
    get_cached_config,
    get_worker_id,
    get_redis_config,
    get_backend_config,
    get_models_config,
)

__all__ = [
    "get_redis_client",
    "BackendTelemetryClient",
    "get_telemetry_client",
    "stop_telemetry_client",
    "fetch_bootstrap_config",
    "get_cached_config",
    "get_worker_id",
    "get_redis_config",
    "get_backend_config",
    "get_models_config",
]
