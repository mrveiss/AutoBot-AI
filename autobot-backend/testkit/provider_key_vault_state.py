# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every backend test starts against an explicit empty, reachable provider-key vault (#18094).

In production a process that has not read the vault hydrates on its first key resolution, and a
DB it cannot reach is an outage that refuses keys. Unit tests have no vault DB, so without this
every test that resolves a key would attempt that read and be refused. The state is set here, in
the test harness, not by a production gate: a test that exercises hydration or refusal sets its
own state on top (``services/provider_key_*_18094_test.py``).
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture(autouse=True)
def empty_reachable_provider_key_vault(monkeypatch):
    """Empty caches, vault state ``reachable``; restored after the test by monkeypatch."""
    try:
        vault = importlib.import_module("services.provider_key_vault")
    except ImportError:  # a test that replaced the import path resolves no key through it either
        yield
        return
    monkeypatch.setattr(vault, "_hydrated_keys", {})
    monkeypatch.setattr(vault, "_unreadable_keys", set())
    monkeypatch.setattr(vault, "_env_fallback_logged", set())
    monkeypatch.setattr(vault, "_vault_state", vault.VAULT_REACHABLE)
    yield
