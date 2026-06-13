# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the unified-secrets envelope-crypto core (Task 1, #10089 / umbrella #10088)."""

from __future__ import annotations

import base64

import pytest

from autobot_shared import secrets_envelope as env

_ROOT = base64.urlsafe_b64encode(bytes(range(32))).decode("ascii")


@pytest.fixture()
def root_key(monkeypatch) -> bytes:
    monkeypatch.setenv(env.ROOT_KEY_ENV, _ROOT)
    return env.load_root_key()


class TestRootKey:
    def test_load_valid(self, monkeypatch) -> None:
        monkeypatch.setenv(env.ROOT_KEY_ENV, _ROOT)
        assert env.load_root_key() == bytes(range(32))

    def test_missing_raises(self, monkeypatch) -> None:
        monkeypatch.delenv(env.ROOT_KEY_ENV, raising=False)
        with pytest.raises(RuntimeError, match=env.ROOT_KEY_ENV):
            env.load_root_key()

    def test_wrong_length_raises(self, monkeypatch) -> None:
        monkeypatch.setenv(env.ROOT_KEY_ENV, base64.urlsafe_b64encode(b"tooshort").decode())
        with pytest.raises(RuntimeError, match="32 bytes"):
            env.load_root_key()


class TestDeriveVaultKey:
    def test_deterministic(self, root_key) -> None:
        assert env.derive_vault_key(root_key, "company:42") == env.derive_vault_key(root_key, "company:42")

    def test_distinct_per_vault(self, root_key) -> None:
        assert env.derive_vault_key(root_key, "company:42") != env.derive_vault_key(root_key, "company:43")

    def test_is_32_bytes(self, root_key) -> None:
        assert len(env.derive_vault_key(root_key, "system")) == 32

    def test_distinct_from_root(self, root_key) -> None:
        assert env.derive_vault_key(root_key, "system") != root_key


class TestSealOpenRoundtrip:
    def test_seal_then_open_with_vault_grant(self, root_key) -> None:
        kek = env.derive_vault_key(root_key, "user:alice")
        sealed, dek = env.seal(b"super-secret-value")
        grant = env.wrap_dek(dek, kek, grantee="user:alice")
        assert env.open_secret(sealed, grant, kek) == b"super-secret-value"

    def test_dek_is_32_bytes(self, root_key) -> None:
        _, dek = env.seal(b"x")
        assert len(dek) == 32

    def test_each_seal_uses_a_fresh_nonce(self) -> None:
        s1, _ = env.seal(b"same")
        s2, _ = env.seal(b"same")
        assert s1.nonce != s2.nonce

    def test_each_seal_uses_a_fresh_dek(self) -> None:
        _, d1 = env.seal(b"same")
        _, d2 = env.seal(b"same")
        assert d1 != d2

    def test_empty_plaintext_roundtrips(self, root_key) -> None:
        kek = env.derive_vault_key(root_key, "user:alice")
        sealed, dek = env.seal(b"")
        assert env.open_secret(sealed, env.wrap_dek(dek, kek, "user:alice"), kek) == b""


class TestWrapUnwrap:
    def test_roundtrip(self, root_key) -> None:
        kek = env.derive_vault_key(root_key, "system")
        _, dek = env.seal(b"x")
        wrapped = env.wrap_dek(dek, kek, grantee="system")
        assert env.unwrap_dek(wrapped, kek) == dek

    def test_wrong_kek_fails(self, root_key) -> None:
        kek_a = env.derive_vault_key(root_key, "user:alice")
        kek_b = env.derive_vault_key(root_key, "user:bob")
        _, dek = env.seal(b"x")
        wrapped = env.wrap_dek(dek, kek_a, grantee="user:alice")
        with pytest.raises(env.DecryptionError):
            env.unwrap_dek(wrapped, kek_b)

    def test_grantee_recorded(self, root_key) -> None:
        kek = env.derive_vault_key(root_key, "company:42")
        _, dek = env.seal(b"x")
        assert env.wrap_dek(dek, kek, grantee="company:42").grantee == "company:42"


class TestSharingCrossVault:
    def test_share_to_second_vault_opens_same_plaintext(self, root_key) -> None:
        # company A owns the secret; shares with company B by wrapping the same DEK.
        kek_a = env.derive_vault_key(root_key, "company:A")
        kek_b = env.derive_vault_key(root_key, "company:B")
        sealed, dek = env.seal(b"shared-api-key")
        grant_a = env.wrap_dek(dek, kek_a, grantee="company:A")
        # B receives a grant; the service unwrapped DEK via A then wrapped for B.
        recovered_dek = env.unwrap_dek(grant_a, kek_a)
        grant_b = env.wrap_dek(recovered_dek, kek_b, grantee="company:B")
        assert env.open_secret(sealed, grant_b, kek_b) == b"shared-api-key"

    def test_b_cannot_open_a_grant(self, root_key) -> None:
        kek_a = env.derive_vault_key(root_key, "company:A")
        kek_b = env.derive_vault_key(root_key, "company:B")
        sealed, dek = env.seal(b"private")
        grant_a = env.wrap_dek(dek, kek_a, grantee="company:A")
        with pytest.raises(env.DecryptionError):
            env.open_secret(sealed, grant_a, kek_b)

    def test_multiple_grantees_all_open(self, root_key) -> None:
        keks = {v: env.derive_vault_key(root_key, v) for v in ("user:alice", "company:A", "company:B")}
        sealed, dek = env.seal(b"multi")
        grants = {v: env.wrap_dek(dek, kek, grantee=v) for v, kek in keks.items()}
        for v, kek in keks.items():
            assert env.open_secret(sealed, grants[v], kek) == b"multi"


class TestRotation:
    def test_rewrap_to_new_kek(self, root_key) -> None:
        old = env.derive_vault_key(root_key, "company:A")
        new_root = bytes((b + 1) % 256 for b in root_key)
        new = env.derive_vault_key(new_root, "company:A")
        sealed, dek = env.seal(b"rotate-me")
        grant = env.wrap_dek(dek, old, grantee="company:A")
        rewrapped = env.rewrap_dek(grant, old, new)
        assert env.open_secret(sealed, rewrapped, new) == b"rotate-me"
        assert rewrapped.grantee == "company:A"

    def test_old_kek_cannot_open_rewrapped(self, root_key) -> None:
        old = env.derive_vault_key(root_key, "company:A")
        new_root = bytes((b + 1) % 256 for b in root_key)
        new = env.derive_vault_key(new_root, "company:A")
        sealed, dek = env.seal(b"rotate-me")
        rewrapped = env.rewrap_dek(env.wrap_dek(dek, old, "company:A"), old, new)
        with pytest.raises(env.DecryptionError):
            env.open_secret(sealed, rewrapped, old)


class TestTamperDetection:
    def test_tampered_value_ciphertext_raises(self, root_key) -> None:
        kek = env.derive_vault_key(root_key, "user:alice")
        sealed, dek = env.seal(b"integrity")
        grant = env.wrap_dek(dek, kek, "user:alice")
        flipped = bytearray(sealed.ciphertext)
        flipped[0] ^= 0x01
        tampered = env.SealedSecret(nonce=sealed.nonce, ciphertext=bytes(flipped))
        with pytest.raises(env.DecryptionError):
            env.open_secret(tampered, grant, kek)

    def test_tampered_wrapped_dek_raises(self, root_key) -> None:
        kek = env.derive_vault_key(root_key, "user:alice")
        _, dek = env.seal(b"x")
        wrapped = env.wrap_dek(dek, kek, "user:alice")
        flipped = bytearray(wrapped.ciphertext)
        flipped[0] ^= 0x01
        tampered = env.WrappedDek(grantee="user:alice", nonce=wrapped.nonce, ciphertext=bytes(flipped))
        with pytest.raises(env.DecryptionError):
            env.unwrap_dek(tampered, kek)


class TestSerialization:
    def test_wrapped_dek_roundtrips_through_dict(self, root_key) -> None:
        kek = env.derive_vault_key(root_key, "company:A")
        _, dek = env.seal(b"x")
        wrapped = env.wrap_dek(dek, kek, "company:A")
        restored = env.WrappedDek.from_dict(wrapped.to_dict())
        assert restored == wrapped
        assert env.unwrap_dek(restored, kek) == dek

    def test_sealed_secret_roundtrips_through_dict(self, root_key) -> None:
        kek = env.derive_vault_key(root_key, "company:A")
        sealed, dek = env.seal(b"persist-me")
        restored = env.SealedSecret.from_dict(sealed.to_dict())
        assert restored == sealed
        grant = env.wrap_dek(dek, kek, "company:A")
        assert env.open_secret(restored, grant, kek) == b"persist-me"
