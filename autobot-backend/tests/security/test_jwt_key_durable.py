# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for durable RS256 keypair persistence — #10750 E2.

Root-cause tested: previously config.set_nested() stored the auto-generated key
in-memory only; after the fix the key is written to / read from a file outside
the code directory so it survives process restarts and code-sync rsyncs.

Strategy: import the real auth_middleware module (not the conftest stub) by
removing the stub entry from sys.modules before import, then call the
_get_rs256_keypair() / _jwt_key_file() methods directly on a minimal stub object
that bypasses the expensive __init__ side-effects (Redis, SecurityLayer, etc.).
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch  # noqa: F401 — patch used via patch.object

# ---------------------------------------------------------------------------
# Import the real auth_middleware module, bypassing the conftest stub.
# conftest.py guards with ``if "auth_middleware" not in sys.modules``, so we
# pop the stub, import the real module, then restore it after this module is
# collected so other tests keep their stub.
# ---------------------------------------------------------------------------


def _load_real_auth_middleware():
    """Return the real auth_middleware module, side-stepping the conftest stub."""
    sys.modules.pop("auth_middleware", None)
    try:
        mod = importlib.import_module("auth_middleware")
        return mod
    finally:
        # Restore: put the real module back so subsequent imports in THIS test
        # file also get the real one, not the stub.
        # Other test files that want the stub are unaffected because each
        # pytest process collects once and conftest guards with `if not in sys.modules`.
        sys.modules["auth_middleware"] = mod  # real module stays


_real_auth = _load_real_auth_middleware()
_RealAuthMW = _real_auth.AuthenticationMiddleware


# ---------------------------------------------------------------------------
# Minimal stub that lets us call instance methods without running __init__
# ---------------------------------------------------------------------------


class _MinimalMW(_RealAuthMW):
    """Bypass __init__ — we only want to call _get_rs256_keypair()."""

    def __new__(cls):
        # Skip __init__ entirely
        return object.__new__(cls)

    def __init__(self):
        self.security_config: dict = {}  # tier-3 in-memory config (empty)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_ssot(tmp_path: Path, jwt_private_key: str = ""):
    """Return a context-manager that patches auth_middleware.ssot_config."""
    mock_ssot = MagicMock()
    mock_ssot.misc.jwt_private_key = jwt_private_key
    mock_ssot.misc.jwt_kid = "autobot-test"
    mock_ssot.path.data_path = tmp_path
    return patch.object(_real_auth, "ssot_config", mock_ssot)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDurableJwtKey:
    """_get_rs256_keypair() must produce a durable key that survives restart."""

    def test_second_call_reuses_key_from_file(self, tmp_path):
        """First call generates + writes; second call must load the same PEM."""
        with _patch_ssot(tmp_path):
            mw1 = _MinimalMW()
            pem1, _, _ = mw1._get_rs256_keypair()

        key_file = tmp_path / "service-keys" / "jwt_rsa_private.pem"
        assert key_file.exists(), "durable file must be written on first call"

        with _patch_ssot(tmp_path):
            mw2 = _MinimalMW()
            pem2, _, _ = mw2._get_rs256_keypair()

        assert pem1 == pem2, (
            "Second call must return the same private key as the first "
            "(simulates process restart reading the durable file)"
        )

    def test_key_file_has_restricted_permissions(self, tmp_path):
        """Key file must be written with mode 0600."""
        with _patch_ssot(tmp_path):
            mw = _MinimalMW()
            mw._get_rs256_keypair()

        key_file = tmp_path / "service-keys" / "jwt_rsa_private.pem"
        assert key_file.exists()
        mode = oct(os.stat(key_file).st_mode & 0o777)
        assert mode == oct(0o600), f"Expected 0600, got {mode}"

    def test_env_var_key_takes_precedence_over_file(self, tmp_path):
        """When AUTOBOT_JWT_PRIVATE_KEY is set it beats the durable file."""
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        def _gen_pem() -> str:
            k = rsa.generate_private_key(65537, 2048, default_backend())
            return k.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            ).decode("utf-8")

        env_pem = _gen_pem()
        file_pem = _gen_pem()

        # Pre-populate durable file with a different key
        key_file = tmp_path / "service-keys" / "jwt_rsa_private.pem"
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_text(file_pem, encoding="utf-8")

        with _patch_ssot(tmp_path, jwt_private_key=env_pem):
            mw = _MinimalMW()
            pem_result, _, _ = mw._get_rs256_keypair()

        assert pem_result == env_pem, "Env var must override the durable file"

    def test_invalid_file_falls_through_to_generate(self, tmp_path):
        """Corrupt key file must be ignored and a fresh key generated."""
        key_dir = tmp_path / "service-keys"
        key_dir.mkdir(parents=True)
        bad_file = key_dir / "jwt_rsa_private.pem"
        bad_file.write_text("NOT A VALID PEM", encoding="utf-8")

        with _patch_ssot(tmp_path):
            mw = _MinimalMW()
            pem_result, _, _ = mw._get_rs256_keypair()

        assert pem_result != "NOT A VALID PEM"
        assert "BEGIN RSA PRIVATE KEY" in pem_result or "BEGIN PRIVATE KEY" in pem_result

    def test_jwt_key_file_path_uses_data_path(self, tmp_path):
        """_jwt_key_file() must resolve under AUTOBOT_DATA_DIR/service-keys/."""
        with _patch_ssot(tmp_path):
            key_file = _RealAuthMW._jwt_key_file()

        assert key_file == tmp_path / "service-keys" / "jwt_rsa_private.pem"

    def test_in_memory_config_key_migrated_to_file(self, tmp_path):
        """If security_config holds a jwt_private_key_pem, it must be migrated to disk."""
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        k = rsa.generate_private_key(65537, 2048, default_backend())
        in_memory_pem = k.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ).decode("utf-8")

        with _patch_ssot(tmp_path):
            mw = _MinimalMW()
            mw.security_config = {"jwt_private_key_pem": in_memory_pem}
            pem_result, _, _ = mw._get_rs256_keypair()

        assert pem_result == in_memory_pem
        key_file = tmp_path / "service-keys" / "jwt_rsa_private.pem"
        assert key_file.exists(), "In-memory key must be migrated to the durable file"
        assert key_file.read_text(encoding="utf-8") == in_memory_pem
