# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The backend refuses to start without the secrets root key, so no audit row is written unchained (#17219).

Chain: ``lifespan._init_config`` calls ``config.validate_startup()`` and raises when the result is invalid;
``ValidationMixin.validate_startup`` adds the root-key error (``_require_root_key``); the audit chain key is
derived from that same root key (``secrets_envelope.derive_audit_chain_key``).
"""

import base64
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI

from autobot_shared.secrets_envelope import ROOT_KEY_ENV, derive_audit_chain_key
from config.validation import ConfigValidationResult, ValidationMixin
from initialization import lifespan


class _Manager(ValidationMixin):
    """The real ``validate_startup`` over an otherwise valid config."""

    _config: dict = {}


async def _start() -> None:
    with (
        patch.object(lifespan, "get_config_manager", return_value=_Manager()),
        patch.object(lifespan, "update_app_state", AsyncMock()),
        patch("config.validation.validate_startup_config", return_value=ConfigValidationResult()),
        patch("config.validation.warn_on_selected_model_drift"),
        patch("config.validation.log_startup_config_summary", create=True),
    ):
        await lifespan._init_config(FastAPI())


@pytest.mark.asyncio
async def test_startup_aborts_without_the_root_key(monkeypatch) -> None:
    monkeypatch.delenv(ROOT_KEY_ENV, raising=False)
    with pytest.raises(RuntimeError, match=ROOT_KEY_ENV):
        await _start()


@pytest.mark.asyncio
async def test_startup_proceeds_with_the_root_key_and_the_chain_key_derives(monkeypatch) -> None:
    root = b"r" * 32
    monkeypatch.setenv(ROOT_KEY_ENV, base64.urlsafe_b64encode(root).decode("ascii"))
    await _start()
    assert len(derive_audit_chain_key()) == 32
