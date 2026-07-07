# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for Part A boot wiring — health probe import + registry init (#10932)."""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# A1 — importing content_reach.health registers the CONTENT_REACH probe
# ---------------------------------------------------------------------------


def test_health_import_registers_probe() -> None:
    """import content_reach.health → 'content_reach' appears in list_registered_probes()."""
    import content_reach.health  # noqa: F401 — side-effect: registers the probe
    from api.system_health import list_registered_probes

    assert "content_reach" in list_registered_probes()


# ---------------------------------------------------------------------------
# A2 — register_default_sources populates all 5 sources
# ---------------------------------------------------------------------------


@pytest.fixture()
def _isolated_registry():
    """Yield a fresh ContentSourceRegistry; restore empty state after the test."""
    from content_reach.registry import get_content_source_registry

    reg = get_content_source_registry()
    reg.clear()
    yield reg
    reg.clear()


def test_register_default_sources_populates_five_sources(_isolated_registry) -> None:
    """register_default_sources adds all 5 expected sources to a cleared registry."""
    from content_reach.bootstrap import register_default_sources

    register_default_sources(_isolated_registry)
    sources = _isolated_registry.list_sources()
    assert set(sources) == {"web_search", "web_page", "youtube", "reddit", "social"}


def test_registry_starts_empty_after_clear(_isolated_registry) -> None:
    """Registry is empty after clear() — fixture isolation check."""
    assert _isolated_registry.list_sources() == {}
