# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A deployment missing the secrets root key fails loudly at startup, not on first credential read (#17981).

``ValidationMixin.validate_startup`` is what ``initialization/lifespan._init_config`` runs before any service
starts; an error there raises "Configuration validation failed at startup". The check reuses the one
reader, ``secrets_envelope.load_root_key``, and its message names the setting, never the value.
"""

from __future__ import annotations

import base64

import pytest

from autobot_shared.secrets_envelope import ROOT_KEY_ENV
from config.validation import ValidationMixin

_GOOD = base64.urlsafe_b64encode(bytes(range(32))).decode()


class _Config(ValidationMixin):
    _config: dict = {}


def _validate(monkeypatch: pytest.MonkeyPatch, value: str | None):
    if value is None:
        monkeypatch.delenv(ROOT_KEY_ENV, raising=False)
    else:
        monkeypatch.setenv(ROOT_KEY_ENV, value)
    return _Config().validate_startup()


def test_an_absent_root_key_fails_startup_naming_the_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _validate(monkeypatch, None)
    assert not result.valid
    assert any(ROOT_KEY_ENV in e and "is not set" in e for e in result.errors), result.errors


@pytest.mark.parametrize(
    ("value", "check"),
    [("Zm9v=x", "not valid url-safe base64"), (base64.urlsafe_b64encode(b"short").decode(), "32 bytes")],
)
def test_a_malformed_root_key_fails_startup_and_never_echoes_it(
    monkeypatch: pytest.MonkeyPatch, value: str, check: str
) -> None:
    result = _validate(monkeypatch, value)
    assert not result.valid
    assert any(ROOT_KEY_ENV in e and check in e for e in result.errors), result.errors
    assert all(value not in e for e in result.errors), "the key's value reached an error message"


def test_a_usable_root_key_adds_no_error(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _validate(monkeypatch, _GOOD)
    assert not any(ROOT_KEY_ENV in e for e in result.errors), result.errors
