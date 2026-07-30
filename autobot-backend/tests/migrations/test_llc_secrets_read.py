# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the LLC company secrets dual-read module (#10088 / Task 4).

Exercises ``services.llc_secrets_read`` directly against a Postgres-backed
unified store. Deliberately builds legacy rows via ``autobot_shared.
legacy_secret_keys`` rather than ``llc.services.secret.SecretService``:
importing that module transitively executes ``llc/services/__init__.py``,
which eagerly imports every concrete LLC service (KB/RAG modules that reach
``llm_shared`` and attempt live Redis connections at import time) — exactly
the heavyweight coupling this migration-gate suite must stay clear of (see
the umbrella's Task 4 discovery; filed separately as a pre-existing bug).

The ``SecretService.get()`` wiring itself (which calls this module only after
its own revoke-check, so a revoked/absent legacy secret never reaches the
unified store) is proven with mocks in ``llc/tests/test_secrets.py`` — that
suite already imports ``llc.services.secret`` for its own purposes and is not
part of the migration-gate path.
"""

import base64
import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from autobot_shared.legacy_secret_keys import derive_llc_company_fernet
from llc.models.secret import LLCSecret
from services.llc_secrets_importer import import_llc_secrets
from services.llc_secrets_read import llc_unified_read_enabled, read_imported_llc_secret_in_session
from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]

_ROOT = base64.urlsafe_b64decode(base64.urlsafe_b64encode(bytes(range(32))))
_MASTER_KEY = b"llc-migration-test-master-key-32b"
_COMPANY = "company-read-test"


def _make_row(company_id: str, name: str, plaintext: str) -> LLCSecret:
    ciphertext = derive_llc_company_fernet(_MASTER_KEY, company_id).encrypt(plaintext.encode("utf-8"))
    return LLCSecret(
        id=uuid.uuid4(), company_id=company_id, name=name, value=ciphertext, version=1, created_by_agent_id="agent-1"
    )


@pytest.fixture()
async def session(fresh_db_url):
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def test_dual_read_serves_imported_secret(session):
    row = _make_row(_COMPANY, "api-key", "legacy-plaintext")
    session.add(row)
    await session.flush()

    report = await import_llc_secrets(session, master_key=_MASTER_KEY, root_key=_ROOT)
    await session.commit()
    assert report.imported == 1

    value = await read_imported_llc_secret_in_session(
        session, source_id=str(row.id), company_id=_COMPANY, root_key=_ROOT
    )
    assert value == "legacy-plaintext"


async def test_unimported_secret_returns_none(session):
    """A source id never imported falls back (dual-read returns None -> legacy Fernet decrypt)."""
    result = await read_imported_llc_secret_in_session(
        session, source_id=str(uuid.uuid4()), company_id=_COMPANY, root_key=_ROOT
    )
    assert result is None


async def test_wrong_company_vault_denied(session):
    """A grantee from a different company vault cannot open the imported secret."""
    row = _make_row(_COMPANY, "api-key", "legacy-plaintext")
    session.add(row)
    await session.flush()
    await import_llc_secrets(session, master_key=_MASTER_KEY, root_key=_ROOT)
    await session.commit()

    result = await read_imported_llc_secret_in_session(
        session, source_id=str(row.id), company_id="some-other-company", root_key=_ROOT
    )
    assert result is None  # SecretAccessError caught internally -> fall back, never raise


async def test_dual_read_never_logs_secret_value(session, caplog):
    plaintext = "super-secret-plaintext-xyz"
    row = _make_row(_COMPANY, "logged-key", plaintext)
    session.add(row)
    await session.flush()
    await import_llc_secrets(session, master_key=_MASTER_KEY, root_key=_ROOT)
    await session.commit()

    with caplog.at_level("DEBUG"):
        value = await read_imported_llc_secret_in_session(
            session, source_id=str(row.id), company_id=_COMPANY, root_key=_ROOT
        )

    assert value == plaintext
    assert plaintext not in caplog.text


def test_env_helper_reads_flag_case_insensitively(monkeypatch):
    monkeypatch.setenv("AUTOBOT_SECRETS_LLC_UNIFIED_READ", "True")
    assert llc_unified_read_enabled() is True
    monkeypatch.setenv("AUTOBOT_SECRETS_LLC_UNIFIED_READ", "0")
    assert llc_unified_read_enabled() is False
    monkeypatch.delenv("AUTOBOT_SECRETS_LLC_UNIFIED_READ", raising=False)
    assert llc_unified_read_enabled() is False
