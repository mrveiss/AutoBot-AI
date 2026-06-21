# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the LLM key-rotation interval resolver (#10415).

The interval env var defaults to "" in ssot_config, so the old
``int(config.llm_key_rotation_interval_minutes)`` at module import raised
ValueError on every startup and silently disabled the scheduler.

conftest stubs the whole ``services`` package (heavy import chain), so we load
the module fresh from its file with apscheduler stubbed to exercise the real
resolver logic.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_MODULE_PATH = Path(__file__).with_name("llm_key_rotation_scheduler.py")


def _load_real_module():
    # Stub apscheduler (not installed in the test env) so the import succeeds.
    aps = types.ModuleType("apscheduler.schedulers.asyncio")
    aps.AsyncIOScheduler = MagicMock
    sys.modules.setdefault("apscheduler", types.ModuleType("apscheduler"))
    sys.modules.setdefault("apscheduler.schedulers", types.ModuleType("apscheduler.schedulers"))
    sys.modules["apscheduler.schedulers.asyncio"] = aps
    spec = importlib.util.spec_from_file_location("_lkr_real_under_test", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("", 60),
        ("   ", 60),
        ("abc", 60),
        ("0", 60),
        ("-5", 60),
        ("30", 30),
        ("120", 120),
        (None, 60),
    ],
)
def test_resolve_rotation_interval_minutes(monkeypatch, raw, expected):
    mod = _load_real_module()
    monkeypatch.setattr(mod.config, "llm_key_rotation_interval_minutes", raw, raising=False)
    assert mod._resolve_rotation_interval_minutes() == expected
