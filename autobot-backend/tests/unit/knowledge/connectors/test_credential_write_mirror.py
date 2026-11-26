# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Mirror routing: marker hit rotates, same-name unmarked row rotates + marks, no row creates (#17850)."""

import base64
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from models.secret import Secret
from services import credential_write as cw

_OWNER = uuid.uuid4()
_VAULT = f"user:{_OWNER}"
_ROOT = base64.urlsafe_b64decode(base64.urlsafe_b64encode(bytes(range(32))))


def _svc(monkeypatch, *, by_name=None):
    svc = MagicMock()
    svc.rotate_value = AsyncMock()
    svc.create = AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4(), owner_vault=_VAULT, extra_data=None))
    svc.find_by_name = AsyncMock(return_value=by_name)
    svc.grantees = AsyncMock(return_value={_VAULT})
    monkeypatch.setattr(
        "services.envelope_secrets_service.EnvelopeSecretsService",
        lambda root_key=None: svc,
    )
    return svc


async def _run(sess):
    await cw.mirror_in_session(sess, "sid-1", str(_OWNER), "v", _ROOT, name="connector:c:auth", secret_type="t")


async def test_name_hit_without_marker_rotates_and_marks(monkeypatch):
    row = Secret(id=uuid.uuid4(), is_active=True, type="t", extra_data={"k": 1}, owner_vault=_VAULT)
    svc = _svc(monkeypatch, by_name=row)
    monkeypatch.setattr(cw, "_find_by_marker", AsyncMock(return_value=None))
    await _run(MagicMock(flush=AsyncMock(), refresh=AsyncMock()))
    svc.rotate_value.assert_awaited_once()
    svc.create.assert_not_awaited()
    assert row.extra_data == {"k": 1, cw._MARKER: "sid-1"}


async def test_no_row_creates(monkeypatch):
    svc = _svc(monkeypatch)
    monkeypatch.setattr(cw, "_find_by_marker", AsyncMock(return_value=None))
    await _run(MagicMock(flush=AsyncMock(), refresh=AsyncMock()))
    svc.create.assert_awaited_once()
    svc.rotate_value.assert_not_awaited()
    assert svc.create.return_value.extra_data == {cw._MARKER: "sid-1"}


async def _refused(monkeypatch, **fields):
    row = Secret(
        id=uuid.uuid4(), **{"is_active": True, "type": "t", "extra_data": None, "owner_vault": _VAULT, **fields}
    )
    svc = _svc(monkeypatch, by_name=row)
    monkeypatch.setattr(cw, "_find_by_marker", AsyncMock(return_value=None))
    await _run(MagicMock(flush=AsyncMock(), refresh=AsyncMock()))
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
    await _run(MagicMock(flush=AsyncMock(), refresh=AsyncMock()))
    svc.rotate_value.assert_awaited_once()
    svc.find_by_name.assert_not_awaited()
    svc.create.assert_not_awaited()


async def test_delete_failure_log_carries_no_identifier_value_or_message(monkeypatch, caplog):
    """The reconciliation ERROR names the exception class only (CodeQL py/clear-text-logging-sensitive-data)."""
    import logging

    leaky_text = "canary-0xDEADBEEF"
    monkeypatch.setattr(cw, "_root_key_or_none", lambda: _ROOT)
    monkeypatch.setattr(
        "user_management.database.get_async_session_factory",
        lambda: (_ for _ in ()).throw(RuntimeError(leaky_text)),
    )
    with caplog.at_level(logging.DEBUG, logger=cw.logger.name):
        await cw.delete_credential_from_vault("sid-private-1", str(_OWNER))
    records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(records) == 1
    text = records[0].getMessage()
    assert "RuntimeError" in text
    for leaked in (leaky_text, "sid-private-1", str(_OWNER)):
        assert leaked not in text


async def test_rotate_skip_log_carries_no_identifier(caplog):
    import logging

    with caplog.at_level(logging.DEBUG, logger=cw.logger.name):
        await cw._rotate_or_skip(MagicMock(), MagicMock(), MagicMock(), None, "sid-private-2", "v")
    assert caplog.records
    assert all("sid-private-2" not in r.getMessage() for r in caplog.records)


async def test_row_granted_to_another_vault_not_adopted(monkeypatch):
    row = Secret(id=uuid.uuid4(), is_active=True, type="t", extra_data=None, owner_vault=_VAULT)
    svc = _svc(monkeypatch, by_name=row)
    svc.grantees = AsyncMock(return_value={_VAULT, "user:someone-else"})
    monkeypatch.setattr(cw, "_find_by_marker", AsyncMock(return_value=None))
    await _run(MagicMock(flush=AsyncMock(), refresh=AsyncMock()))
    svc.rotate_value.assert_not_awaited()
    svc.create.assert_not_awaited()
    assert row.extra_data is None


async def test_create_returning_another_mirrors_row_does_not_restamp(monkeypatch):
    svc = _svc(monkeypatch)
    other = SimpleNamespace(
        id=uuid.uuid4(),
        owner_vault=_VAULT,
        type="t",
        is_live=True,
        already_existed=True,
        extra_data={cw._MARKER: "other-sid"},
    )
    svc.create = AsyncMock(return_value=other)
    monkeypatch.setattr(cw, "_find_by_marker", AsyncMock(return_value=None))
    await _run(MagicMock(flush=AsyncMock(), refresh=AsyncMock()))
    assert other.extra_data == {cw._MARKER: "other-sid"}
    svc.rotate_value.assert_not_awaited()


async def test_create_returning_same_plaintext_unmarked_row_is_stamped(monkeypatch):
    svc = _svc(monkeypatch)
    row = SimpleNamespace(
        id=uuid.uuid4(), owner_vault=_VAULT, type="t", is_live=True, already_existed=True, extra_data=None
    )
    svc.create = AsyncMock(return_value=row)
    monkeypatch.setattr(cw, "_find_by_marker", AsyncMock(return_value=None))
    await _run(MagicMock(flush=AsyncMock(), refresh=AsyncMock()))
    assert row.extra_data == {cw._MARKER: "sid-1"}


async def test_marker_lookup_is_by_owning_vault_not_creator():
    """An adopted row created by another actor is still found, because the filter is owner_vault."""
    captured = {}

    async def _execute(stmt):
        captured["sql"] = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        return MagicMock(scalars=lambda: MagicMock(first=lambda: None))

    await cw._find_by_marker(MagicMock(execute=_execute), "sid-1", _VAULT)
    where = captured["sql"].split("WHERE", 1)[1]
    assert "owner_vault" in where
    assert "owner_id" not in where


def _session_answering(row):
    """A session whose one marker query returns *row*; the recorded statement shows what that query asked."""
    from testkit.fake_async_session import FakeAsyncSession, FakeResult

    return FakeAsyncSession(results=[FakeResult([row])])


def _assert_asked_for_the_vault(session, row):
    """The marker query bound the owning vault and the marker, and never the creator's id."""
    bound = set(map(str, session.statements[0].compile().params.values()))
    assert {row.owner_vault, row.extra_data[cw._MARKER]} <= bound
    assert str(row.owner_id) not in bound and str(_OWNER) not in bound


def _adopted_row_by_another_actor():
    """A row created by actor B (owner_id) in the user's vault, stamped with the marker."""
    return SimpleNamespace(id=uuid.uuid4(), owner_id=uuid.uuid4(), owner_vault=_VAULT, extra_data={cw._MARKER: "sid-1"})


async def test_rotation_by_the_vault_user_finds_a_row_created_by_another_actor(monkeypatch):
    row = _adopted_row_by_another_actor()
    svc = _svc(monkeypatch)
    session = _session_answering(row)
    await cw.mirror_in_session(session, "sid-1", str(_OWNER), "new-value", _ROOT)
    _assert_asked_for_the_vault(session, row)
    svc.rotate_value.assert_awaited_once()
    assert svc.rotate_value.await_args.kwargs["secret_id"] == row.id
    assert svc.rotate_value.await_args.kwargs["new_plaintext"] == b"new-value"
    svc.create.assert_not_awaited()


async def test_revocation_by_the_vault_user_removes_a_row_created_by_another_actor(monkeypatch):
    row = _adopted_row_by_another_actor()
    svc = _svc(monkeypatch)
    svc.delete = AsyncMock()
    session = _session_answering(row)
    await cw.delete_in_session(session, "sid-1", str(_OWNER), _ROOT)
    _assert_asked_for_the_vault(session, row)
    svc.delete.assert_awaited_once()
    assert svc.delete.await_args.kwargs["secret_id"] == row.id


async def test_adoption_locks_the_row_before_the_grant_check_and_stamp(monkeypatch):
    row = Secret(id=uuid.uuid4(), is_active=True, type="t", extra_data=None, owner_vault=_VAULT)
    _svc(monkeypatch, by_name=row)
    monkeypatch.setattr(cw, "_find_by_marker", AsyncMock(return_value=None))
    sess = MagicMock(flush=AsyncMock(), refresh=AsyncMock())
    await _run(sess)
    sess.refresh.assert_awaited_once_with(row, with_for_update=True)


async def test_create_returning_a_reused_row_rotates_it_under_the_lock_before_stamping(monkeypatch):
    svc = _svc(monkeypatch)
    row = SimpleNamespace(
        id=uuid.uuid4(), owner_vault=_VAULT, type="t", is_live=True, already_existed=True, extra_data=None
    )
    svc.create = AsyncMock(return_value=row)
    order = []
    sess = MagicMock(flush=AsyncMock(), refresh=AsyncMock(side_effect=lambda *a, **k: order.append("lock")))
    svc.rotate_value.side_effect = lambda *a, **k: order.append("rotate")
    monkeypatch.setattr(cw, "_find_by_marker", AsyncMock(return_value=None))
    await _run(sess)
    assert order == ["lock", "rotate"]
    assert svc.rotate_value.await_args.kwargs["secret_id"] == row.id
    assert row.extra_data == {cw._MARKER: "sid-1"}
