# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical database pool settings (#12645).

The same 20-line body — read SSOT pool config, fall back to a fixed table —
was duplicated byte-for-byte in `autobot-backend/user_management/database.py`
and `autobot-slm-backend/user_management/database.py`, with a third
tuple-shaped variant in `autobot-slm-backend/config.py`. Three copies of one
fallback table means a tuning change lands in one engine and silently not the
others.

The fallback path gets the most attention here, because it runs exactly when
SSOT config is already failing — the moment a second error is most expensive
and least visible.
"""

from unittest.mock import patch

import pytest

from autobot_shared.ssot_config import database_pool_settings

_KEYS = {"pool_size", "max_overflow", "pool_recycle", "pool_timeout"}


class TestHappyPath:
    def test_returns_all_four_pool_keys(self):
        assert set(database_pool_settings()) == _KEYS

    def test_values_are_ints(self):
        """SQLAlchemy rejects non-int pool arguments at engine construction."""
        assert all(isinstance(v, int) for v in database_pool_settings().values())

    def test_reads_from_ssot_when_available(self):
        import autobot_shared.ssot_config as mod

        cfg = type(
            "C",
            (),
            {
                "database_pool": type(
                    "P", (), {"pool_size": 42, "max_overflow": 7, "pool_recycle": 111, "pool_timeout": 9}
                )()
            },
        )()

        with patch.object(mod, "get_config", return_value=cfg):
            assert database_pool_settings() == {
                "pool_size": 42,
                "max_overflow": 7,
                "pool_recycle": 111,
                "pool_timeout": 9,
            }


class TestFallback:
    """The path that runs when SSOT config is already broken."""

    def test_does_not_raise_when_config_is_unavailable(self):
        """Regression: the first draft referenced an undefined module-level
        `logger`, so this path raised NameError — masking the real failure with
        a second, less informative one."""
        import autobot_shared.ssot_config as mod

        with patch.object(mod, "get_config", side_effect=RuntimeError("ssot down")):
            settings = database_pool_settings()

        assert set(settings) == _KEYS

    def test_fallback_values_are_unchanged_from_the_duplicated_copies(self):
        """This is a de-duplication, not a re-tuning — the numbers must match."""
        import autobot_shared.ssot_config as mod

        with patch.object(mod, "get_config", side_effect=RuntimeError("ssot down")):
            assert database_pool_settings() == {
                "pool_size": 10,
                "max_overflow": 10,
                "pool_recycle": 3600,
                "pool_timeout": 30,
            }

    def test_warns_so_the_fallback_is_not_silent(self, caplog):
        import autobot_shared.ssot_config as mod

        with patch.object(mod, "get_config", side_effect=RuntimeError("ssot down")):
            with caplog.at_level("WARNING"):
                database_pool_settings()

        assert "database pool config" in caplog.text.lower()


@pytest.mark.parametrize(
    "rel",
    [
        "autobot-backend/user_management/database.py",
        "autobot-slm-backend/user_management/database.py",
    ],
)
def test_both_backends_delegate_rather_than_redefine(rel):
    """Neither copy may reimplement the fallback table locally again."""
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / rel).read_text(encoding="utf-8")

    assert "database_pool_settings()" in source, f"{rel} should delegate to the shared helper"
    assert '"pool_recycle": 3600' not in source, f"{rel} still carries its own fallback table"
