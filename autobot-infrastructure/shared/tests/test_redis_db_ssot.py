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
    # #15181: this read `parents[2]`, one level too high — `autobot-infrastructure/`
    # rather than `autobot-infrastructure/shared/`. No checkout has ever had a
    # `redis-databases.yaml` there, so the assert below fired inside the fixture and
    # all four tests in this file ERRORED at setup instead of running. They had never
    # executed once. `parents[0]` is this `tests/` directory and `parents[1]` is
    # `shared/`, which is the directory `config/redis-databases.yaml` actually sits in.
    #
    # Kept as an assert rather than letting `open()` raise: a missing SSOT file must
    # read as "this test could not run", not as an empty mapping that every assertion
    # below would pass over vacuously. `repo_tests/test_module_path_anchors_15181_test.py`
    # now fails on any test module whose `Path(__file__)`-anchored data file is absent,
    # so the next one is caught when it is written rather than by inspection.
    yaml_path = Path(__file__).resolve().parents[1] / "config" / "redis-databases.yaml"
    assert yaml_path.exists(), f"SSOT file not found: {yaml_path}"
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    databases = (data or {}).get("redis_databases", {})
    mapping = {name: cfg["db"] for name, cfg in databases.items() if "db" in cfg}
    # Every test below iterates this mapping, so an empty one would pass all four
    # while comparing nothing — the same vacuous-green as the `assert True` in
    # #15182. Asserted here so a renamed or emptied YAML section is a failure.
    assert mapping, f"{yaml_path.name} declares no `redis_databases` entries carrying a `db` number"
    return mapping


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
