# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Redis Types Module — Single Source of Truth (#2670)

Database numbers are loaded from redis-databases.yaml at import time.
If the YAML is not found, a hardcoded fallback (kept in sync with the YAML
via tests/test_redis_db_ssot.py) is used.

Contains:
- RedisDatabase: Type-safe database enumeration
- ConnectionState: Circuit breaker connection states
- DATABASE_MAPPING: name → db-number dict (the runtime SSOT)
- load_database_mapping_from_yaml(): loader for redis-databases.yaml

Extracted from redis_client.py as part of Issue #381 refactoring.
Centralized as part of Issue #2670.
"""

import logging
import os
from enum import Enum
from typing import Dict

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# YAML loader — reads redis-databases.yaml and returns {name: db_number}
# ---------------------------------------------------------------------------


def _resolve_yaml_path() -> str | None:
    """Find redis-databases.yaml in known locations."""
    possible_paths = [
        # Relative to this file: autobot_shared/redis_management/ → ../../
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "autobot-infrastructure",
            "shared",
            "config",
            "redis-databases.yaml",
        ),
        "/app/config/redis-databases.yaml",  # Container
        "./config/redis-databases.yaml",  # Host relative
        os.path.join(
            os.environ.get("AUTOBOT_BASE_DIR", "/opt/autobot"),  # ssot-config-exempt: bootstrap before config available
            "config/redis-databases.yaml",
        ),
    ]
    for path in possible_paths:
        resolved = os.path.normpath(path)
        if os.path.exists(resolved):
            return resolved
    return None


def load_database_mapping_from_yaml() -> Dict[str, int] | None:
    """Load database name→number mapping from redis-databases.yaml.

    Returns:
        Dict mapping database names to numbers, or None if YAML not found.
    """
    yaml_path = _resolve_yaml_path()
    if not yaml_path:
        return None

    try:
        import yaml

        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        databases = data.get("redis_databases", {})
        return {name: cfg["db"] for name, cfg in databases.items() if "db" in cfg}
    except Exception as e:
        logger.warning("Failed to load redis-databases.yaml: %s", e)
        return None


# ---------------------------------------------------------------------------
# Hardcoded fallback — MUST match redis-databases.yaml exactly.
# Validated by tests/test_redis_db_ssot.py (#2670).
# ---------------------------------------------------------------------------
_FALLBACK_MAPPING: Dict[str, int] = {
    "main": 0,
    "knowledge": 1,
    "prompts": 2,
    "agents": 3,
    "metrics": 4,
    "cache": 5,
    "sessions": 6,
    "workflows": 7,
    "logs": 8,
    "temp": 9,
    "audit": 10,
    "analytics": 11,
    "testing": 13,
    "celery_broker": 14,
    "celery_results": 15,
}

# Backward-compatible aliases for names used in existing code.
# These map to the canonical database they logically belong to.
_ALIASES: Dict[str, int] = {
    "conversations": 3,  # Alias for agents (conversation storage)
    "locks": 6,  # Alias for sessions (distributed locks)
    "memory": 0,  # Uses DB 0 — required for RediSearch indexing (FT.*)
    "vectors": 8,  # LlamaIndex vector store — DB 8 per docs/system-state.md
    "facts": 1,  # Knowledge facts and rules
}


def _build_database_mapping() -> Dict[str, int]:
    """Build the canonical DATABASE_MAPPING from YAML or fallback."""
    yaml_mapping = load_database_mapping_from_yaml()
    base = yaml_mapping if yaml_mapping is not None else _FALLBACK_MAPPING.copy()
    # Merge aliases (don't overwrite canonical names from YAML)
    for alias, db_num in _ALIASES.items():
        if alias not in base:
            base[alias] = db_num
    return base


# The runtime mapping used by RedisConnectionManager._get_database_number()
DATABASE_MAPPING: Dict[str, int] = _build_database_mapping()


class RedisDatabase(Enum):
    """Type-safe database enumeration aligned with redis-databases.yaml (#2670).

    Each value corresponds to a Redis database number (0-15).
    """

    MAIN = 0
    KNOWLEDGE = 1
    PROMPTS = 2
    AGENTS = 3
    METRICS = 4
    CACHE = 5
    SESSIONS = 6
    WORKFLOWS = 7
    LOGS = 8
    TEMP = 9
    AUDIT = 10
    ANALYTICS = 11
    TESTING = 13
    CELERY_BROKER = 14
    CELERY_RESULTS = 15
    # Aliases — share DB numbers with canonical entries
    VECTORS = 8  # LlamaIndex vector store
    MEMORY = 0  # RediSearch indexing on DB 0


class ConnectionState(Enum):
    """Redis connection states for circuit breaker pattern.

    States:
    - HEALTHY: Connection is working normally
    - DEGRADED: Connection experiencing intermittent issues
    - FAILED: Connection is down, circuit breaker may be open
    """

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
