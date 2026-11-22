# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Redis Types Module — Single Source of Truth (#2670)

Database numbers are loaded from redis-databases.yaml at import time.
If the YAML is not found, a hardcoded fallback (kept in sync with the YAML
via tests/test_redis_db_ssot.py) is used. ``AUTOBOT_REDIS_DB_<NAME>`` overrides
are applied on top (#19232), so this module holds the ONE name -> number table;
``redis_db_single_table_19232_test.py`` fails on a second one.

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

from autobot_shared.redis_management.database_overrides import apply_overrides, override_source

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# YAML loader — reads redis-databases.yaml and returns {name: db_number}
# ---------------------------------------------------------------------------


_YAML_NAME = "redis-databases.yaml"


def _base_dir() -> str | None:
    """``AUTOBOT_BASE_DIR``, else the project root (the SSOT ``path.base_dir`` rule), else None.

    Never raises: importing ``redis_management`` must not fail on path resolution. With no
    determinable root the host-absolute candidate is skipped; #19350 adds the install-root
    fallback (``fleet_constants.FLEET_INSTALL_ROOT``) -- a literal here is a hardcoding finding.
    """
    explicit = os.environ.get("AUTOBOT_BASE_DIR")  # ssot-config-exempt: bootstrap before config available
    if explicit:
        return explicit
    from autobot_shared.paths import ProjectRootUndeterminable, project_root

    try:
        return str(project_root())
    except ProjectRootUndeterminable:
        return None


def _infrastructure_config_dir() -> str:
    """``shared/config`` of code_source's infrastructure tree, never the stale copy beside the install (#20578).

    Never raises (see ``_base_dir``): with no determinable root, the tree two levels above this module.
    """
    from autobot_shared.paths import INFRASTRUCTURE_DIR_NAME, ProjectRootUndeterminable, infrastructure_dir

    try:
        infra = str(infrastructure_dir())
    except ProjectRootUndeterminable:
        infra = os.path.join(os.path.dirname(__file__), "..", "..", INFRASTRUCTURE_DIR_NAME)
    return os.path.join(infra, "shared", "config")


def _yaml_candidates() -> list[str]:
    """Every place redis-databases.yaml may live, in priority order -- the ONE list (#19232).

    Built per call, never at import, so a path that changes after import is seen.
    """
    candidates = [
        os.path.join(_infrastructure_config_dir(), _YAML_NAME),  # code_source (#20578), else checkout/install
        os.path.join("/app/config", _YAML_NAME),  # container
        os.path.join(".", "config", _YAML_NAME),  # host relative
    ]
    base_dir = _base_dir()
    if base_dir:
        candidates.append(os.path.join(base_dir, "config", _YAML_NAME))  # host absolute
    return candidates


def resolve_databases_yaml() -> str | None:
    """The redis-databases.yaml in use, or None. The one resolver: the number table and the
    connection manager's per-database tuning read the same file (#19232)."""
    for path in _yaml_candidates():
        resolved = os.path.normpath(path)
        if os.path.exists(resolved):
            return resolved
    return None


def load_database_mapping_from_yaml() -> Dict[str, int] | None:
    """Load database name→number mapping from redis-databases.yaml.

    Returns:
        Dict mapping database names to numbers, or None if YAML not found.
    """
    yaml_path = resolve_databases_yaml()
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
# Validated by tests/test_redis_db_ssot.py (#2670). The only number literals
# allowed to name a database outside the YAML (#19232).
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

# Backward-compatible aliases: each NAMES the database it shares, never a number, so an
# alias follows its target when the YAML or an override moves it (#19232).
_ALIASES: Dict[str, str] = {
    "conversations": "agents",  # conversation storage
    "locks": "sessions",  # distributed locks
    "memory": "main",  # RediSearch indexing (FT.*) needs DB 0
    "vectors": "logs",  # LlamaIndex vector store, per docs/system-state.md
    "facts": "knowledge",  # knowledge facts and rules
}


def _declared_databases() -> Dict[str, int]:
    """Every database redis-databases.yaml declares, with its YAML number (no aliases, no overrides)."""
    yaml_mapping = load_database_mapping_from_yaml()
    return yaml_mapping if yaml_mapping is not None else _FALLBACK_MAPPING.copy()


#: The declared databases at their YAML numbers -- the documented defaults (env registry, docs).
DECLARED_DATABASES: Dict[str, int] = _declared_databases()


def _build_database_mapping() -> Dict[str, int]:
    """The ONE name -> number table: the YAML, then ``AUTOBOT_REDIS_DB_*`` overrides, then aliases."""
    mapping = apply_overrides(DECLARED_DATABASES, override_source())
    for alias, target in _ALIASES.items():
        if alias in mapping:
            continue
        if target not in mapping:
            # A YAML that drops an alias's target must not fail the import; the alias is
            # simply undeclared, and database_number() refuses it by name.
            logger.warning("Redis alias %r names %r, which redis-databases.yaml does not declare", alias, target)
            continue
        mapping[alias] = mapping[target]
    return mapping


# The runtime mapping every reader resolves through (database_names.database_number).
DATABASE_MAPPING: Dict[str, int] = _build_database_mapping()


class RedisDatabase(Enum):
    """Type-safe database names aligned with redis-databases.yaml (#2670).

    A member is a NAME. Its value is the YAML default number, kept only so members stay
    distinct; it is not where a database lives. Resolve one with
    ``database_names.database_number``, which honours ``AUTOBOT_REDIS_DB_*`` (#19232).
    """

    MAIN = _FALLBACK_MAPPING["main"]
    KNOWLEDGE = _FALLBACK_MAPPING["knowledge"]
    PROMPTS = _FALLBACK_MAPPING["prompts"]
    AGENTS = _FALLBACK_MAPPING["agents"]
    METRICS = _FALLBACK_MAPPING["metrics"]
    CACHE = _FALLBACK_MAPPING["cache"]
    SESSIONS = _FALLBACK_MAPPING["sessions"]
    WORKFLOWS = _FALLBACK_MAPPING["workflows"]
    LOGS = _FALLBACK_MAPPING["logs"]
    TEMP = _FALLBACK_MAPPING["temp"]
    AUDIT = _FALLBACK_MAPPING["audit"]
    ANALYTICS = _FALLBACK_MAPPING["analytics"]
    TESTING = _FALLBACK_MAPPING["testing"]
    CELERY_BROKER = _FALLBACK_MAPPING["celery_broker"]
    CELERY_RESULTS = _FALLBACK_MAPPING["celery_results"]
    # Aliases -- share a number with their canonical entry
    VECTORS = _FALLBACK_MAPPING["logs"]  # LlamaIndex vector store
    MEMORY = _FALLBACK_MAPPING["main"]  # RediSearch indexing on DB 0


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
