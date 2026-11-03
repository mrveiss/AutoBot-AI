# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#16299: a new SLM admin never gets a guessable password, no restart is stopped, and an existing one is left alone."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from services import admin_seed_password as seed

_STRONG = "kV9-long-unique-value"  # pragma: allowlist secret


@pytest.mark.parametrize("weak", ["autobot123", "zq-short-1", "qwerty123"])
def test_a_guessable_password_stops_a_new_admin_without_naming_it(monkeypatch, weak: str) -> None:
    monkeypatch.setenv("SLM_ADMIN_PASSWORD", weak)
    monkeypatch.delenv("SLM_ADMIN_PASSWORD_FILE", raising=False)
    with patch.object(seed, "logger") as logger:
        assert seed.password_for_new_admin() == ""
    assert "refused" in logger.error.call_args.args[0]
    assert weak not in str(logger.error.call_args)


def test_a_guessable_file_secret_stops_it_too(monkeypatch, tmp_path) -> None:
    secret = tmp_path / "pw"
    secret.write_text("admin\n", encoding="utf-8")
    monkeypatch.delenv("SLM_ADMIN_PASSWORD", raising=False)
    monkeypatch.setenv("SLM_ADMIN_PASSWORD_FILE", str(secret))
    assert seed.password_for_new_admin() == ""


def test_a_strong_password_and_no_password_pass(monkeypatch) -> None:
    monkeypatch.delenv("SLM_ADMIN_PASSWORD_FILE", raising=False)
    monkeypatch.setenv("SLM_ADMIN_PASSWORD", _STRONG)
    assert seed.password_for_new_admin() == _STRONG
    monkeypatch.delenv("SLM_ADMIN_PASSWORD")
    assert seed.password_for_new_admin() == ""


def test_an_existing_admin_is_never_checked(monkeypatch) -> None:
    monkeypatch.setenv("SLM_ADMIN_PASSWORD", "admin")
    assert seed.password_for_existing_admin() == "admin"


def test_the_random_password_notice_names_the_way_back() -> None:
    """#20527: the role installs this command at /usr/local/bin/autobot-admin."""
    assert "autobot-admin reset-password admin" in seed.RANDOM_ADMIN_NOTICE


def test_the_notice_is_what_startup_logs() -> None:
    main = Path(seed.__file__).resolve().parent.parent / "main.py"
    assert "logger.critical(RANDOM_ADMIN_NOTICE)" in main.read_text(encoding="utf-8")
    role = main.parent / "ansible/roles/slm_manager/tasks/main.yml"
    assert "dest: /usr/local/bin/autobot-admin" in role.read_text(encoding="utf-8")
