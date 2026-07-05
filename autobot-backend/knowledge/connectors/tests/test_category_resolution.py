# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for ConnectorRegistry.resolve_by_category — Issue #10539.

Verifies:
  - resolve_by_category returns configured (live) instances for a category.
  - resolve_by_category returns empty list for an unconfigured category.
  - resolve_by_category is case-insensitive and strips surrounding whitespace.
  - resolve_by_category returns empty list for an unknown category.
  - CATEGORY_MAP is exported from the package.
  - Existing exact-type resolution (get / list_types) is unaffected.
"""

import os
import sys
from unittest.mock import MagicMock

import pytest

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from knowledge.connectors.registry import CATEGORY_MAP, ConnectorRegistry  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_instance(connector_type: str, connector_id: str) -> MagicMock:
    """Build a minimal mock connector instance."""
    cfg = MagicMock()
    cfg.connector_type = connector_type
    cfg.connector_id = connector_id
    instance = MagicMock()
    instance.config = cfg
    return instance


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_instances():
    """Isolate each test by clearing the live-instance registry."""
    original = dict(ConnectorRegistry._instances)
    ConnectorRegistry._instances.clear()
    yield
    ConnectorRegistry._instances.clear()
    ConnectorRegistry._instances.update(original)


# ---------------------------------------------------------------------------
# CATEGORY_MAP contract
# ---------------------------------------------------------------------------


class TestCategoryMap:
    def test_exported_from_registry(self):
        assert isinstance(CATEGORY_MAP, dict)

    def test_exported_from_package(self):
        from knowledge.connectors import CATEGORY_MAP as pkg_map

        assert pkg_map is CATEGORY_MAP

    def test_known_categories_present(self):
        for category in ("cloud storage", "source control", "wiki", "knowledge base"):
            assert category in CATEGORY_MAP, "CATEGORY_MAP missing %r" % category

    def test_cloud_storage_members(self):
        assert set(CATEGORY_MAP["cloud storage"]) == {"gdrive", "onedrive", "nextcloud"}

    def test_source_control_members(self):
        assert set(CATEGORY_MAP["source control"]) == {"gitlab", "gitea"}

    def test_wiki_members(self):
        assert "notion" in CATEGORY_MAP["wiki"]

    def test_knowledge_base_members(self):
        kb = CATEGORY_MAP["knowledge base"]
        assert "notion" in kb
        assert "file_server" in kb
        assert "web_crawler" in kb

    def test_all_types_are_real(self):
        """Every type listed in CATEGORY_MAP must be a real connector type."""
        # We cannot import all connectors in the bare test context (they need
        # Redis/other infra), so we just verify the strings are non-empty
        # and match the known canonical list.
        known_types = {
            "gdrive",
            "onedrive",
            "nextcloud",
            "gitlab",
            "gitea",
            "notion",
            "file_server",
            "web_crawler",
            "database",
            "audio",
            "external_adapter",
        }
        for category, types in CATEGORY_MAP.items():
            for t in types:
                assert t in known_types, "CATEGORY_MAP[%r] contains unknown type %r" % (category, t)


# ---------------------------------------------------------------------------
# resolve_by_category — live-instance filtering
# ---------------------------------------------------------------------------


class TestResolveByCategory:
    def test_returns_empty_for_unconfigured_category(self):
        result = ConnectorRegistry.resolve_by_category("cloud storage")
        assert result == []

    def test_returns_matching_instance(self):
        instance = _make_instance("gdrive", "gdrive-1")
        ConnectorRegistry._instances["gdrive-1"] = instance

        result = ConnectorRegistry.resolve_by_category("cloud storage")
        assert instance in result

    def test_returns_multiple_matching_instances(self):
        gdrive = _make_instance("gdrive", "gdrive-1")
        onedrive = _make_instance("onedrive", "onedrive-1")
        ConnectorRegistry._instances["gdrive-1"] = gdrive
        ConnectorRegistry._instances["onedrive-1"] = onedrive

        result = ConnectorRegistry.resolve_by_category("cloud storage")
        assert set(result) == {gdrive, onedrive}

    def test_excludes_instances_from_other_categories(self):
        gitlab = _make_instance("gitlab", "gl-1")
        gdrive = _make_instance("gdrive", "gd-1")
        ConnectorRegistry._instances["gl-1"] = gitlab
        ConnectorRegistry._instances["gd-1"] = gdrive

        result = ConnectorRegistry.resolve_by_category("cloud storage")
        assert gdrive in result
        assert gitlab not in result

    def test_unknown_category_returns_empty(self):
        instance = _make_instance("gdrive", "gdrive-1")
        ConnectorRegistry._instances["gdrive-1"] = instance

        result = ConnectorRegistry.resolve_by_category("nonexistent category")
        assert result == []

    def test_case_insensitive_lookup(self):
        instance = _make_instance("gdrive", "gdrive-1")
        ConnectorRegistry._instances["gdrive-1"] = instance

        for variant in ("Cloud Storage", "CLOUD STORAGE", "cloud storage", "Cloud storage"):
            assert instance in ConnectorRegistry.resolve_by_category(variant), (
                "Expected instance for category variant %r" % variant
            )

    def test_strips_surrounding_whitespace(self):
        instance = _make_instance("gdrive", "gdrive-1")
        ConnectorRegistry._instances["gdrive-1"] = instance

        assert instance in ConnectorRegistry.resolve_by_category("  cloud storage  ")

    def test_knowledge_base_multiple_types(self):
        notion = _make_instance("notion", "notion-1")
        fs = _make_instance("file_server", "fs-1")
        ConnectorRegistry._instances["notion-1"] = notion
        ConnectorRegistry._instances["fs-1"] = fs

        result = ConnectorRegistry.resolve_by_category("knowledge base")
        assert notion in result
        assert fs in result

    def test_source_control_gitlab_and_gitea(self):
        gl = _make_instance("gitlab", "gl-1")
        gt = _make_instance("gitea", "gt-1")
        ConnectorRegistry._instances["gl-1"] = gl
        ConnectorRegistry._instances["gt-1"] = gt

        result = ConnectorRegistry.resolve_by_category("source control")
        assert set(result) == {gl, gt}


# ---------------------------------------------------------------------------
# Backward-compat: existing exact-type resolution unaffected
# ---------------------------------------------------------------------------


class TestExistingResolutionUnaffected:
    def test_get_still_works_by_id(self):
        instance = _make_instance("gdrive", "gdrive-1")
        ConnectorRegistry._instances["gdrive-1"] = instance

        assert ConnectorRegistry.get("gdrive-1") is instance

    def test_list_instances_unaffected(self):
        instance = _make_instance("notion", "notion-1")
        ConnectorRegistry._instances["notion-1"] = instance

        assert "notion-1" in ConnectorRegistry.list_instances()
