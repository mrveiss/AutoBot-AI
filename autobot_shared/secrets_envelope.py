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
- **Authenticated binding (AAD)** — both AEAD layers bind the stable
  identifiers of where the ciphertext lives (the secret id, and for a wrapped
  DEK the grantee), plus the format version, as Associated Data. A
  write-capable attacker therefore cannot move a sealed value or a wrapped DEK
  onto a different secret, relabel a grant's grantee, or downgrade the format —
  any such tamper fails authentication (:class:`DecryptionError`). The
  ``grantee`` field is plaintext metadata *and* is authenticated via AAD.

All AEAD is AES-256-GCM (12-byte random nonce), matching ``field_encryption.py``
and ``encryption_service.py``. A DEK encrypts exactly one value once, so its
nonce never repeats. A KEK wraps many DEKs with random 96-bit nonces; the safe
budget is ~2**32 wraps per KEK (NIST SP 800-38D) — far beyond any real
deployment, with KEK rotation (:func:`rewrap_dek`) as the backstop. Any
authentication failure raises :class:`DecryptionError`.
"""

from __future__ import annotations

import base64
import binascii
import os
from collections.abc import Mapping
from dataclasses import dataclass

ROOT_KEY_ENV = "AUTOBOT_SECRETS_ROOT_KEY"

# On-disk crypto format. Persisted in every blob AND authenticated into the AAD
# so a future v2 (different AEAD/KDF) cannot be downgraded onto by a store-write
# attacker. Bump only when the wire format changes.
FORMAT_VERSION = 1

_KEY_LEN = 32  # AES-256
_NONCE_LEN = 12  # AES-GCM standard nonce
_HKDF_INFO_PREFIX = b"autobot-secrets-vault:"
_MAX_VAULT_ID_LEN = 512


class DecryptionError(Exception):
    """Raised when an AEAD open fails — wrong key, wrong grantee, wrong secret, or tampering."""


class UnsupportedFormatError(Exception):
    """Raised when a serialized blob carries a crypto-format version we can't read."""


def _check_version(data: Mapping[str, object]) -> None:
    version = data.get("v")
    if version != FORMAT_VERSION:
        raise UnsupportedFormatError(f"unsupported secrets crypto format v={version!r} (expected {FORMAT_VERSION})")


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _b64d(text: str) -> bytes:
    stripped = text.rstrip("=")
    return base64.urlsafe_b64decode(stripped + "=" * (-len(stripped) % 4))


def _aad(kind: bytes, *fields: bytes) -> bytes:
    """Unambiguous (length-prefixed) Associated Data, version-bound and domain-separated.

    Length-prefixing each field makes the encoding injective, so no two distinct
    (kind, fields) tuples can ever collide into the same AAD.
    """
    parts = (FORMAT_VERSION.to_bytes(2, "big"), kind, *fields)
    return b"".join(len(p).to_bytes(4, "big") + p for p in parts)


def _value_aad(secret_id: str) -> bytes:
    return _aad(b"secret-value", secret_id.encode("utf-8"))


def _dek_aad(grantee: str, secret_id: str) -> bytes:
    return _aad(b"wrapped-dek", grantee.encode("utf-8"), secret_id.encode("utf-8"))


def _aesgcm(key: bytes):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    return AESGCM(key)


def _seal_bytes(key: bytes, plaintext: bytes, aad: bytes) -> tuple[bytes, bytes]:
    """AES-256-GCM encrypt with associated data; return (nonce, ciphertext-with-tag)."""
    nonce = os.urandom(_NONCE_LEN)
    return nonce, _aesgcm(key).encrypt(nonce, plaintext, aad)


def _open_bytes(key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes) -> bytes:
    """AES-256-GCM decrypt; raise :class:`DecryptionError` on any failure."""
    from cryptography.exceptions import InvalidTag

    try:
        return _aesgcm(key).decrypt(nonce, ciphertext, aad)
    except InvalidTag as exc:
        raise DecryptionError("AEAD authentication failed (wrong key/grantee/secret or tampered data)") from exc


def load_root_key() -> bytes:
    """Load the 32-byte root key from ``AUTOBOT_SECRETS_ROOT_KEY`` (url-safe base64)."""
    raw = os.environ.get(ROOT_KEY_ENV, "")
    if not raw:
        raise RuntimeError(f"{ROOT_KEY_ENV} is not set — the unified secrets root key is required")
    try:
        key = _b64d(raw)
    except (binascii.Error, ValueError) as exc:
        raise RuntimeError(f"{ROOT_KEY_ENV} is not valid url-safe base64") from exc
    if len(key) != _KEY_LEN:
        raise RuntimeError(f"{ROOT_KEY_ENV} must decode to 32 bytes (got {len(key)})")
    return key


def derive_vault_key(root_key: bytes, vault_id: str) -> bytes:
    """Derive a vault's 32-byte KEK from the root key via HKDF-SHA256."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    if not vault_id:
        raise ValueError("vault_id must be a non-empty string")
    if len(vault_id) > _MAX_VAULT_ID_LEN:
        raise ValueError(f"vault_id exceeds {_MAX_VAULT_ID_LEN} chars")

    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=_KEY_LEN,
        salt=None,
        # Single variable-length trailing field after a constant prefix → injective.
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
    def from_dict(cls, data: Mapping[str, str | int]) -> SealedSecret:
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
    def from_dict(cls, data: Mapping[str, str | int]) -> WrappedDek:
        _check_version(data)
        return cls(
            grantee=str(data["grantee"]),
            nonce=_b64d(str(data["nonce"])),
            ciphertext=_b64d(str(data["ciphertext"])),
        )


def seal(plaintext: bytes, *, secret_id: str, dek: bytes | None = None) -> tuple[SealedSecret, bytes]:
    """Encrypt *plaintext* under a fresh (or supplied) DEK, bound to *secret_id*. Returns (SealedSecret, dek)."""
    if dek is None:
        dek = os.urandom(_KEY_LEN)
    nonce, ciphertext = _seal_bytes(dek, plaintext, _value_aad(secret_id))
    return SealedSecret(nonce=nonce, ciphertext=ciphertext), dek


def wrap_dek(dek: bytes, kek: bytes, grantee: str, *, secret_id: str) -> WrappedDek:
    """Wrap *dek* under a vault *kek* for *grantee*, bound to (grantee, secret_id)."""
    nonce, ciphertext = _seal_bytes(kek, dek, _dek_aad(grantee, secret_id))
    return WrappedDek(grantee=grantee, nonce=nonce, ciphertext=ciphertext)


def unwrap_dek(wrapped: WrappedDek, kek: bytes, *, secret_id: str) -> bytes:
    """Recover the DEK from *wrapped* using the grantee's vault *kek*; authenticates (grantee, secret_id)."""
    return _open_bytes(kek, wrapped.nonce, wrapped.ciphertext, _dek_aad(wrapped.grantee, secret_id))


def open_secret(sealed: SealedSecret, wrapped: WrappedDek, kek: bytes, *, secret_id: str) -> bytes:
    """Decrypt *sealed* by unwrapping its DEK from *wrapped* with vault *kek*; both layers bound to *secret_id*."""
    dek = unwrap_dek(wrapped, kek, secret_id=secret_id)
    return _open_bytes(dek, sealed.nonce, sealed.ciphertext, _value_aad(secret_id))


def rewrap_dek(wrapped: WrappedDek, old_kek: bytes, new_kek: bytes, *, secret_id: str) -> WrappedDek:
    """Re-wrap a grant from *old_kek* to *new_kek* (key rotation; payload untouched)."""
    dek = unwrap_dek(wrapped, old_kek, secret_id=secret_id)
    return wrap_dek(dek, new_kek, wrapped.grantee, secret_id=secret_id)
