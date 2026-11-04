# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A deployment missing the secrets root key fails loudly at startup, not on first credential read (#17981).

``ValidationMixin.validate_startup`` is what ``initialization/lifespan._init_config`` runs before any service
starts, and ``_init_config`` raises when the result is not ``valid``. The check reuses the one reader,
``secrets_envelope.load_root_key``, and its message names the setting, never the value.

Every test isolates the root key as the ONLY variable: the file-config checks are replaced by a clean
result, so ``valid`` can only flip because of the key. An earlier version validated an empty config whose
own missing-key errors already made the result invalid, so it passed while the root-key error was recorded
without marking the result invalid.
"""

from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import config.validation as validation
from autobot_shared.secrets_envelope import ROOT_KEY_ENV
from config.validation import ConfigValidationResult, ValidationMixin
from initialization import lifespan

_GOOD = base64.urlsafe_b64encode(bytes(range(32))).decode()


class _Config(ValidationMixin):
    _config: dict = {}


@pytest.fixture(autouse=True)
def _only_the_root_key_varies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(validation, "validate_startup_config", lambda _raw: ConfigValidationResult())
    monkeypatch.setattr(validation, "log_startup_config_summary", lambda _raw: None)


def _set(monkeypatch: pytest.MonkeyPatch, value: str | None) -> None:
    if value is None:
        monkeypatch.delenv(ROOT_KEY_ENV, raising=False)
    else:
        monkeypatch.setenv(ROOT_KEY_ENV, value)


def test_a_usable_root_key_leaves_startup_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    _set(monkeypatch, _GOOD)
    result = _Config().validate_startup()
    assert (result.valid, result.errors) == (True, [])


def test_an_absent_root_key_makes_startup_invalid_naming_the_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    _set(monkeypatch, None)
    result = _Config().validate_startup()
    assert result.valid is False
    assert result.errors == [f"{ROOT_KEY_ENV} is not set — the unified secrets root key is required"]


@pytest.mark.parametrize(
    ("value", "check"),
    [("Zm9v=x", "not valid url-safe base64"), (base64.urlsafe_b64encode(b"short").decode(), "32 bytes")],
)
def test_a_malformed_root_key_makes_startup_invalid_and_never_echoes_it(
    monkeypatch: pytest.MonkeyPatch, value: str, check: str
) -> None:
    _set(monkeypatch, value)
    result = _Config().validate_startup()
    assert result.valid is False
    assert len(result.errors) == 1 and ROOT_KEY_ENV in result.errors[0] and check in result.errors[0]
    assert value not in result.errors[0], "the key's value reached an error message"


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, "Zm9v=x"])
async def test_the_lifespan_config_step_refuses_to_start_without_a_usable_key(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    """The real startup step: ``_init_config`` raises, so no service after it starts."""
    _set(monkeypatch, value)
    monkeypatch.setattr(lifespan, "get_config_manager", _Config)
    monkeypatch.setattr(lifespan, "update_app_state", AsyncMock())
    with pytest.raises(RuntimeError, match=f"Configuration validation failed at startup: {ROOT_KEY_ENV}"):
        await lifespan._init_config(SimpleNamespace(state=SimpleNamespace()))


@pytest.mark.asyncio
async def test_the_lifespan_config_step_starts_with_a_usable_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _set(monkeypatch, _GOOD)
    monkeypatch.setattr(lifespan, "get_config_manager", _Config)
    monkeypatch.setattr(lifespan, "update_app_state", AsyncMock())
    app = SimpleNamespace(state=SimpleNamespace())
    await lifespan._init_config(app)
    assert isinstance(app.state.config, _Config)
