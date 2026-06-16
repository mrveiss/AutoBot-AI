# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for cloud ASR provider selection (Issue #10147)."""

import os
from unittest.mock import patch

import pytest

from voice_processing.providers import selection


@pytest.fixture(autouse=True)
def _reset_override():
    """Ensure the in-process override never leaks between tests."""
    selection.set_active_provider(None)
    yield
    selection.set_active_provider(None)


def test_env_selected_reads_and_normalizes():
    with patch.dict(os.environ, {"TRANSCRIBER_ASR_PROVIDER": "  Deepgram "}):
        assert selection.get_active_provider_id() == "deepgram"


def test_env_unset_is_none():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("TRANSCRIBER_ASR_PROVIDER", None)
        assert selection.get_active_provider_id() is None


def test_override_beats_env():
    with patch.dict(os.environ, {"TRANSCRIBER_ASR_PROVIDER": "google"}):
        selection.set_active_provider("assemblyai")
        assert selection.get_active_provider_id() == "assemblyai"


def test_set_active_provider_rejects_unknown():
    with pytest.raises(ValueError):
        selection.set_active_provider("not-a-provider")


def test_list_available_reflects_configuration():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("DEEPGRAM_API_KEY", None)
        os.environ.pop("ASSEMBLYAI_API_KEY", None)
        os.environ["DEEPGRAM_API_KEY"] = "dg-key"
        providers = {p["id"]: p for p in selection.list_available_providers()}
    assert set(providers) == {"deepgram", "assemblyai", "google"}
    assert providers["deepgram"]["configured"] is True
    assert providers["assemblyai"]["configured"] is False
    assert providers["deepgram"]["languages"]  # non-empty


def test_get_selected_none_when_unconfigured():
    with patch.dict(os.environ, {"TRANSCRIBER_ASR_PROVIDER": "deepgram"}, clear=False):
        os.environ.pop("DEEPGRAM_API_KEY", None)
        assert selection.get_selected_cloud_provider() is None


def test_get_selected_returns_configured_instance():
    with patch.dict(os.environ, {"TRANSCRIBER_ASR_PROVIDER": "deepgram", "DEEPGRAM_API_KEY": "dg-key"}):
        provider = selection.get_selected_cloud_provider()
    assert provider is not None
    assert provider.is_configured
