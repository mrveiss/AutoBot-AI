# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Reproduction tests for the secrets-store migration (#14081 review).

#14081's resolver fix changed *where* SecretsManager/SecretsService look for
their storage, from a legacy CWD-relative path to the canonical
ssot_config-derived one. On an existing deployment the real store is still
at the legacy location -- these tests prove the migration actually
preserves access to it, not merely that files get moved to a new path.

Each test stands up a legacy store with a *known* key and a *known*
encrypted value (never a fake "the file exists" placeholder), points the
canonical location at an empty directory, constructs the real class, and
asserts the original plaintext still decrypts. A test that only checked
"the file exists at the new path" would pass even if the migrated key and
the migrated ciphertext no longer matched -- decrypting is the only check
that catches that.
"""

from __future__ import annotations

import base64
import json
import sqlite3

import pytest
from cryptography.fernet import Fernet

from autobot_shared.ssot_config import config as _real_ssot_config
from autobot_shared.time_utils import now_utc


@pytest.fixture(autouse=True)
def _no_stray_secrets_artifacts():
    """Clean up any secrets-store file this test session causes to be
    (re-)provisioned at the *real* canonical location (#14081 review).

    ``api.secrets`` provisions a module-level ``SecretsManager`` singleton
    at import time (pre-existing design, tracked separately as #14116),
    which auto-generates a real encryption key the first time the module is
    imported and no key file exists yet. Importing it here (to reach the
    real, unmocked class) can be that first import in an isolated test run.
    Removes only files that did not exist before this test and were created
    during it -- never touches a real, pre-existing store.
    """
    data_dir = _real_ssot_config.path.data_path
    candidates = [data_dir / "secrets.key", data_dir / "secrets.json", data_dir / "secrets.db"]
    pre_existing = {p for p in candidates if p.exists()}
    yield
    for p in candidates:
        if p.exists() and p not in pre_existing:
            p.unlink()


class TestSecretsManagerMigrationPreservesDecryption:
    """SecretsManager: legacy secrets.key + secrets.json -> canonical."""

    def test_legacy_secret_still_decrypts_after_migration(self, tmp_path, monkeypatch):
        import api.secrets as secrets_api

        # Legacy location: get_data_path() (unmocked, real) falls back to
        # the CWD-relative "data/" when config.yaml has no "paths" section.
        legacy_root = tmp_path / "legacy_cwd"
        legacy_root.mkdir()
        monkeypatch.chdir(legacy_root)
        legacy_data_dir = legacy_root / "data"
        legacy_data_dir.mkdir()

        key = Fernet.generate_key()
        cipher = Fernet(key)
        plaintext = "sk-known-plaintext-value"  # noqa: S105 - test fixture, not a real credential
        encrypted_value = base64.b64encode(cipher.encrypt(plaintext.encode())).decode()

        (legacy_data_dir / "secrets.key").write_bytes(key)
        (legacy_data_dir / "secrets.key").chmod(0o600)
        (legacy_data_dir / "secrets.json").write_text(
            json.dumps({"known-id": {"id": "known-id", "encrypted_value": encrypted_value}}),
            encoding="utf-8",
        )

        # Canonical location: empty. Stubs api.secrets's module-level
        # `ssot_config` reference directly rather than touching the real
        # global singleton (which TestRealResolverAgreement already
        # exercises for the resolver-agreement concern; this test is about
        # the migration mechanism itself).
        canonical_dir = tmp_path / "canonical"
        canonical_dir.mkdir()

        class _StubPathConfig:
            data_path = canonical_dir

        class _StubConfig:
            path = _StubPathConfig()

        monkeypatch.setattr(secrets_api, "ssot_config", _StubConfig())

        manager = secrets_api.SecretsManager()

        loaded = manager._load_secrets()
        assert manager._decrypt_value(loaded["known-id"]["encrypted_value"]) == plaintext

        # The migration must have actually moved the files, not merely made
        # them independently reachable at both locations.
        assert not (legacy_data_dir / "secrets.key").exists()
        assert not (legacy_data_dir / "secrets.json").exists()
        assert oct((canonical_dir / "secrets.key").stat().st_mode)[-3:] == "600"


class TestSecretsServiceMigrationPreservesDecryption:
    """SecretsService: legacy secrets.db -> canonical."""

    def test_legacy_row_still_decrypts_after_migration(self, tmp_path, monkeypatch):
        import services.secrets_service as secrets_service_module

        legacy_root = tmp_path / "legacy_cwd"
        legacy_root.mkdir()
        monkeypatch.chdir(legacy_root)
        legacy_data_dir = legacy_root / "data"
        legacy_data_dir.mkdir()

        key = Fernet.generate_key()
        cipher = Fernet(key)
        plaintext = "sk-known-plaintext-value"  # noqa: S105 - test fixture, not a real credential
        encrypted_value = cipher.encrypt(plaintext.encode()).decode()

        conn = sqlite3.connect(str(legacy_data_dir / "secrets.db"))
        conn.execute("""
            CREATE TABLE secrets (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
                secret_type TEXT NOT NULL, encrypted_value TEXT NOT NULL,
                scope TEXT NOT NULL DEFAULT 'general', chat_id TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, expires_at TEXT,
                created_by TEXT, metadata TEXT, access_count INTEGER DEFAULT 0,
                last_accessed_at TEXT, is_active BOOLEAN DEFAULT 1
            )
            """)
        now = now_utc().isoformat()
        conn.execute(
            "INSERT INTO secrets (id, name, description, secret_type, encrypted_value, "
            "scope, chat_id, created_at, updated_at, expires_at, created_by, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("known-id", "test-secret", "", "api_key", encrypted_value, "general", None, now, now, None, "", "{}"),
        )
        conn.commit()
        conn.close()

        canonical_dir = tmp_path / "canonical"
        canonical_dir.mkdir()
        # Pre-place the shared key at the canonical location, as
        # SecretsManager's own migration would already have done in a real
        # deployment -- this test isolates SecretsService's secrets.db
        # migration specifically.
        (canonical_dir / "secrets.key").write_bytes(key)

        class _StubPathConfig:
            data_path = canonical_dir

        class _StubConfig:
            path = _StubPathConfig()
            secrets_key = ""  # forces _init_encryption to fall through to the key file

        monkeypatch.setattr(secrets_service_module, "config", _StubConfig())

        service = secrets_service_module.SecretsService()

        secret = service.get_secret(secret_id="known-id", include_value=True)
        assert secret is not None
        assert secret["value"] == plaintext

        assert not (legacy_data_dir / "secrets.db").exists()
