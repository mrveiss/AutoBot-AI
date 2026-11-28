# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SLM encryption module is the shared codec keyed from the SLM environment (#18449).

Loaded by path under a private name: conftest stubs ``services.encryption`` for
the api tests, so a bare import would hand back the stub.
"""

import importlib.util
from pathlib import Path

import pytest

from autobot_shared.passphrase_encryption import PassphraseEncryptionService

_PATH = Path(__file__).resolve().parents[2] / "services" / "encryption.py"
KEY = "slm-shared-core-key-0123456789abcdef"


@pytest.fixture
def enc():
    spec = importlib.util.spec_from_file_location("_slm_encryption_18449", _PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_slm_service_is_the_shared_codec(enc):
    assert issubclass(enc.SlmEncryptionService, PassphraseEncryptionService)
    assert enc.SlmEncryptionService.KEY_ENV_HINT == "SLM_ENCRYPTION_KEY"


def test_key_comes_from_slm_env_with_secret_key_fallback(enc, monkeypatch):
    monkeypatch.delenv("SLM_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("SLM_SECRET_KEY", KEY)
    assert enc.SlmEncryptionService().master_key == KEY
    monkeypatch.delenv("SLM_SECRET_KEY")
    with pytest.raises(ValueError, match="SLM_ENCRYPTION_KEY"):
        enc.SlmEncryptionService()


def test_module_helpers_round_trip_through_the_singleton(enc, monkeypatch):
    monkeypatch.setenv("SLM_ENCRYPTION_KEY", KEY)
    enc.get_encryption_service.reset()
    assert enc.decrypt_data(enc.encrypt_data("v")) == "v"
    assert enc.decrypt_data(enc.encrypt_data({"a": 1}), as_json=True) == {"a": 1}
    enc.get_encryption_service.reset()
