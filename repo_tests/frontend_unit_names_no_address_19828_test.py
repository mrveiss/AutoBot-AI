# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#19828: the frontend unit holds no address, and the fleet-address guard covers it with no allowance."""

from __future__ import annotations

import re

from repo_tests._paths import repo_root

_UNIT = "autobot-infrastructure/shared/scripts/systemd/autobot-frontend.service"
_LITERAL = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")


def _unit() -> str:
    return (repo_root() / _UNIT).read_text(encoding="utf-8")


def test_the_unit_holds_no_address() -> None:
    assert not _LITERAL.findall(_unit())


def test_the_backend_settings_come_from_the_deployed_env_file() -> None:
    assert "EnvironmentFile=-/etc/autobot/autobot-frontend.env" in _unit()
    assert "VITE_BACKEND_HOST=" not in _unit()


def test_the_guard_gives_this_unit_no_allowance() -> None:
    guard = (repo_root() / "tools/lint/check_fleet_addressing_uncovered.py").read_text(encoding="utf-8")
    assert _UNIT not in guard
