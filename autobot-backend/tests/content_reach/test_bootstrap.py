# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for content_reach.bootstrap — default source registry assembler (#10932)."""

from content_reach.bootstrap import build_default_registry, register_default_sources
from content_reach.registry import ContentSourceRegistry
from source_attribution import SourceType

_EXPECTED_SOURCES = {"web_search", "web_page", "youtube", "reddit", "social"}

_SOURCE_TYPE_MAP = {
    "web_search": SourceType.WEB_SEARCH,
    "web_page": SourceType.WEB_PAGE,
    "youtube": SourceType.YOUTUBE,
    "reddit": SourceType.REDDIT,
    "social": SourceType.SOCIAL,
}


def test_build_default_registry_has_all_sources():
    registry = build_default_registry()
    assert set(registry.list_sources()) == _EXPECTED_SOURCES


def test_each_chain_source_type():
    registry = build_default_registry()
    for source_name, expected_type in _SOURCE_TYPE_MAP.items():
        chain = registry.get_chain(source_name)
        assert chain is not None, f"chain for {source_name!r} is missing"
        assert chain.source_type == expected_type, f"{source_name}: expected {expected_type}, got {chain.source_type}"


def test_register_default_sources_into_existing():
    registry = ContentSourceRegistry()
    register_default_sources(registry)
    assert set(registry.list_sources()) == _EXPECTED_SOURCES
