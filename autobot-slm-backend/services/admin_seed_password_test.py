# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SLM_ADMIN_PASSWORD_FILE seeds a fresh install only; an existing admin keeps its password (#19368)."""

import ast
import logging
import secrets
from pathlib import Path

import pytest

from services.admin_seed_password import (
    AdminPasswordFileError,
    password_for_existing_admin,
    password_for_new_admin,
)

_MAIN = Path(__file__).resolve().parents[1] / "main.py"


def _throwaway() -> str:
    """A per-run fixture value: no credential-shaped literal in this file."""
    return secrets.token_hex(8)


@pytest.fixture()
def no_admin_env(monkeypatch):
    monkeypatch.delenv("SLM_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("SLM_ADMIN_PASSWORD_FILE", raising=False)
    return monkeypatch


def _secret_file(tmp_path: Path, value: str) -> Path:
    path = tmp_path / "slm_admin_password"
    path.write_text(value + "\n", encoding="utf-8")
    return path


def test_a_fresh_install_takes_the_file_secret(no_admin_env, tmp_path) -> None:
    value = _throwaway()
    no_admin_env.setenv("SLM_ADMIN_PASSWORD_FILE", str(_secret_file(tmp_path, value)))
    no_admin_env.setenv("SLM_ADMIN_PASSWORD", "")  # the hardened overlay clears it
    assert password_for_new_admin() == value


def test_an_existing_admin_keeps_its_stored_password(no_admin_env, tmp_path, caplog) -> None:
    no_admin_env.setenv("SLM_ADMIN_PASSWORD_FILE", str(_secret_file(tmp_path, _throwaway())))
    with caplog.at_level(logging.INFO, logger="services.admin_seed_password"):
        assert password_for_existing_admin() == ""
    assert "stored password kept" in caplog.text


def test_the_plain_variable_still_wins_and_still_syncs(no_admin_env, tmp_path) -> None:
    value = _throwaway()
    no_admin_env.setenv("SLM_ADMIN_PASSWORD", value)
    no_admin_env.setenv("SLM_ADMIN_PASSWORD_FILE", str(_secret_file(tmp_path, _throwaway())))
    assert password_for_new_admin() == value
    assert password_for_existing_admin() == value


def test_an_unreadable_file_is_a_clear_error_not_a_default(no_admin_env, tmp_path) -> None:
    no_admin_env.setenv("SLM_ADMIN_PASSWORD_FILE", str(tmp_path / "missing"))
    with pytest.raises(AdminPasswordFileError, match="SLM_ADMIN_PASSWORD_FILE .* is unreadable"):
        password_for_new_admin()


def test_an_empty_file_is_a_clear_error(no_admin_env, tmp_path) -> None:
    no_admin_env.setenv("SLM_ADMIN_PASSWORD_FILE", str(_secret_file(tmp_path, "  ")))
    with pytest.raises(AdminPasswordFileError, match="is empty"):
        password_for_new_admin()


def test_the_error_never_carries_the_value(no_admin_env, tmp_path) -> None:
    path = tmp_path / "dir_not_file"
    path.mkdir()
    no_admin_env.setenv("SLM_ADMIN_PASSWORD_FILE", str(path))
    with pytest.raises(AdminPasswordFileError) as info:
        password_for_new_admin()
    assert str(path) in str(info.value)


def test_nothing_set_means_generate(no_admin_env) -> None:
    assert password_for_new_admin() == ""
    assert password_for_existing_admin() == ""


def _calls_in(node: ast.AST) -> set[str]:
    return {n.func.id for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}


def test_main_seeds_through_the_one_resolver() -> None:
    """main.py's _ensure_admin_user reads neither variable itself (#19318, #19368)."""
    tree = ast.parse(_MAIN.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "_ensure_admin_user")
    calls = _calls_in(fn)
    assert {"password_for_existing_admin", "password_for_new_admin"} <= calls
    getenv = [n for n in ast.walk(fn) if isinstance(n, ast.Attribute) and n.attr in ("getenv", "environ")]
    assert "env" not in calls and not getenv, "_ensure_admin_user reads the environment directly"
