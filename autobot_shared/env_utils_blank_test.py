# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Blank-means-absent coercion for config-sourced values (#12782).

Six tuning knobs logged an "invalid value" warning on every boot while quietly
using their defaults. None of them was misconfigured: ``ssot_config`` declares
optional knobs as ``str = Field(default="")``, so an *unset* knob arrives as
``""`` rather than ``None``. Every read site guarded with ``if raw is None``,
which never fires for a blank, and ``int("")`` then raised.

The same defect by a different route (blank env var defeating a default
argument) is what ``env_raw`` already covers, and what broke REDIS_HOST in
#12778. ``blank_to_none`` is that rule as one function so both routes share a
single definition of "blank".
"""

import pytest

from autobot_shared.env_utils import blank_to_none, env_raw


@pytest.mark.parametrize("value", ["", "   ", "\t", "\n", None])
def test_blank_values_collapse_to_none(value):
    """An unset knob must read as absent, not as a value that fails at parse time."""
    assert blank_to_none(value) is None


@pytest.mark.parametrize("value,expected", [("0", "0"), ("50", "50"), ("  8  ", "8"), ("false", "false")])
def test_real_values_survive_and_are_stripped(value, expected):
    """'0' and 'false' are meaningful settings — they must not be treated as blank."""
    assert blank_to_none(value) == expected


def test_non_string_values_are_coerced():
    """ssot_config fields are typed str, but callers may pass ints — do not crash."""
    assert blank_to_none(0) == "0"
    assert blank_to_none(50) == "50"


def test_env_raw_delegates_to_the_same_rule(monkeypatch):
    """One definition of "blank", not two that can drift apart."""
    monkeypatch.setenv("AUTOBOT_TEST_BLANK", "   ")
    assert env_raw("AUTOBOT_TEST_BLANK") is None

    monkeypatch.setenv("AUTOBOT_TEST_BLANK", "value")
    assert env_raw("AUTOBOT_TEST_BLANK") == "value"


class TestReadSitesTreatBlankAsAbsent:
    """The six settings #12782 named must fall back silently, not warn every boot."""

    @pytest.mark.parametrize(
        "module_path,symbol",
        [
            ("autobot-backend/chat_history/cache.py", "config.misc.chat_session_cache_ttl"),
            ("autobot-backend/chat_history/cache.py", "config.misc.chat_recent_max_entries"),
            (
                "autobot-backend/services/llm_key_rotation_scheduler.py",
                "config.llm_key_rotation_interval_minutes",
            ),
            (
                "autobot-backend/api/codebase_analytics/chromadb_storage.py",
                "config.codebase_index_parallel_batches",
            ),
            (
                "autobot-backend/api/codebase_analytics/file_analyzer.py",
                "config.codebase_index_parallel_files",
            ),
            (
                "autobot-backend/api/codebase_analytics/scanner.py",
                "config.codebase_scan_parallel_files",
            ),
        ],
    )
    def test_knob_is_read_through_blank_to_none(self, module_path, symbol):
        """Source-level assertion: a bare read would reintroduce the boot warning.

        Checked statically rather than by import because these are module-level
        constants evaluated at import time — re-reading them under a patched
        config would require reloading half the backend.
        """
        from pathlib import Path

        source = (Path(__file__).resolve().parents[1] / module_path).read_text(encoding="utf-8")

        assert f"blank_to_none({symbol})" in source, f"{module_path}: {symbol} is not blank-guarded"
