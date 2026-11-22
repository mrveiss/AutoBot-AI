# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The audit chain writer's key handling and row completion (#17219).

The lock, tail read and sequence under PostgreSQL are covered by
``autobot-backend/tests/migrations/test_audit_chain_17219.py`` (a real database).
"""

import base64
from types import SimpleNamespace

import pytest

from autobot_shared import audit_chain_writer as writer
from autobot_shared.secrets_envelope import ROOT_KEY_ENV, derive_audit_chain_key
from autobot_shared.user_management.audit_rows import audit_row


@pytest.fixture(autouse=True)
def _fresh_key_cache(monkeypatch):
    monkeypatch.setattr(writer, "_key_cache", {})


def _set_root_key(monkeypatch) -> bytes:
    root = b"r" * 32
    monkeypatch.setenv(ROOT_KEY_ENV, base64.urlsafe_b64encode(root).decode("ascii"))
    return root


def test_without_a_root_key_the_service_refuses_to_start(monkeypatch) -> None:
    monkeypatch.delenv(ROOT_KEY_ENV, raising=False)
    with pytest.raises(writer.ChainKeyUnavailable):
        writer.require_chain_key()


def test_without_a_root_key_no_row_is_written(monkeypatch) -> None:
    monkeypatch.delenv(ROOT_KEY_ENV, raising=False)
    connection = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    with pytest.raises(writer.ChainKeyUnavailable):
        writer._seal_row(SimpleNamespace(local_table=None), connection, audit_row(action="x", resource_type="r"))


def test_the_key_is_derived_from_the_root_key_and_differs_from_it(monkeypatch) -> None:
    root = _set_root_key(monkeypatch)
    key, kid = writer.chain_key()
    assert key == derive_audit_chain_key(root) and key != root and kid != key.hex()


def test_the_key_error_does_not_carry_key_material(monkeypatch) -> None:
    monkeypatch.setenv(ROOT_KEY_ENV, "not-base64-!!")
    with pytest.raises(writer.ChainKeyUnavailable) as raised:
        writer.chain_key()
    assert "not-base64-!!" not in str(raised.value)


def test_a_dialect_without_the_chain_gets_complete_rows_and_no_chain(monkeypatch) -> None:
    monkeypatch.delenv(ROOT_KEY_ENV, raising=False)  # would fail closed on PostgreSQL
    org = __import__("uuid").uuid4()
    row = audit_row(action="x", resource_type="r", org_id=org)
    row.outcome, row.details, row.created_at = None, None, None
    writer._seal_row(SimpleNamespace(local_table=None), SimpleNamespace(dialect=SimpleNamespace(name="sqlite")), row)
    assert (row.outcome, row.details, row.org_ref) == ("success", {}, str(org))
    assert row.created_at is not None and row.chain_seq is None and row.row_mac is None
