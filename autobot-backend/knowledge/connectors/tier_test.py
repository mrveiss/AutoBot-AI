# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Tests for connector readiness tier (Issue #4421).

Verifies:
  - Every registered connector class declares a ``tier`` class attribute.
  - Expected tier values for each built-in connector.
  - The ``/knowledge_base/connector_types`` endpoint returns tier per type.
  - ``_cfg_to_dict`` includes the tier in API responses.
"""

import os
import sys
from datetime import datetime

import pytest

# ---------------------------------------------------------------------------
# Ensure the autobot-backend package root is on sys.path
# ---------------------------------------------------------------------------
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# Importing the connector modules triggers their @ConnectorRegistry.register
# decorators so the registry is populated for these tests.
from knowledge.connectors import (  # noqa: E402,F401
    audio_connector,
    database,
    file_server,
    notion,
    web_crawler,
)
from knowledge.connectors.base import AbstractConnector  # noqa: E402
from knowledge.connectors.models import ConnectorConfig  # noqa: E402
from knowledge.connectors.registry import ConnectorRegistry  # noqa: E402

# Expected tier assignments (Issue #4421)
_EXPECTED_TIERS = {
    "file_server": 0,
    "web_crawler": 0,
    "audio": 0,
    "notion": 1,
    "database": 2,
}


class TestConnectorTierAttribute:
    """Every registered connector must declare a tier."""

    def test_abstract_base_declares_tier(self):
        assert hasattr(AbstractConnector, "tier")
        assert isinstance(AbstractConnector.tier, int)

    def test_every_registered_connector_has_tier(self):
        # Snapshot the class registry rather than walk instances — we want
        # the source of truth to be the class attribute.
        connectors = dict(ConnectorRegistry._connectors)
        assert connectors, "No connectors registered — imports failed"
        for type_name, klass in connectors.items():
            assert hasattr(klass, "tier"), "Connector %s (%s) missing tier" % (type_name, klass)
            assert isinstance(klass.tier, int), "Connector %s tier must be int, got %r" % (type_name, type(klass.tier))
            assert 0 <= klass.tier <= 2, "Connector %s tier out of range: %d" % (type_name, klass.tier)

    @pytest.mark.parametrize("connector_type,expected", _EXPECTED_TIERS.items())
    def test_expected_tier_per_builtin(self, connector_type, expected):
        klass = ConnectorRegistry._connectors.get(connector_type)
        assert klass is not None, "Connector %s not registered" % connector_type
        assert klass.tier == expected, "Expected %s tier=%d, got %d" % (connector_type, expected, klass.tier)


class TestConnectorConfigTier:
    """ConnectorConfig carries a tier field that defaults to 0."""

    def test_default_tier_is_zero(self):
        cfg = ConnectorConfig(
            connector_id="t-1",
            connector_type="file_server",
            name="t",
            config={},
        )
        assert cfg.tier == 0

    def test_explicit_tier_preserved(self):
        cfg = ConnectorConfig(
            connector_id="t-2",
            connector_type="database",
            name="t",
            config={},
            tier=2,
        )
        assert cfg.tier == 2


class TestApiSerialization:
    """_cfg_to_dict exposes tier via the registered class attribute."""

    def test_cfg_to_dict_includes_tier_from_class(self):
        from api.knowledge_connectors import _cfg_to_dict

        cfg = ConnectorConfig(
            connector_id="api-1",
            connector_type="notion",
            name="My Notion",
            config={"token": "secret", "database_ids": ["x"]},
            created_at=datetime(2026, 1, 1),
        )
        payload = _cfg_to_dict(cfg)
        assert payload["tier"] == 1, "notion connector should surface tier=1 in API payload"

    def test_cfg_to_dict_falls_back_to_cfg_tier_when_type_unknown(self):
        from api.knowledge_connectors import _cfg_to_dict

        cfg = ConnectorConfig(
            connector_id="api-2",
            connector_type="no_such_type",
            name="Unknown",
            config={},
            tier=2,
            created_at=datetime(2026, 1, 1),
        )
        payload = _cfg_to_dict(cfg)
        assert payload["tier"] == 2


class TestConnectorTypesEndpoint:
    """/knowledge_base/connector_types enumerates types with tier."""

    @pytest.mark.asyncio
    async def test_endpoint_returns_tier_per_type(self):
        from api.knowledge_connectors import list_connector_types

        response = await list_connector_types()
        assert "connector_types" in response
        assert response["total"] == len(response["connector_types"])

        by_type = {entry["connector_type"]: entry["tier"] for entry in response["connector_types"]}
        for connector_type, expected in _EXPECTED_TIERS.items():
            assert by_type.get(connector_type) == expected, "endpoint tier mismatch for %s: expected %d, got %r" % (
                connector_type,
                expected,
                by_type.get(connector_type),
            )

    @pytest.mark.asyncio
    async def test_endpoint_sorted_by_tier_then_name(self):
        from api.knowledge_connectors import list_connector_types

        response = await list_connector_types()
        entries = response["connector_types"]
        keys = [(e["tier"], e["connector_type"]) for e in entries]
        assert keys == sorted(keys)
