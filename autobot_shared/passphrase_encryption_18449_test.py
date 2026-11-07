# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The shared passphrase codec serves what both services' copies used to (#18449)."""

import pytest

from autobot_shared.passphrase_encryption import PassphraseEncryptionService, make_data_codec

KEY = "shared-core-test-master-key-0123456789abcdef"


class _KeyedFromArg(PassphraseEncryptionService):
    KEY_ENV_HINT = "A_TEST_KEY"

    def _load_master_key(self):
        return None


def test_round_trip_text_bytes_and_json():
    svc = _KeyedFromArg(KEY)
    assert svc.decrypt(svc.encrypt("hello")) == "hello"
    assert svc.decrypt(svc.encrypt(b"raw")) == "raw"
    assert svc.decrypt_json(svc.encrypt_json({"a": 1})) == {"a": 1}


def test_two_services_with_the_same_key_read_each_others_blobs():
    """The wire format has one definition, so the former backend/SLM copies interoperate."""

    class Other(_KeyedFromArg):
        pass

    blob = _KeyedFromArg(KEY).encrypt("secret")
    assert Other(KEY).decrypt(blob) == "secret"


def test_missing_key_error_names_the_subclass_hint():
    with pytest.raises(ValueError, match="A_TEST_KEY"):
        _KeyedFromArg()


def test_wrong_key_and_short_blob_raise_value_error():
    blob = _KeyedFromArg(KEY).encrypt("x")
    with pytest.raises(ValueError):
        _KeyedFromArg("another-master-key-0123456789abcdef!!").decrypt(blob)
    with pytest.raises(ValueError, match="too short"):
        _KeyedFromArg(KEY).decrypt("AAAA")


def test_is_encrypted_and_key_info():
    svc = _KeyedFromArg(KEY)
    assert svc.is_encrypted(svc.encrypt("x"))
    assert not svc.is_encrypted("not base64 !!")
    info = svc.get_key_info()
    assert info["iterations"] == 100000 and KEY not in str(info)
    assert len(_KeyedFromArg.generate_key(8)) > 0


def test_codec_resolves_the_service_on_every_call():
    holder = {"svc": _KeyedFromArg(KEY)}
    encrypt_data, decrypt_data = make_data_codec(lambda: holder["svc"])
    assert decrypt_data(encrypt_data("a")) == "a"
    assert decrypt_data(encrypt_data({"k": 1}), as_json=True) == {"k": 1}
    holder["svc"] = _KeyedFromArg("swapped-master-key-0123456789abcdef!!")
    with pytest.raises(ValueError):
        decrypt_data(_KeyedFromArg(KEY).encrypt("a"))
