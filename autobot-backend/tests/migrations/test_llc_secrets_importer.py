# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the LLC company secrets → unified envelope importer (#10088 / Task 4).

Unlike the JSON/SQLite importers, ``llc_secrets`` already lives in the same
Postgres database as the unified store, so these tests insert legacy
``LLCSecret`` rows directly (through the ORM, against the same migration-built
schema) rather than standing up a separate file/connection, then import them
and verify each is envelope-readable via ``EnvelopeSecretsService`` owned by
its Company vault. Also verifies company isolation and that no secret value is
ever logged.

Deliberately imports ``autobot_shared.legacy_secret_keys`` (not
``llc.services.secret``) to build the legacy ciphertext: importing
``llc.services.secret`` transitively executes ``llc/services/__init__.py``,
which eagerly imports every concrete LLC service (including KB/RAG modules
that reach ``llm_shared`` and attempt live Redis connections at import time) —
exactly the heavyweight coupling this migration-gate suite must stay clear of
(see the umbrella's Task 4 discovery; filed separately).
"""

import base64
import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from autobot_shared.legacy_secret_keys import derive_llc_company_fernet
from autobot_shared.secrets_vault import VaultKind, VaultRef
from llc.models.secret import LLCSecret
from services.envelope_secrets_service import EnvelopeSecretsService, SecretAccessError
from services.llc_secrets_importer import import_llc_secrets
from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]

_ROOT = base64.urlsafe_b64decode(base64.urlsafe_b64encode(bytes(range(32))))
_MASTER_KEY = b"llc-migration-test-master-key-32b"
_COMPANY_A = "company-aaa"
_COMPANY_B = "company-bbb"


def _make_row(company_id: str, name: str, plaintext: str, agent: str = "agent-001", revoked: bool = False) -> LLCSecret:
    ciphertext = derive_llc_company_fernet(_MASTER_KEY, company_id).encrypt(plaintext.encode("utf-8"))
    from autobot_shared.time_utils import now_utc

    return LLCSecret(
        id=uuid.uuid4(),
        company_id=company_id,
        name=name,
        value=ciphertext,
        version=1,
        created_by_agent_id=agent,
        revoked_at=now_utc() if revoked else None,
    )


@pytest.fixture()
async def session(fresh_db_url):
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def test_imports_and_envelope_readable(session):
    row = _make_row(_COMPANY_A, "db-password", "s3cr3t-value")
    session.add(row)
    await session.flush()

    report = await import_llc_secrets(session, master_key=_MASTER_KEY, root_key=_ROOT)
    await session.commit()
    assert report.total == 1 and report.imported == 1 and report.failed == []

    svc = EnvelopeSecretsService(root_key=_ROOT)
    company_secrets = await svc.list_for_vaults(session, accessible_vaults={VaultRef(VaultKind.COMPANY, _COMPANY_A)})
    assert len(company_secrets) == 1
    assert company_secrets[0].extra_data["imported_from_llc_secrets"] == str(row.id)
    assert company_secrets[0].extra_data["legacy_company_id"] == _COMPANY_A
    value = await svc.read(
        session, secret_id=company_secrets[0].id, accessible_vaults={VaultRef(VaultKind.COMPANY, _COMPANY_A)}
    )
    assert value == b"s3cr3t-value"


async def test_idempotent_skips_already_imported(session):
    row = _make_row(_COMPANY_A, "k", "v")
    session.add(row)
    await session.flush()

    first = await import_llc_secrets(session, master_key=_MASTER_KEY, root_key=_ROOT)
    await session.commit()
    second = await import_llc_secrets(session, master_key=_MASTER_KEY, root_key=_ROOT)
    await session.commit()
    assert first.imported == 1
    assert second.total == 1 and second.imported == 0 and second.skipped_existing == 1


async def test_revoked_secret_not_imported(session):
    active = _make_row(_COMPANY_A, "active-key", "v1")
    revoked = _make_row(_COMPANY_A, "revoked-key", "v2", revoked=True)
    session.add_all([active, revoked])
    await session.flush()

    report = await import_llc_secrets(session, master_key=_MASTER_KEY, root_key=_ROOT)
    await session.commit()
    assert report.total == 1 and report.imported == 1

    svc = EnvelopeSecretsService(root_key=_ROOT)
    company_secrets = await svc.list_for_vaults(session, accessible_vaults={VaultRef(VaultKind.COMPANY, _COMPANY_A)})
    assert [s.name for s in company_secrets] == ["active-key"]


async def test_company_isolation_no_cross_company_read(session):
    """Company B holds no grant for Company A's imported secret — proves isolation."""
    row_a = _make_row(_COMPANY_A, "a-secret", "a-value")
    row_b = _make_row(_COMPANY_B, "b-secret", "b-value")
    session.add_all([row_a, row_b])
    await session.flush()

    await import_llc_secrets(session, master_key=_MASTER_KEY, root_key=_ROOT)
    await session.commit()

    svc = EnvelopeSecretsService(root_key=_ROOT)
    a_secrets = await svc.list_for_vaults(session, accessible_vaults={VaultRef(VaultKind.COMPANY, _COMPANY_A)})
    assert len(a_secrets) == 1

    with pytest.raises(SecretAccessError):
        await svc.read(session, secret_id=a_secrets[0].id, accessible_vaults={VaultRef(VaultKind.COMPANY, _COMPANY_B)})


async def test_bad_ciphertext_reported_not_batch_abort(session):
    ok_row = _make_row(_COMPANY_A, "ok", "v")
    bad_row = _make_row(_COMPANY_A, "bad", "v")
    bad_row.value = b"not-a-fernet-token"
    session.add_all([ok_row, bad_row])
    await session.flush()

    report = await import_llc_secrets(session, master_key=_MASTER_KEY, root_key=_ROOT)
    await session.commit()
    assert report.total == 2 and report.imported == 1 and len(report.failed) == 1
    assert str(ok_row.id) not in "".join(report.failed)


async def test_wrong_company_key_reported_not_batch_abort(session):
    """A row decrypted with a *different* company's derived key never wraps as ciphertext-valid
    for its own company — this exercises the same decrypt-failure path as bit-corrupted data."""
    good = _make_row(_COMPANY_A, "good", "v1")
    cross = _make_row(_COMPANY_B, "cross", "v2")
    # Simulate dirty data: this row's declared company_id doesn't match the key used to encrypt it.
    cross.value = derive_llc_company_fernet(_MASTER_KEY, _COMPANY_A).encrypt(b"v2")
    session.add_all([good, cross])
    await session.flush()

    report = await import_llc_secrets(session, master_key=_MASTER_KEY, root_key=_ROOT)
    await session.commit()
    assert report.total == 2 and report.imported == 1 and len(report.failed) == 1


async def test_import_never_logs_secret_value(session, caplog):
    plaintext = "super-secret-plaintext-xyz"
    row = _make_row(_COMPANY_A, "k", plaintext)
    session.add(row)
    await session.flush()

    with caplog.at_level("DEBUG"):
        report = await import_llc_secrets(session, master_key=_MASTER_KEY, root_key=_ROOT)
        await session.commit()

    assert report.imported == 1
    assert plaintext not in caplog.text
    assert all(plaintext not in failure for failure in report.failed)


async def test_legacy_fernet_still_readable(session):
    """The legacy row and its Fernet ciphertext are untouched by the import (no retirement)."""
    row = _make_row(_COMPANY_A, "k", "still-here")
    session.add(row)
    await session.flush()

    await import_llc_secrets(session, master_key=_MASTER_KEY, root_key=_ROOT)
    await session.commit()

    # The legacy row's own cipher must still decrypt via the exact same derivation the
    # live SecretService uses -- proves llc_secrets was left fully intact, not migrated
    # in-place or retired.
    plaintext = derive_llc_company_fernet(_MASTER_KEY, _COMPANY_A).decrypt(row.value)
    assert plaintext == b"still-here"
