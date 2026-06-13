# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Envelope-crypto core for AutoBot's unified secrets infrastructure.

Task 1 of umbrella #10088. Pure, database-free primitives that every higher
layer (the SecretsService, vault store, migrations) builds on.

Design
------
- **One root key** (``AUTOBOT_SECRETS_ROOT_KEY``) — the single bootstrap
  secret, supplied via env (it cannot live in the store it protects).
- **Per-vault keys (KEK)** — ``derive_vault_key(root, vault_id)`` stretches the
  root with HKDF-SHA256 keyed to the vault id, so each vault (system, a user,
  an LLC company, a node) has a distinct key. Generalizes the per-company HKDF
  already used by ``llc/services/secret.py``.
- **Envelope encryption** — each secret has its own random **data key (DEK)**
  that encrypts the value *once* (AES-256-GCM). The DEK is then **wrapped** by a
  vault KEK and stored beside the ciphertext. Sharing a secret with another
  user/team/LLC-company = wrapping the *same* DEK for that grantee's KEK, so the
  payload is never re-encrypted or copied as plaintext and no KEK ever crosses a
  vault boundary. Revoking a share drops one wrapped DEK; rotating a KEK
  re-wraps the DEKs and leaves payloads untouched.

All AEAD is AES-256-GCM (12-byte random nonce), matching ``field_encryption.py``
and ``encryption_service.py``. Any authentication failure raises
:class:`DecryptionError` (wrong key or tampering).
"""

from __future__ import annotations

import base64
import os
from collections.abc import Mapping
from dataclasses import dataclass

ROOT_KEY_ENV = "AUTOBOT_SECRETS_ROOT_KEY"

# On-disk crypto format. Every persisted blob carries this so the algorithm can
# change later without guessing: a future v2 (different AEAD/KDF) is detected by
# the tag, not by trial decryption. Bump only when the wire format changes.
FORMAT_VERSION = 1

_KEY_LEN = 32  # AES-256
_NONCE_LEN = 12  # AES-GCM standard nonce
_HKDF_INFO_PREFIX = b"autobot-secrets-vault:"


class DecryptionError(Exception):
    """Raised when an AEAD open fails — wrong key, wrong grantee, or tampering."""


class UnsupportedFormatError(Exception):
    """Raised when a serialized blob carries a crypto-format version we can't read."""


def _check_version(data: Mapping[str, object]) -> None:
    version = data.get("v")
    if version != FORMAT_VERSION:
        raise UnsupportedFormatError(f"unsupported secrets crypto format v={version!r} (expected {FORMAT_VERSION})")


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "==")


def _aesgcm(key: bytes):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    return AESGCM(key)


def _seal_bytes(key: bytes, plaintext: bytes) -> tuple[bytes, bytes]:
    """AES-256-GCM encrypt; return (nonce, ciphertext-with-tag)."""
    nonce = os.urandom(_NONCE_LEN)
    return nonce, _aesgcm(key).encrypt(nonce, plaintext, None)


def _open_bytes(key: bytes, nonce: bytes, ciphertext: bytes) -> bytes:
    """AES-256-GCM decrypt; raise :class:`DecryptionError` on any failure."""
    from cryptography.exceptions import InvalidTag

    try:
        return _aesgcm(key).decrypt(nonce, ciphertext, None)
    except InvalidTag as exc:
        raise DecryptionError("AEAD authentication failed (wrong key or tampered data)") from exc


def load_root_key() -> bytes:
    """Load the 32-byte root key from ``AUTOBOT_SECRETS_ROOT_KEY`` (url-safe base64)."""
    raw = os.environ.get(ROOT_KEY_ENV, "")
    if not raw:
        raise RuntimeError(f"{ROOT_KEY_ENV} is not set — the unified secrets root key is required")
    key = _b64d(raw)
    if len(key) != _KEY_LEN:
        raise RuntimeError(f"{ROOT_KEY_ENV} must decode to 32 bytes (got {len(key)})")
    return key


def derive_vault_key(root_key: bytes, vault_id: str) -> bytes:
    """Derive a vault's 32-byte KEK from the root key via HKDF-SHA256."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=_KEY_LEN,
        salt=None,
        info=_HKDF_INFO_PREFIX + vault_id.encode("utf-8"),
    )
    return hkdf.derive(root_key)


@dataclass(frozen=True)
class SealedSecret:
    """A secret value encrypted once under its own DEK (DEK stored separately)."""

    nonce: bytes
    ciphertext: bytes

    def to_dict(self) -> dict[str, str | int]:
        return {"v": FORMAT_VERSION, "nonce": _b64e(self.nonce), "ciphertext": _b64e(self.ciphertext)}

    @classmethod
    def from_dict(cls, data: dict[str, str | int]) -> SealedSecret:
        _check_version(data)
        return cls(nonce=_b64d(str(data["nonce"])), ciphertext=_b64d(str(data["ciphertext"])))


@dataclass(frozen=True)
class WrappedDek:
    """A secret's DEK wrapped under one grantee's vault KEK (one per share)."""

    grantee: str
    nonce: bytes
    ciphertext: bytes

    def to_dict(self) -> dict[str, str | int]:
        return {
            "v": FORMAT_VERSION,
            "grantee": self.grantee,
            "nonce": _b64e(self.nonce),
            "ciphertext": _b64e(self.ciphertext),
        }

    @classmethod
    def from_dict(cls, data: dict[str, str | int]) -> WrappedDek:
        _check_version(data)
        return cls(
            grantee=str(data["grantee"]),
            nonce=_b64d(str(data["nonce"])),
            ciphertext=_b64d(str(data["ciphertext"])),
        )


def seal(plaintext: bytes, dek: bytes | None = None) -> tuple[SealedSecret, bytes]:
    """Encrypt *plaintext* under a fresh (or supplied) DEK. Returns (SealedSecret, dek)."""
    if dek is None:
        dek = os.urandom(_KEY_LEN)
    nonce, ciphertext = _seal_bytes(dek, plaintext)
    return SealedSecret(nonce=nonce, ciphertext=ciphertext), dek


def wrap_dek(dek: bytes, kek: bytes, grantee: str) -> WrappedDek:
    """Wrap *dek* under a vault *kek* for *grantee* (a vault id / principal)."""
    nonce, ciphertext = _seal_bytes(kek, dek)
    return WrappedDek(grantee=grantee, nonce=nonce, ciphertext=ciphertext)


def unwrap_dek(wrapped: WrappedDek, kek: bytes) -> bytes:
    """Recover the DEK from *wrapped* using the grantee's vault *kek*."""
    return _open_bytes(kek, wrapped.nonce, wrapped.ciphertext)


def open_secret(sealed: SealedSecret, wrapped: WrappedDek, kek: bytes) -> bytes:
    """Decrypt *sealed* by unwrapping its DEK from *wrapped* with vault *kek*."""
    dek = unwrap_dek(wrapped, kek)
    return _open_bytes(dek, sealed.nonce, sealed.ciphertext)


def rewrap_dek(wrapped: WrappedDek, old_kek: bytes, new_kek: bytes) -> WrappedDek:
    """Re-wrap a grant from *old_kek* to *new_kek* (key rotation; payload untouched)."""
    dek = unwrap_dek(wrapped, old_kek)
    return wrap_dek(dek, new_kek, wrapped.grantee)
