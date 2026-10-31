# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Env overrides of the generation timeouts reject values aiohttp misreads (#12979)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent / "generation_http_timeouts.py"

#: env var -> (module attribute, default)
_VARS = {
    "AUTOBOT_GENERATION_REQUEST_TIMEOUT_S": ("GENERATION_TIMEOUT_S", 300.0),
    "AUTOBOT_GENERATION_POLL_TIMEOUT_S": ("POLL_TIMEOUT_S", 30.0),
    "AUTOBOT_GENERATION_CONNECT_TIMEOUT_S": ("CONNECT_TIMEOUT_S", 10.0),
}


def _fresh_module():
    """Execute the module under a private name so the real one is never mutated."""
    spec = importlib.util.spec_from_file_location("generation_http_timeouts_under_test", _PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("bad", ["0", "-1", "nan", "inf", "-inf"])
@pytest.mark.parametrize("var", sorted(_VARS))
def test_invalid_override_falls_back_to_default(monkeypatch, var, bad):
    monkeypatch.setenv(var, bad)
    attr, default = _VARS[var]
    assert getattr(_fresh_module(), attr) == default


@pytest.mark.parametrize("var", sorted(_VARS))
def test_valid_override_is_honoured(monkeypatch, var):
    monkeypatch.setenv(var, "42.5")
    attr, _ = _VARS[var]
    assert getattr(_fresh_module(), attr) == 42.5
