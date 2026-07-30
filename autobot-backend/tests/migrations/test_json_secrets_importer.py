# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the legacy JSON file → unified envelope importer (#10088 / Task 3).

Builds a legacy ``secrets.json`` file directly (the exact on-disk shape
``SecretsManager._save_secrets`` produces) rather than importing ``api.secrets`` —
that module pulls in the whole FastAPI app surface (auth middleware, memory graph,
plugin SDK, which transitively imports ``jsonschema``), which the migration-gate
environment deliberately keeps minimal (see ``.github/workflows/migration-gate.yml``).
Imports it into a Postgres unified store (migration-gate) and verifies each row is
envelope-readable via ``EnvelopeSecretsService`` owned by the System vault. Also
verifies the ``json_secrets_read`` dual-read path and that no secret value is ever
logged.
"""

import base64
import json
import uuid
from datetime import datetime, timezone

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from autobot_shared.secrets_vault import VaultKind, VaultRef
from services.envelope_secrets_service import EnvelopeSecretsService
from services.json_secrets_importer import import_json_secrets
from services.json_secrets_read import read_imported_json_secret_in_session
from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]

_ROOT = base64.urlsafe_b64decode(base64.urlsafe_b64encode(bytes(range(32))))
_FERNET = Fernet(Fernet.generate_key())


def _encrypt(value: str) -> str:
    """Mirror ``SecretsManager._encrypt_value``: base64(fernet.encrypt(value))."""
    return base64.b64encode(_FERNET.encrypt(value.encode("utf-8"))).decode("utf-8")


def _row(secret_id: str, name: str, value: str | None, **kwargs) -> dict:
    """One legacy ``secrets.json`` row, matching ``SecretModel`` + ``encrypted_value``."""
    now = datetime.now(tz=timezone.utc).isoformat()
    return {
        "id": secret_id,
        "name": name,
        "type": kwargs.get("type", "api_key"),
        "scope": kwargs.get("scope", "general"),
        "chat_id": kwargs.get("chat_id"),
        "description": kwargs.get("description"),
        "tags": kwargs.get("tags", []),
        "created_at": now,
        "updated_at": now,
        "expires_at": kwargs.get("expires_at"),
        "metadata": kwargs.get("metadata", {}),
        "encrypted_value": _encrypt(value) if value is not None else kwargs.get("raw_encrypted_value"),
    }


def _write_store(tmp_path, rows: dict) -> str:
    path = tmp_path / "secrets.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f)
    return str(path)


@pytest.fixture()
async def session(fresh_db_url):
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def test_imports_and_envelope_readable(session, tmp_path):
    sid = str(uuid.uuid4())
    path = _write_store(tmp_path, {sid: _row(sid, "openai-key", "sk-abc123")})

    report = await import_json_secrets(session, secrets_path=path, fernet=_FERNET, root_key=_ROOT)
    await session.commit()
    assert report.total == 1 and report.imported == 1 and report.failed == []

    svc = EnvelopeSecretsService(root_key=_ROOT)
    system_secrets = await svc.list_for_vaults(session, accessible_vaults={VaultRef(VaultKind.SYSTEM)})
    assert len(system_secrets) == 1
    assert system_secrets[0].extra_data["imported_from_json"] == sid
    assert system_secrets[0].extra_data["legacy_scope"] == "general"
    value = await svc.read(session, secret_id=system_secrets[0].id, accessible_vaults={VaultRef(VaultKind.SYSTEM)})
    assert value == b"sk-abc123"


async def test_idempotent_skips_already_imported(session, tmp_path):
    sid = str(uuid.uuid4())
    path = _write_store(tmp_path, {sid: _row(sid, "k", "v")})

    first = await import_json_secrets(session, secrets_path=path, fernet=_FERNET, root_key=_ROOT)
    await session.commit()
    second = await import_json_secrets(session, secrets_path=path, fernet=_FERNET, root_key=_ROOT)
    await session.commit()
    assert first.imported == 1
    assert second.total == 1 and second.imported == 0 and second.skipped_existing == 1


async def test_dual_read_reconstructs_legacy_shape(session, tmp_path):
    sid = str(uuid.uuid4())
    path = _write_store(tmp_path, {sid: _row(sid, "hf-token", "hf-secret-value", description="HF token", tags=["ml"])})

    report = await import_json_secrets(session, secrets_path=path, fernet=_FERNET, root_key=_ROOT)
    await session.commit()
    assert report.imported == 1

    result = await read_imported_json_secret_in_session(session, sid, _ROOT)
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


async def test_missing_encrypted_value_reported(session, tmp_path):
    sid = str(uuid.uuid4())
    path = _write_store(tmp_path, {sid: _row(sid, "k", None, raw_encrypted_value="")})

    report = await import_json_secrets(session, secrets_path=path, fernet=_FERNET, root_key=_ROOT)
    assert report.total == 1 and report.imported == 0 and len(report.failed) == 1


async def test_bad_ciphertext_reported_not_batch_abort(session, tmp_path):
    ok_id, bad_id = str(uuid.uuid4()), str(uuid.uuid4())
    path = _write_store(
        tmp_path,
        {
            ok_id: _row(ok_id, "ok", "v"),
            bad_id: _row(bad_id, "bad", None, raw_encrypted_value="not-a-fernet-token"),
        },
    )

    report = await import_json_secrets(session, secrets_path=path, fernet=_FERNET, root_key=_ROOT)
    await session.commit()
    assert report.total == 2 and report.imported == 1 and len(report.failed) == 1
    assert ok_id not in "".join(report.failed)


async def test_import_never_logs_secret_value(session, tmp_path, caplog):
    """No plaintext secret value appears in logs or the failure report during import."""
    sid = str(uuid.uuid4())
    plaintext = "super-secret-plaintext-xyz"
    path = _write_store(tmp_path, {sid: _row(sid, "k", plaintext)})

    with caplog.at_level("DEBUG"):
        report = await import_json_secrets(session, secrets_path=path, fernet=_FERNET, root_key=_ROOT)
        await session.commit()

    assert report.imported == 1
    assert plaintext not in caplog.text
    assert all(plaintext not in failure for failure in report.failed)


async def test_dual_read_never_logs_secret_value(session, tmp_path, caplog):
    """No plaintext secret value appears in logs when the dual-read path decrypts it."""
    sid = str(uuid.uuid4())
    plaintext = "super-secret-plaintext-xyz"
    path = _write_store(tmp_path, {sid: _row(sid, "k", plaintext)})
    await import_json_secrets(session, secrets_path=path, fernet=_FERNET, root_key=_ROOT)
    await session.commit()

    with caplog.at_level("DEBUG"):
        result = await read_imported_json_secret_in_session(session, sid, _ROOT)

    assert result["value"] == plaintext
    assert plaintext not in caplog.text
