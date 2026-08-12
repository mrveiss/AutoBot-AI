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
import re
import sqlite3
from pathlib import Path

import pytest
import yaml
from cryptography.fernet import Fernet

from autobot_shared.ssot_config import config as _real_ssot_config
from autobot_shared.time_utils import now_utc

_REPO_ROOT = Path(__file__).resolve().parents[3]


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


class TestMigrationRunsAtStartupNotImport:
    """#14081 review round 4 / #14110: the migration -- and any disk I/O
    the module-level ``SecretsManager`` singleton used to do in its
    constructor -- must never run as a side effect of importing
    ``api.secrets``.

    That was the actual cause of the ``hardened-smoke-test`` failure on PR
    #14110: the hardened compose overlay's read-only root made the
    canonical data directory unwritable, and ``SecretsManager.__init__``
    running ``_initialize_encryption()`` at import time turned that into an
    ``OSError`` no operator could see or recover from -- it crashed the
    interpreter before FastAPI's startup ordering existed to report it.
    """

    def test_constructing_secrets_manager_touches_no_disk(self, tmp_path, monkeypatch):
        """Regression guard for the exact #14110 failure.

        This is the reproduction that must fail against the pre-fix
        constructor: give it a legacy store to migrate and a canonical
        directory, then merely *construct* ``SecretsManager()`` -- exactly
        what ``secrets_manager = SecretsManager()`` does at import time --
        without calling any method on it. Nothing must be read, moved, or
        written.
        """
        import api.secrets as secrets_api

        legacy_root = tmp_path / "legacy_cwd"
        legacy_root.mkdir()
        monkeypatch.chdir(legacy_root)
        legacy_data_dir = legacy_root / "data"
        legacy_data_dir.mkdir()
        (legacy_data_dir / "secrets.key").write_bytes(b"legacy-key-material")

        canonical_dir = tmp_path / "canonical"
        canonical_dir.mkdir()

        class _StubPathConfig:
            data_path = canonical_dir

        class _StubConfig:
            path = _StubPathConfig()

        monkeypatch.setattr(secrets_api, "ssot_config", _StubConfig())

        secrets_api.SecretsManager()  # must not touch disk

        assert list(canonical_dir.iterdir()) == [], "construction wrote to the canonical data dir"
        assert (legacy_data_dir / "secrets.key").exists(), "construction moved the legacy store"

    def test_importing_api_secrets_module_touches_no_disk(self, tmp_path, monkeypatch):
        """The literal regression: importing the module alone -- what
        ``secrets_manager = SecretsManager()`` running at import time means
        in practice -- must not migrate or generate key material.

        ``reload`` re-runs every module-level statement, including
        ``secrets_manager = SecretsManager()``, exactly reproducing what a
        fresh process import does -- without needing to stub ``ssot_config``
        (construction no longer reads it at all; that is the fix).
        """
        import importlib

        import api.secrets as secrets_api

        legacy_root = tmp_path / "legacy_cwd"
        legacy_root.mkdir()
        monkeypatch.chdir(legacy_root)
        legacy_data_dir = legacy_root / "data"
        legacy_data_dir.mkdir()
        (legacy_data_dir / "secrets.key").write_bytes(b"legacy-key-material")

        canonical_dir = _real_ssot_config.path.data_path
        pre_existing_canonical = {p.name for p in canonical_dir.iterdir()} if canonical_dir.exists() else set()

        importlib.reload(secrets_api)

        new_canonical_files = (
            {p.name for p in canonical_dir.iterdir()} - pre_existing_canonical if canonical_dir.exists() else set()
        )
        assert new_canonical_files == set(), "importing api.secrets wrote to the canonical data dir"
        assert (legacy_data_dir / "secrets.key").exists(), "importing api.secrets moved the legacy store"

    def test_ensure_initialized_is_idempotent(self, tmp_path, monkeypatch):
        """Safe to call twice: the second call is a no-op, not a re-migration."""
        import api.secrets as secrets_api

        legacy_root = tmp_path / "legacy_cwd"
        legacy_root.mkdir()
        monkeypatch.chdir(legacy_root)
        legacy_data_dir = legacy_root / "data"
        legacy_data_dir.mkdir()
        (legacy_data_dir / "secrets.key").write_bytes(Fernet.generate_key())
        (legacy_data_dir / "secrets.json").write_text("{}", encoding="utf-8")

        canonical_dir = tmp_path / "canonical"
        canonical_dir.mkdir()

        class _StubPathConfig:
            data_path = canonical_dir

        class _StubConfig:
            path = _StubPathConfig()

        monkeypatch.setattr(secrets_api, "ssot_config", _StubConfig())

        manager = secrets_api.SecretsManager()
        manager.ensure_initialized()
        key_after_first_call = (canonical_dir / "secrets.key").read_bytes()

        manager.ensure_initialized()  # must not raise, move, or regenerate
        assert (canonical_dir / "secrets.key").read_bytes() == key_after_first_call


class TestSecretsServiceMigrationPreservesDecryption:
    """SecretsService: legacy secrets.db -> canonical.

    #14081 review round 5, finding 2: SecretsService now migrates the FULL
    secrets-store file set (ALL_SECRETS_STORE_FILES), not just secrets.db,
    so a process that constructs it standalone -- a celery worker, with no
    SecretsManager ever running -- still gets the shared key moved. This
    test's legacy store therefore includes a real secrets.key alongside
    secrets.db, exactly like a real pre-#14081 deployment, rather than
    pre-placing the key directly at canonical.
    """

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

        # The shared key lives at the LEGACY location, same as secrets.db --
        # a real pre-#14081 deployment. SecretsService alone must migrate
        # both, not just the db it directly reads.
        (legacy_data_dir / "secrets.key").write_bytes(key)

        canonical_dir = tmp_path / "canonical"
        canonical_dir.mkdir()

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
        assert not (legacy_data_dir / "secrets.key").exists(), "SecretsService alone must migrate the shared key too"
        assert (canonical_dir / "secrets.key").read_bytes() == key


class TestSecretsServiceAloneMigratesTheSharedKey:
    """#14081 review round 5, finding 2: a process that constructs
    SecretsService without SecretsManager (api/secrets.py) ever running --
    a celery worker via tasks/credential_reconcile.py or
    services/workflow_secret_service.py, neither of which runs the FastAPI
    lifespan -- must still migrate the shared secrets.key, not just
    secrets.db. Before the fix, SecretsService's own migration call only
    covered ["secrets.db"]: the db moved, the key stayed at the legacy
    location, _init_encryption found no key file there and silently minted
    an unpersisted throwaway one -- reads raised InvalidToken, writes
    produced rows nothing could ever decrypt.

    Deliberately never imports api.secrets -- the whole point is that
    SecretsManager plays no part in the outcome.
    """

    def test_key_is_readable_after_secrets_service_alone(self, tmp_path, monkeypatch):
        import services.secrets_service as secrets_service_module

        legacy_root = tmp_path / "legacy_cwd"
        legacy_root.mkdir()
        monkeypatch.chdir(legacy_root)
        legacy_data_dir = legacy_root / "data"
        legacy_data_dir.mkdir()

        key = Fernet.generate_key()
        (legacy_data_dir / "secrets.key").write_bytes(key)

        canonical_dir = tmp_path / "canonical"
        canonical_dir.mkdir()

        class _StubPathConfig:
            data_path = canonical_dir

        class _StubConfig:
            path = _StubPathConfig()
            secrets_key = ""  # forces _init_encryption to fall through to the key file

        monkeypatch.setattr(secrets_service_module, "config", _StubConfig())

        service = secrets_service_module.SecretsService()

        # Proof the service's cipher is built from the ORIGINAL migrated
        # key, not a freshly-minted throwaway one: a Fernet token encrypted
        # with a *different* key raises InvalidToken on decrypt, so a
        # successful cross-decrypt is only possible if both sides agree.
        token = service.cipher.encrypt(b"round-trip-probe")
        assert Fernet(key).decrypt(token) == b"round-trip-probe"

        assert (canonical_dir / "secrets.key").read_bytes() == key
        assert not (legacy_data_dir / "secrets.key").exists()


class TestComposeCanonicalDataDirIsPersistent:
    """#14081 review round 5, finding 1: under docker-compose.yml, with no
    AUTOBOT_DATA_DIR configured, ssot_config.path.data_path (canonical)
    resolved to the container's ephemeral writable layer while the legacy
    CWD-relative resolver landed on the persistent backend_data named
    volume. The migration this PR added moved real secrets OFF durable
    storage and deleted the source -- the next `--force-recreate` or image
    update destroyed them.

    Parses the real docker-compose.yml (never a hand-written fixture), so a
    future edit that drops the AUTOBOT_DATA_DIR override re-triggers this
    failure rather than silently reintroducing it.
    """

    @staticmethod
    def _service_env(compose: dict, service_name: str) -> dict[str, str]:
        return dict(entry.split("=", 1) for entry in compose["services"][service_name]["environment"])

    @pytest.mark.parametrize("service_name", ["autobot-backend", "autobot-worker", "autobot-celery-beat"])
    def test_canonical_data_dir_matches_the_persistent_volume_mount(self, service_name):
        compose = yaml.safe_load((_REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
        service = compose["services"][service_name]

        volume_mount = next((v for v in service["volumes"] if v.startswith("backend_data:")), None)
        assert volume_mount is not None, f"{service_name} must mount the persistent backend_data volume"
        persistent_mount_point = volume_mount.split(":", 1)[1]

        env = self._service_env(compose, service_name)
        data_dir_setting = env.get("AUTOBOT_DATA_DIR", "")
        # Compose interpolation syntax `${AUTOBOT_DATA_DIR:-/app/data}` is
        # never expanded by a plain YAML load -- extract the default, which
        # is what applies for every operator who hasn't overridden it
        # (including this smoke test's own environment).
        match = re.search(r"\$\{AUTOBOT_DATA_DIR:-([^}]*)\}", data_dir_setting)
        assert match, (
            f"{service_name} must set AUTOBOT_DATA_DIR so ssot_config.path.data_path "
            "resolves under the persistent backend_data volume, not the container's "
            "ephemeral writable layer -- otherwise the legacy->canonical secrets-store "
            "migration moves real secrets off durable storage and deletes the source."
        )
        default_data_dir = match.group(1)

        assert default_data_dir == persistent_mount_point, (
            f"{service_name}: AUTOBOT_DATA_DIR default ({default_data_dir!r}) does not match "
            f"the backend_data volume's mount point ({persistent_mount_point!r}) -- the "
            "secrets-store migration would move data off the persistent volume."
        )
