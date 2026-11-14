# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which tracing observers get registered at import, and that nothing there can stop the app (#19933)."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

KEY = "ls-" + "Qx9" * 12  # built at runtime: a literal key trips the secret scanner
LF_HOST = "http://lf.example:3000"


@pytest.fixture()
def registered(monkeypatch):
    """Run registration against a fake registry and fake client packages; yield the registered list."""
    from llm_shared.observability import tracing_registration as reg

    for name in (
        "LANGSMITH_API_KEY",
        "LANGSMITH_API_URL",
        "LANGFUSE_HOST",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("AUTOBOT_LLM_TRACING_ALLOW_EXTERNAL", raising=False)
    monkeypatch.delenv("AUTOBOT_LLM_TRACING_ALLOWED_ORIGINS", raising=False)
    got: list = []
    mods = {"langsmith": MagicMock(), "langfuse": MagicMock()}
    with patch.object(reg, "register", got.append), patch.dict("sys.modules", mods):
        yield reg, got


def test_key_alone_with_the_default_url_registers_nothing(registered, monkeypatch):
    reg, got = registered
    monkeypatch.setenv("LANGSMITH_API_KEY", KEY)
    reg.register_tracing_observers()
    assert got == []


def test_an_allowed_host_registers_the_observer(registered, monkeypatch):
    reg, got = registered
    monkeypatch.setenv("LANGFUSE_HOST", LF_HOST)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pub")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", KEY)
    monkeypatch.setenv("AUTOBOT_LLM_TRACING_ALLOWED_ORIGINS", LF_HOST)
    reg.register_tracing_observers()
    assert [type(o).__name__ for o in got] == ["LangFuseObserver"]


def test_a_failing_policy_registers_nothing_and_does_not_raise(registered, monkeypatch):
    reg, got = registered
    monkeypatch.setenv("LANGSMITH_API_KEY", KEY)
    with patch.object(reg, "destination_allowed", side_effect=RuntimeError(KEY)):
        reg.register_tracing_observers()
    assert got == []


def test_a_failing_origin_lookup_does_not_break_registration(registered, monkeypatch):
    reg, got = registered
    monkeypatch.setenv("LANGSMITH_API_KEY", KEY)
    monkeypatch.setenv("AUTOBOT_LLM_TRACING_ALLOW_EXTERNAL", "true")
    with patch("llm_shared.observability.tracing_policy.is_public_url", side_effect=OSError("dns")):
        reg.register_tracing_observers()
    assert got == []


def test_a_missing_client_package_is_a_warning_not_an_import_error(registered, monkeypatch):
    reg, got = registered
    monkeypatch.setenv("LANGFUSE_HOST", LF_HOST)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pub")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", KEY)
    monkeypatch.setenv("AUTOBOT_LLM_TRACING_ALLOWED_ORIGINS", LF_HOST)
    with patch.dict("sys.modules", {"langfuse": None}):
        reg.register_tracing_observers()
    assert got == []


def test_logs_on_the_active_and_failing_paths_carry_no_key(registered, monkeypatch, caplog):
    reg, got = registered
    caplog.set_level(logging.DEBUG)
    monkeypatch.setenv("LANGFUSE_HOST", LF_HOST)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pub-" + KEY)
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", KEY)
    monkeypatch.setenv("LANGSMITH_API_KEY", KEY)
    monkeypatch.setenv("AUTOBOT_LLM_TRACING_ALLOWED_ORIGINS", LF_HOST)
    reg.register_tracing_observers()
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert len(got) == 1 and "LLM tracing active" in logged
    assert KEY not in logged and KEY not in caplog.text
