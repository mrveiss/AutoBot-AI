# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The backend EncryptionService and its helpers are the shared codec bound to SSOT config (#18449)."""

import encryption_service as enc
from autobot_shared.passphrase_encryption import PassphraseEncryptionService

KEY = "backend-shared-core-key-0123456789abcdef"


def test_backend_service_is_the_shared_codec():
    assert issubclass(enc.EncryptionService, PassphraseEncryptionService)
    assert enc.EncryptionService.KEY_ENV_HINT == "AUTOBOT_ENCRYPTION_KEY"


def test_module_helpers_use_the_module_singleton(monkeypatch):
    svc = enc.EncryptionService(master_key=KEY)
    monkeypatch.setattr(enc, "get_encryption_service", lambda: svc)
    assert enc.decrypt_data(enc.encrypt_data("v")) == "v"
    assert enc.decrypt_data(enc.encrypt_data({"a": 1}), as_json=True) == {"a": 1}
