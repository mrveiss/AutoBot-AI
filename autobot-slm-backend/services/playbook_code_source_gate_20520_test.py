# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20520: with no code_source a deploy refuses, and never reads the deployed tree."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

_SERVICES = Path(__file__).resolve().parent


def _load(name: str, alias: str):
    """The real module: the package conftest stubs ``services.*``, so a plain import gets a stub."""
    spec = importlib.util.spec_from_file_location(alias, _SERVICES / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def playbook_executor(monkeypatch):
    monkeypatch.setitem(
        sys.modules, "services.playbook_code_source_gate", _load("playbook_code_source_gate", "gate_under_20520_test")
    )
    return _load("playbook_executor", "playbook_executor_under_20520_test")


def _executor(playbook_executor, tmp_path: Path, monkeypatch, code_source_exists: bool):
    fallback = tmp_path / "installed" / "ansible"
    fallback.mkdir(parents=True)
    (fallback / "site.yml").write_text("---\n", encoding="utf-8")
    source = tmp_path / "code_source" / "ansible"
    if code_source_exists:
        source.mkdir(parents=True)
    monkeypatch.setattr(playbook_executor, "FALLBACK_ANSIBLE_DIR", fallback)
    monkeypatch.setattr(playbook_executor, "DEFAULT_CODE_SOURCE_ANSIBLE_DIR", str(source))
    monkeypatch.delenv("SLM_ANSIBLE_DIR", raising=False)
    return playbook_executor.PlaybookExecutor()


def test_no_code_source_refuses_naming_how_to_create_it_before_any_sync(
    playbook_executor, tmp_path, monkeypatch
) -> None:
    executor = _executor(playbook_executor, tmp_path, monkeypatch, code_source_exists=False)
    with patch.object(executor, "_update_code_source", AsyncMock()) as sync:
        result = asyncio.run(executor.execute_playbook("site.yml"))
    assert result["success"] is False and "install.sh" in result["output"]
    sync.assert_not_awaited()


def test_contrast_a_code_source_does_not_get_this_refusal(playbook_executor, tmp_path, monkeypatch) -> None:
    """It goes on to look for the playbook there, which this test did not put in place."""
    executor = _executor(playbook_executor, tmp_path, monkeypatch, code_source_exists=True)
    with patch.object(executor, "_update_code_source", AsyncMock(return_value=None)) as sync:
        try:
            asyncio.run(executor.execute_playbook("site.yml"))
        except FileNotFoundError as missing:
            assert "code_source" in str(missing)
    sync.assert_awaited_once()


def test_contrast_an_explicit_directory_is_never_refused(playbook_executor, tmp_path, monkeypatch) -> None:
    fallback = tmp_path / "installed" / "ansible"
    fallback.mkdir(parents=True)
    monkeypatch.setattr(playbook_executor, "FALLBACK_ANSIBLE_DIR", fallback)
    executor = playbook_executor.PlaybookExecutor(ansible_dir=fallback)
    with patch.object(executor, "_update_code_source", AsyncMock(return_value=None)) as sync:
        try:
            asyncio.run(executor.execute_playbook("absent.yml"))
        except FileNotFoundError:
            pass
    sync.assert_awaited_once()
