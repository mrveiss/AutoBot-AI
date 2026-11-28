# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Company PM credentials: the settings route seals, outbound sync opens, both for the same record (#17981)."""

import base64
import os
import uuid

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from autobot_shared.field_encryption import FieldDecryptionError
from llc.sync.outbound_sync import open_pm_config, seal_pm_config


@pytest.fixture(autouse=True)
def _root_key(monkeypatch):
    monkeypatch.setenv("AUTOBOT_SECRETS_ROOT_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())


def test_the_settings_seal_opens_in_outbound_sync_for_the_same_company():
    company = uuid.uuid4()
    # companies.set_pm_config seals with the UUID; the sync worker holds the id as a str.
    blob = seal_pm_config(company, {"token": "t"})
    assert open_pm_config(blob, str(company)) == {"token": "t"}


def test_one_companys_credentials_do_not_open_as_anothers():
    blob = seal_pm_config(uuid.uuid4(), {"token": "t"})
    with pytest.raises(FieldDecryptionError, match="external_pm_config"):
        open_pm_config(blob, str(uuid.uuid4()))


def test_a_pre_17981_pm_config_still_reads(monkeypatch):
    key = os.urandom(32)
    monkeypatch.setenv("AUTOBOT_FIELD_ENCRYPTION_KEY", base64.urlsafe_b64encode(key).decode())
    nonce = os.urandom(12)
    legacy = base64.urlsafe_b64encode(nonce + AESGCM(key).encrypt(nonce, b'{"token": "old"}', None)).decode()
    assert open_pm_config(legacy, str(uuid.uuid4())) == {"token": "old"}
