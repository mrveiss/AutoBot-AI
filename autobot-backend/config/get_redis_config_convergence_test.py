# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Regression tests for Issue #12748 (get_redis_config fork convergence).

Confirms the re-entry-safe _ConfigStub.get_redis_config() returns the
identical superset shape/values as the canonical
config.service_config.ServiceConfigMixin.get_redis_config() (reached via
unified_config_manager), instead of the pre-fix broken/partial dict that
referenced nonexistent SSOT attributes.
"""

import config as config_pkg


def test_config_stub_redis_config_matches_canonical_shape():
    """_ConfigStub.get_redis_config() must return the same keys as canonical."""
    stub_result = config_pkg._ConfigStub().get_redis_config()
    canonical_result = config_pkg.unified_config_manager.get_redis_config()

    assert set(stub_result.keys()) == set(canonical_result.keys())


def test_config_stub_redis_config_matches_canonical_values():
    """_ConfigStub.get_redis_config() must resolve the same values as canonical."""
    stub_result = config_pkg._ConfigStub().get_redis_config()
    canonical_result = config_pkg.unified_config_manager.get_redis_config()

    assert stub_result == canonical_result


def test_config_stub_redis_config_has_no_attribute_error():
    """Regression: pre-fix stub read config.redis_enabled/config.redis_db_main,
    attributes that do not exist on AutoBotConfig and raised AttributeError.
    """
    result = config_pkg._ConfigStub().get_redis_config()

    assert isinstance(result["enabled"], bool)
    assert isinstance(result["db"], int)
    assert "host" in result
    assert "port" in result
    assert "password" in result
