# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Mirror routing: marker hit rotates, same-name unmarked row rotates + marks, no row creates (#17850)."""

import base64
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from services import credential_write as cw

_OWNER = uuid.uuid4()
_VAULT = f"user:{_OWNER}"
_ROOT = base64.urlsafe_b64decode(base64.urlsafe_b64encode(bytes(range(32))))


def _svc(monkeypatch, *, by_name=None):
    svc = MagicMock()
    svc.rotate_value = AsyncMock()
    svc.create = AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4(), owner_vault=_VAULT, extra_data=None))
    svc.find_by_name = AsyncMock(return_value=by_name)
    monkeypatch.setattr(
        "services.envelope_secrets_service.EnvelopeSecretsService",
        lambda root_key=None: svc,
    )
    return svc


async def _run(sess):
    await cw.mirror_in_session(sess, "sid-1", str(_OWNER), "v", _ROOT, name="connector:c:auth", secret_type="t")


async def test_name_hit_without_marker_rotates_and_marks(monkeypatch):
    row = SimpleNamespace(id=uuid.uuid4(), is_active=True, type="t", extra_data={"k": 1})
    svc = _svc(monkeypatch, by_name=row)
    monkeypatch.setattr(cw, "_find_by_marker", AsyncMock(return_value=None))
    await _run(MagicMock(flush=AsyncMock()))
    svc.rotate_value.assert_awaited_once()
    svc.create.assert_not_awaited()
    assert row.extra_data == {"k": 1, cw._MARKER: "sid-1"}


async def test_no_row_creates(monkeypatch):
    svc = _svc(monkeypatch)
    monkeypatch.setattr(cw, "_find_by_marker", AsyncMock(return_value=None))
    await _run(MagicMock(flush=AsyncMock()))
    svc.create.assert_awaited_once()
    svc.rotate_value.assert_not_awaited()
    assert svc.create.return_value.extra_data == {cw._MARKER: "sid-1"}


async def _refused(monkeypatch, **fields):
    row = SimpleNamespace(id=uuid.uuid4(), is_active=True, type="t", extra_data=None)
    row.__dict__.update(fields)
    svc = _svc(monkeypatch, by_name=row)
    monkeypatch.setattr(cw, "_find_by_marker", AsyncMock(return_value=None))
    await _run(MagicMock(flush=AsyncMock()))
    svc.rotate_value.assert_not_awaited()
    svc.create.assert_not_awaited()
    assert row.extra_data == fields.get("extra_data")


async def test_inactive_row_not_rotated(monkeypatch):
    await _refused(monkeypatch, is_active=False)


async def test_other_type_row_not_rotated(monkeypatch):
    await _refused(monkeypatch, type="other_type")


async def test_row_marked_for_another_credential_not_rotated(monkeypatch):
    await _refused(monkeypatch, extra_data={cw._MARKER: "other-sid"})


async def test_marker_hit_rotates(monkeypatch):
    row = SimpleNamespace(id=uuid.uuid4())
    svc = _svc(monkeypatch)
    monkeypatch.setattr(cw, "_find_by_marker", AsyncMock(return_value=row))
    await _run(MagicMock(flush=AsyncMock()))
    svc.rotate_value.assert_awaited_once()
    svc.find_by_name.assert_not_awaited()
    svc.create.assert_not_awaited()
