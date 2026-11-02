# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The LLM registry build skips a refused provider and still registers its siblings (#18094)."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def refusing_openai(monkeypatch):
    """OPENAI_API_KEY is held by the vault but unreadable; ANTHROPIC_API_KEY resolves; the rest are unset."""
    import services.provider_key_vault as vault_mod

    def _resolve(name: str, fallback: str = "") -> str:
        if name == "OPENAI_API_KEY":
            raise vault_mod.VaultKeyUnavailableError(name)
        return "anthropic-key" if name == "ANTHROPIC_API_KEY" else ""

    monkeypatch.setattr(vault_mod, "resolve_provider_key", _resolve)


def test_the_refused_provider_is_skipped_and_its_siblings_register(refusing_openai, caplog) -> None:
    from llm_shared import provider_registry

    registry = MagicMock()
    with caplog.at_level(logging.ERROR):
        provider_registry._populate_default_providers(registry)

    registered = [call.args[0].provider_name for call in registry.register.call_args_list]
    assert "anthropic" in registered
    assert "openai" not in registered
    assert "OPENAI_API_KEY provider not registered -- vault unavailable" in caplog.text
