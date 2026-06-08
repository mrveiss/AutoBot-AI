# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Tests for ConnectorRegistry public API — Issue #5057.

Verifies:
  - ``registered_types()`` returns an immutable view containing every
    registered connector class.
  - ``get_registered_class(known)`` returns the correct class.
  - ``get_registered_class(unknown)`` returns ``None`` (no KeyError).
"""

import os
import sys
from types import MappingProxyType

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
from knowledge.connectors.registry import ConnectorRegistry  # noqa: E402


class TestRegisteredTypes:
    """``registered_types()`` exposes all registered classes."""

    def test_returns_mapping_proxy(self):
        view = ConnectorRegistry.registered_types()
        assert isinstance(view, MappingProxyType)

    def test_view_is_read_only(self):
        view = ConnectorRegistry.registered_types()
        with pytest.raises(TypeError):
            view["new_type"] = object  # type: ignore[index]

    def test_contains_every_builtin(self):
        view = ConnectorRegistry.registered_types()
        for type_name in (
            "file_server",
            "web_crawler",
            "audio",
            "notion",
            "database",
        ):
            assert type_name in view, "registered_types() missing built-in %s" % type_name

    def test_classes_match_private_dict(self):
        # Source of truth inside this test is the private dict — the public
        # API must surface the same objects.
        view = ConnectorRegistry.registered_types()
        for type_name, klass in ConnectorRegistry._connectors.items():
            assert view[type_name] is klass


class TestGetRegisteredClass:
    """``get_registered_class()`` is a safe lookup with None fallback."""

    def test_known_type_returns_class(self):
        klass = ConnectorRegistry.get_registered_class("notion")
        assert klass is not None
        assert klass is ConnectorRegistry._connectors["notion"]

    def test_unknown_type_returns_none(self):
        assert ConnectorRegistry.get_registered_class("no_such_type") is None

    def test_empty_string_returns_none(self):
        assert ConnectorRegistry.get_registered_class("") is None
