# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the legacy JSON file → unified envelope importer (#10088 / Task 3).

Builds a legacy ``secrets.json`` + ``secrets.key`` file store in a temp dir (bypassing
``SecretsManager.__init__`` so no real data directory is touched), imports it into a
Postgres unified store (migration-gate), and verifies each row is envelope-readable via
``EnvelopeSecretsService`` owned by the System vault. Also verifies the ``json_secrets_read``
dual-read path and that no secret value is ever logged.
"""

import base64
import threading
import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from autobot_shared.secrets_vault import VaultKind, VaultRef
from services.envelope_secrets_service import EnvelopeSecretsService
from services.json_secrets_importer import import_json_secrets
from services.json_secrets_read import read_imported_json_secret_in_session
from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]

_ROOT = base64.urlsafe_b64decode(base64.urlsafe_b64encode(bytes(range(32))))


def _make_store(tmp_path):
    """A ``SecretsManager`` rooted at *tmp_path*, bypassing ``__init__``'s real data dir."""
    from api.secrets import SecretsManager

    mgr = SecretsManager.__new__(SecretsManager)
    mgr.secrets_file = str(tmp_path / "secrets.json")
    mgr.key_file = str(tmp_path / "secrets.key")
    mgr._initialize_encryption()
    mgr._secrets_cache = None
    mgr._cache_lock = threading.RLock()
    mgr._cache_mtime = None
    return mgr


def _create(mgr, name: str, value: str, **kwargs):
    from api.schemas_system import ChatSecretScope, SecretCreateRequest, SecretType

    req = SecretCreateRequest(
        name=name,
        type=kwargs.pop("type", SecretType.API_KEY),
        scope=kwargs.pop("scope", ChatSecretScope.GENERAL),
        value=value,
        **kwargs,
    )
    return mgr.create_secret(req)


@pytest.fixture()
async def session(fresh_db_url):
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def test_imports_and_envelope_readable(session, tmp_path, monkeypatch):
    mgr = _make_store(tmp_path)
    secret = _create(mgr, "openai-key", "sk-abc123")
    monkeypatch.setattr("api.secrets.secrets_manager", mgr)

    report = await import_json_secrets(session, root_key=_ROOT)
    await session.commit()
    assert report.total == 1 and report.imported == 1 and report.failed == []

    svc = EnvelopeSecretsService(root_key=_ROOT)
    system_secrets = await svc.list_for_vaults(session, accessible_vaults={VaultRef(VaultKind.SYSTEM)})
    assert len(system_secrets) == 1
    assert system_secrets[0].extra_data["imported_from_json"] == secret.id
    assert system_secrets[0].extra_data["legacy_scope"] == "general"
    value = await svc.read(session, secret_id=system_secrets[0].id, accessible_vaults={VaultRef(VaultKind.SYSTEM)})
    assert value == b"sk-abc123"


async def test_idempotent_skips_already_imported(session, tmp_path, monkeypatch):
    mgr = _make_store(tmp_path)
    _create(mgr, "k", "v")
    monkeypatch.setattr("api.secrets.secrets_manager", mgr)

    first = await import_json_secrets(session, root_key=_ROOT)
    await session.commit()
    second = await import_json_secrets(session, root_key=_ROOT)
    await session.commit()
    assert first.imported == 1
    assert second.total == 1 and second.imported == 0 and second.skipped_existing == 1


async def test_dual_read_reconstructs_legacy_shape(session, tmp_path, monkeypatch):
    mgr = _make_store(tmp_path)
    secret = _create(mgr, "hf-token", "hf-secret-value", description="HF token", tags=["ml"])
    monkeypatch.setattr("api.secrets.secrets_manager", mgr)

    report = await import_json_secrets(session, root_key=_ROOT)
    await session.commit()
    assert report.imported == 1

    result = await read_imported_json_secret_in_session(session, secret.id, _ROOT)
    assert result is not None
    assert result["value"] == "hf-secret-value"
    assert result["name"] == "hf-token"
    assert result["description"] == "HF token"
    assert result["tags"] == ["ml"]
    assert result["scope"] == "general"


async def test_unimported_secret_returns_none(session):
    """A secret_id never imported falls back (dual-read returns None -> legacy file read)."""
    result = await read_imported_json_secret_in_session(session, str(uuid.uuid4()), _ROOT)
    assert result is None


async def test_missing_encrypted_value_reported(session, tmp_path, monkeypatch):
    mgr = _make_store(tmp_path)
    secret = _create(mgr, "k", "v")
    monkeypatch.setattr("api.secrets.secrets_manager", mgr)

    # Corrupt the on-disk row to simulate dirty legacy data.
    secrets = mgr._load_secrets()
    secrets[secret.id]["encrypted_value"] = ""
    mgr._save_secrets(secrets)

    report = await import_json_secrets(session, root_key=_ROOT)
    assert report.total == 1 and report.imported == 0 and len(report.failed) == 1


async def test_bad_ciphertext_reported_not_batch_abort(session, tmp_path, monkeypatch):
    mgr = _make_store(tmp_path)
    ok = _create(mgr, "ok", "v")
    bad = _create(mgr, "bad", "v2")
    monkeypatch.setattr("api.secrets.secrets_manager", mgr)

    secrets = mgr._load_secrets()
    secrets[bad.id]["encrypted_value"] = "not-a-fernet-token"
    mgr._save_secrets(secrets)

    report = await import_json_secrets(session, root_key=_ROOT)
    await session.commit()
    assert report.total == 2 and report.imported == 1 and len(report.failed) == 1
    assert ok.id not in "".join(report.failed)


async def test_import_never_logs_secret_value(session, tmp_path, monkeypatch, caplog):
    """No plaintext secret value appears in logs or the failure report during import."""
    mgr = _make_store(tmp_path)
    plaintext = "super-secret-plaintext-xyz"
    _create(mgr, "k", plaintext)
    monkeypatch.setattr("api.secrets.secrets_manager", mgr)

    with caplog.at_level("DEBUG"):
        report = await import_json_secrets(session, root_key=_ROOT)
        await session.commit()

    assert report.imported == 1
    assert plaintext not in caplog.text
    assert all(plaintext not in failure for failure in report.failed)


async def test_dual_read_never_logs_secret_value(session, tmp_path, monkeypatch, caplog):
    """No plaintext secret value appears in logs when the dual-read path decrypts it."""
    mgr = _make_store(tmp_path)
    plaintext = "super-secret-plaintext-xyz"
    secret = _create(mgr, "k", plaintext)
    monkeypatch.setattr("api.secrets.secrets_manager", mgr)
    await import_json_secrets(session, root_key=_ROOT)
    await session.commit()

    with caplog.at_level("DEBUG"):
        result = await read_imported_json_secret_in_session(session, secret.id, _ROOT)

    assert result["value"] == plaintext
    assert plaintext not in caplog.text
