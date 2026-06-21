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
_SID = "secret:abc"  # a representative stable secret id used for AAD binding


@pytest.fixture()
def root_key(monkeypatch) -> bytes:
    monkeypatch.setenv(env.ROOT_KEY_ENV, _ROOT)
    return env.load_root_key()


class TestRootKey:
    def test_load_valid(self, monkeypatch) -> None:
        monkeypatch.setenv(env.ROOT_KEY_ENV, _ROOT)
        assert env.load_root_key() == bytes(range(32))

    def test_load_valid_unpadded(self, monkeypatch) -> None:
        monkeypatch.setenv(env.ROOT_KEY_ENV, _ROOT.rstrip("="))
        assert env.load_root_key() == bytes(range(32))

    def test_missing_raises(self, monkeypatch) -> None:
        monkeypatch.delenv(env.ROOT_KEY_ENV, raising=False)
        with pytest.raises(RuntimeError, match=env.ROOT_KEY_ENV):
            env.load_root_key()

    def test_wrong_length_raises(self, monkeypatch) -> None:
        monkeypatch.setenv(env.ROOT_KEY_ENV, base64.urlsafe_b64encode(b"tooshort").decode())
        with pytest.raises(RuntimeError, match="32 bytes"):
            env.load_root_key()

    def test_malformed_base64_raises_runtimeerror(self, monkeypatch) -> None:
        monkeypatch.setenv(env.ROOT_KEY_ENV, "not!valid!base64!!!")
        with pytest.raises(RuntimeError, match="base64"):
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

    def test_empty_vault_id_rejected(self, root_key) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            env.derive_vault_key(root_key, "")

    def test_overlong_vault_id_rejected(self, root_key) -> None:
        with pytest.raises(ValueError):
            env.derive_vault_key(root_key, "x" * (env._MAX_VAULT_ID_LEN + 1))


class TestSealOpenRoundtrip:
    def test_seal_then_open_with_vault_grant(self, root_key) -> None:
        kek = env.derive_vault_key(root_key, "user:alice")
        sealed, dek = env.seal(b"super-secret-value", secret_id=_SID)
        grant = env.wrap_dek(dek, kek, grantee="user:alice", secret_id=_SID)
        assert env.open_secret(sealed, grant, kek, secret_id=_SID) == b"super-secret-value"

    def test_dek_is_32_bytes(self) -> None:
        _, dek = env.seal(b"x", secret_id=_SID)
        assert len(dek) == 32

    def test_each_seal_uses_a_fresh_nonce(self) -> None:
        s1, _ = env.seal(b"same", secret_id=_SID)
        s2, _ = env.seal(b"same", secret_id=_SID)
        assert s1.nonce != s2.nonce

    def test_each_seal_uses_a_fresh_dek(self) -> None:
        _, d1 = env.seal(b"same", secret_id=_SID)
        _, d2 = env.seal(b"same", secret_id=_SID)
        assert d1 != d2

    def test_empty_plaintext_roundtrips(self, root_key) -> None:
        kek = env.derive_vault_key(root_key, "user:alice")
        sealed, dek = env.seal(b"", secret_id=_SID)
        grant = env.wrap_dek(dek, kek, "user:alice", secret_id=_SID)
        assert env.open_secret(sealed, grant, kek, secret_id=_SID) == b""


class TestWrapUnwrap:
    def test_roundtrip(self, root_key) -> None:
        kek = env.derive_vault_key(root_key, "system")
        _, dek = env.seal(b"x", secret_id=_SID)
        wrapped = env.wrap_dek(dek, kek, grantee="system", secret_id=_SID)
        assert env.unwrap_dek(wrapped, kek, secret_id=_SID) == dek

    def test_wrong_kek_fails(self, root_key) -> None:
        kek_a = env.derive_vault_key(root_key, "user:alice")
        kek_b = env.derive_vault_key(root_key, "user:bob")
        _, dek = env.seal(b"x", secret_id=_SID)
        wrapped = env.wrap_dek(dek, kek_a, grantee="user:alice", secret_id=_SID)
        with pytest.raises(env.DecryptionError):
            env.unwrap_dek(wrapped, kek_b, secret_id=_SID)

    def test_grantee_recorded(self, root_key) -> None:
        kek = env.derive_vault_key(root_key, "company:42")
        _, dek = env.seal(b"x", secret_id=_SID)
        assert env.wrap_dek(dek, kek, grantee="company:42", secret_id=_SID).grantee == "company:42"


class TestSharingCrossVault:
    def test_share_to_second_vault_opens_same_plaintext(self, root_key) -> None:
        kek_a = env.derive_vault_key(root_key, "company:A")
        kek_b = env.derive_vault_key(root_key, "company:B")
        sealed, dek = env.seal(b"shared-api-key", secret_id=_SID)
        grant_a = env.wrap_dek(dek, kek_a, grantee="company:A", secret_id=_SID)
        recovered_dek = env.unwrap_dek(grant_a, kek_a, secret_id=_SID)
        grant_b = env.wrap_dek(recovered_dek, kek_b, grantee="company:B", secret_id=_SID)
        assert env.open_secret(sealed, grant_b, kek_b, secret_id=_SID) == b"shared-api-key"

    def test_b_cannot_open_a_grant(self, root_key) -> None:
        kek_a = env.derive_vault_key(root_key, "company:A")
        kek_b = env.derive_vault_key(root_key, "company:B")
        sealed, dek = env.seal(b"private", secret_id=_SID)
        grant_a = env.wrap_dek(dek, kek_a, grantee="company:A", secret_id=_SID)
        with pytest.raises(env.DecryptionError):
            env.open_secret(sealed, grant_a, kek_b, secret_id=_SID)

    def test_multiple_grantees_all_open(self, root_key) -> None:
        keks = {v: env.derive_vault_key(root_key, v) for v in ("user:alice", "company:A", "company:B")}
        sealed, dek = env.seal(b"multi", secret_id=_SID)
        grants = {v: env.wrap_dek(dek, kek, grantee=v, secret_id=_SID) for v, kek in keks.items()}
        for v, kek in keks.items():
            assert env.open_secret(sealed, grants[v], kek, secret_id=_SID) == b"multi"


class TestAadBinding:
    """The H1 fix: ciphertexts are bound to their secret id and grantee."""

    def test_wrapped_dek_bound_to_secret_id(self, root_key) -> None:
        kek = env.derive_vault_key(root_key, "user:alice")
        _, dek = env.seal(b"x", secret_id="secret:X")
        grant = env.wrap_dek(dek, kek, "user:alice", secret_id="secret:X")
        # The same vault, same key — but claiming a different secret id must fail.
        with pytest.raises(env.DecryptionError):
            env.unwrap_dek(grant, kek, secret_id="secret:Y")

    def test_sealed_value_bound_to_secret_id(self, root_key) -> None:
        kek = env.derive_vault_key(root_key, "user:alice")
        sealed, dek = env.seal(b"value", secret_id="secret:X")
        grant = env.wrap_dek(dek, kek, "user:alice", secret_id="secret:X")
        # Open under the wrong secret id: the DEK-unwrap AAD mismatches first.
        with pytest.raises(env.DecryptionError):
            env.open_secret(sealed, grant, kek, secret_id="secret:Y")

    def test_cross_secret_grant_swap_rejected(self, root_key) -> None:
        # Alice holds grants for two secrets in her vault. Moving secret Y's
        # wrapped DEK onto secret X (same vault/key) must not disclose Y as X.
        kek = env.derive_vault_key(root_key, "user:alice")
        sealed_x, dek_x = env.seal(b"value-X", secret_id="secret:X")
        _, dek_y = env.seal(b"value-Y", secret_id="secret:Y")
        grant_y = env.wrap_dek(dek_y, kek, "user:alice", secret_id="secret:Y")
        # Attacker places grant_y where X's grant should be; open as X.
        with pytest.raises(env.DecryptionError):
            env.open_secret(sealed_x, grant_y, kek, secret_id="secret:X")

    def test_grantee_relabel_rejected(self, root_key) -> None:
        kek = env.derive_vault_key(root_key, "user:alice")
        _, dek = env.seal(b"x", secret_id=_SID)
        grant = env.wrap_dek(dek, kek, "user:alice", secret_id=_SID)
        # Relabel the grantee (plaintext field) — authenticated via AAD, so it fails.
        relabeled = env.WrappedDek(grantee="user:mallory", nonce=grant.nonce, ciphertext=grant.ciphertext)
        with pytest.raises(env.DecryptionError):
            env.unwrap_dek(relabeled, kek, secret_id=_SID)


class TestRotation:
    def test_rewrap_to_new_kek(self, root_key) -> None:
        old = env.derive_vault_key(root_key, "company:A")
        new_root = bytes((b + 1) % 256 for b in root_key)
        new = env.derive_vault_key(new_root, "company:A")
        sealed, dek = env.seal(b"rotate-me", secret_id=_SID)
        grant = env.wrap_dek(dek, old, grantee="company:A", secret_id=_SID)
        rewrapped = env.rewrap_dek(grant, old, new, secret_id=_SID)
        assert env.open_secret(sealed, rewrapped, new, secret_id=_SID) == b"rotate-me"
        assert rewrapped.grantee == "company:A"

    def test_old_kek_cannot_open_rewrapped(self, root_key) -> None:
        old = env.derive_vault_key(root_key, "company:A")
        new_root = bytes((b + 1) % 256 for b in root_key)
        new = env.derive_vault_key(new_root, "company:A")
        sealed, dek = env.seal(b"rotate-me", secret_id=_SID)
        rewrapped = env.rewrap_dek(env.wrap_dek(dek, old, "company:A", secret_id=_SID), old, new, secret_id=_SID)
        with pytest.raises(env.DecryptionError):
            env.open_secret(sealed, rewrapped, old, secret_id=_SID)


class TestTamperDetection:
    def test_tampered_value_ciphertext_raises(self, root_key) -> None:
        kek = env.derive_vault_key(root_key, "user:alice")
        sealed, dek = env.seal(b"integrity", secret_id=_SID)
        grant = env.wrap_dek(dek, kek, "user:alice", secret_id=_SID)
        flipped = bytearray(sealed.ciphertext)
        flipped[0] ^= 0x01
        tampered = env.SealedSecret(nonce=sealed.nonce, ciphertext=bytes(flipped))
        with pytest.raises(env.DecryptionError):
            env.open_secret(tampered, grant, kek, secret_id=_SID)

    def test_tampered_wrapped_dek_raises(self, root_key) -> None:
        kek = env.derive_vault_key(root_key, "user:alice")
        _, dek = env.seal(b"x", secret_id=_SID)
        wrapped = env.wrap_dek(dek, kek, "user:alice", secret_id=_SID)
        flipped = bytearray(wrapped.ciphertext)
        flipped[0] ^= 0x01
        tampered = env.WrappedDek(grantee="user:alice", nonce=wrapped.nonce, ciphertext=bytes(flipped))
        with pytest.raises(env.DecryptionError):
            env.unwrap_dek(tampered, kek, secret_id=_SID)


class TestSerialization:
    def test_wrapped_dek_roundtrips_through_dict(self, root_key) -> None:
        kek = env.derive_vault_key(root_key, "company:A")
        _, dek = env.seal(b"x", secret_id=_SID)
        wrapped = env.wrap_dek(dek, kek, "company:A", secret_id=_SID)
        restored = env.WrappedDek.from_dict(wrapped.to_dict())
        assert restored == wrapped
        assert env.unwrap_dek(restored, kek, secret_id=_SID) == dek

    def test_sealed_secret_roundtrips_through_dict(self, root_key) -> None:
        kek = env.derive_vault_key(root_key, "company:A")
        sealed, dek = env.seal(b"persist-me", secret_id=_SID)
        restored = env.SealedSecret.from_dict(sealed.to_dict())
        assert restored == sealed
        grant = env.wrap_dek(dek, kek, "company:A", secret_id=_SID)
        assert env.open_secret(restored, grant, kek, secret_id=_SID) == b"persist-me"

    def test_dicts_carry_format_version(self, root_key) -> None:
        sealed, dek = env.seal(b"x", secret_id=_SID)
        assert sealed.to_dict()["v"] == env.FORMAT_VERSION
        wrapped = env.wrap_dek(dek, env.derive_vault_key(root_key, "u"), "user:alice", secret_id=_SID)
        assert wrapped.to_dict()["v"] == env.FORMAT_VERSION

    def test_unknown_version_rejected(self, root_key) -> None:
        sealed, dek = env.seal(b"x", secret_id=_SID)
        with pytest.raises(env.UnsupportedFormatError):
            env.SealedSecret.from_dict({**sealed.to_dict(), "v": 999})
        wrapped = env.wrap_dek(dek, env.derive_vault_key(root_key, "u"), "u", secret_id=_SID)
        with pytest.raises(env.UnsupportedFormatError):
            env.WrappedDek.from_dict({**wrapped.to_dict(), "v": 999})

    def test_missing_version_rejected(self) -> None:
        sealed, _ = env.seal(b"x", secret_id=_SID)
        legacy = {k: v for k, v in sealed.to_dict().items() if k != "v"}
        with pytest.raises(env.UnsupportedFormatError):
            env.SealedSecret.from_dict(legacy)
