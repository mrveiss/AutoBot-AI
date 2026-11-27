# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Link pipeline test fixtures."""

import pytest


@pytest.fixture(autouse=True)
def _third_party_fast_paths_on(monkeypatch):
    """These tests exercise the opt-in third-party fast path, so the gate is on (#21850)."""
    monkeypatch.setattr("services.web_research_config.third_party_fast_paths_enabled", lambda: True)
