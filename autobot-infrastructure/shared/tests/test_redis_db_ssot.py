# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Validate Redis DB allocation stays in sync across all sources (#2670).

redis-databases.yaml is the single source of truth.  This test ensures that
DATABASE_MAPPING (the runtime dict) and _FALLBACK_MAPPING (the hardcoded
backup) both match it exactly.
"""

from pathlib import Path

import pytest
import yaml


def _load_yaml_mapping() -> dict:
    """Load DB name→number from redis-databases.yaml."""
    yaml_path = Path(__file__).resolve().parents[2] / "config" / "redis-databases.yaml"
    assert yaml_path.exists(), f"SSOT file not found: {yaml_path}"
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    databases = data.get("redis_databases", {})
    return {name: cfg["db"] for name, cfg in databases.items() if "db" in cfg}


@pytest.fixture()
def yaml_mapping():
    return _load_yaml_mapping()


class TestRedisDatabaseSSOT:
    """Ensure all DB-number sources agree with redis-databases.yaml."""

    def test_fallback_matches_yaml(self, yaml_mapping):
        """_FALLBACK_MAPPING must be identical to redis-databases.yaml."""
        from autobot_shared.redis_management.types import _FALLBACK_MAPPING

        assert _FALLBACK_MAPPING == yaml_mapping, (
            "Hardcoded _FALLBACK_MAPPING diverged from redis-databases.yaml. "
            "Update _FALLBACK_MAPPING in types.py to match the YAML."
        )

    def test_database_mapping_contains_yaml_entries(self, yaml_mapping):
        """DATABASE_MAPPING must contain every entry from redis-databases.yaml."""
        from autobot_shared.redis_management.types import DATABASE_MAPPING

        for name, db_num in yaml_mapping.items():
            assert name in DATABASE_MAPPING, (
                f"'{name}' present in redis-databases.yaml but missing " f"from DATABASE_MAPPING"
            )
            assert DATABASE_MAPPING[name] == db_num, (
                f"'{name}' is DB {DATABASE_MAPPING[name]} in "
                f"DATABASE_MAPPING but DB {db_num} in redis-databases.yaml"
            )

    def test_no_unknown_canonical_entries(self, yaml_mapping):
        """DATABASE_MAPPING should not invent canonical names absent from YAML."""
        from autobot_shared.redis_management.types import (
            _ALIASES,
            DATABASE_MAPPING,
        )

        allowed = set(yaml_mapping.keys()) | set(_ALIASES.keys())
        for name in DATABASE_MAPPING:
            assert name in allowed, (
                f"'{name}' in DATABASE_MAPPING is not in " f"redis-databases.yaml and not a declared alias"
            )

    def test_redis_database_enum_values_match_yaml(self, yaml_mapping):
        """RedisDatabase enum values must match redis-databases.yaml."""
        from autobot_shared.redis_management.types import RedisDatabase

        for member in RedisDatabase:
            lower_name = member.name.lower()
            if lower_name in yaml_mapping:
                assert member.value == yaml_mapping[lower_name], (
                    f"RedisDatabase.{member.name} = {member.value} but "
                    f"redis-databases.yaml says {lower_name} = "
                    f"{yaml_mapping[lower_name]}"
                )
