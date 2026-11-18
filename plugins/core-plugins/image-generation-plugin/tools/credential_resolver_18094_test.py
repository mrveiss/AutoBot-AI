# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The image tool reads provider keys through the injected resolver when present (#18094)."""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent / "generate_image.py"
_spec = importlib.util.spec_from_file_location("gi_cred_under_test", _PATH)
gi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gi)

_VALUE = "resolver-value-5d41402a"  # pragma: allowlist secret
_ENV = "env-value-7d793037"  # pragma: allowlist secret


@pytest.fixture(autouse=True)
def _standalone(monkeypatch):
    gi.set_credential_resolver(None)
    for name in ("OPENAI_API_KEY", "FLUX_API_KEY", "STABILITY_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    yield
    gi.set_credential_resolver(None)


def test_standalone_reads_the_environment_and_defaults_to_empty(monkeypatch) -> None:
    assert gi.read_provider_key("FLUX_API_KEY") == ""
    monkeypatch.setenv("FLUX_API_KEY", _ENV)
    assert gi.read_provider_key("FLUX_API_KEY") == _ENV


def test_the_injected_resolver_is_used_instead_of_the_environment(monkeypatch) -> None:
    monkeypatch.setenv("FLUX_API_KEY", _ENV)
    seen: list[str] = []

    def _resolver(name: str) -> str:
        seen.append(name)
        return _VALUE

    gi.set_credential_resolver(_resolver)
    assert gi.read_provider_key("FLUX_API_KEY") == _VALUE
    assert seen == ["FLUX_API_KEY"]


def test_clearing_the_resolver_restores_standalone_semantics() -> None:
    gi.set_credential_resolver(lambda name: _VALUE)
    gi.set_credential_resolver(None)
    assert gi.read_provider_key("OPENAI_API_KEY") == ""


@pytest.mark.asyncio
async def test_a_missing_key_fails_by_name_only_and_never_logs_a_value(caplog) -> None:
    gi.set_credential_resolver(lambda name: "")
    with caplog.at_level(logging.DEBUG):
        result = await gi.GenerateImageTool().execute({"prompt": "x", "provider": "flux"})
    assert result.success is False and result.error == "FLUX_API_KEY not configured"
    assert _VALUE not in caplog.text


@pytest.mark.asyncio
async def test_a_resolver_error_does_not_leak_the_value(caplog) -> None:
    def _refuse(name: str) -> str:
        raise ValueError("not an image-provider credential name")

    gi.set_credential_resolver(_refuse)
    with caplog.at_level(logging.DEBUG):
        result = await gi.GenerateImageTool().execute({"prompt": "x", "provider": "dalle"})
    assert result.success is False
    assert _VALUE not in (result.error or "") and _VALUE not in caplog.text
