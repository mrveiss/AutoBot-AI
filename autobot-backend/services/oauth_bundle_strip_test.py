# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The OAuth bundle strip (#13630): dry run writes nothing, strip is gated, verified and value-free."""

import asyncio
import json
import uuid

import pytest

import api.admin_oauth_bundle_strip as proposer
from api.schemas_oauth_bundle_strip import OAuthBundleStripRequest
from autobot_shared.eventually import eventually
from autobot_shared.leader_lease import LeaderLease
from knowledge.connectors import oauth_flow
from knowledge.connectors.credential_store import _refresh_lock_key
from models.approval import Approval, ApprovalComment
from services import approval_execution, oauth_bundle_strip, oauth_bundle_strip_action
from services.approval_gate_service import ApprovalGateService
from testkit.fake_approval_session import ApprovalClaimSession

pytestmark = pytest.mark.asyncio

_SECRET = "app-client-secret-VALUE"  # pragma: allowlist secret
_LEGACY = {
    "access_token": "at-1",
    "refresh_token": "rt-1",
    "provider": "google",
    "token_url": "https://example.test/token",
    "scope": "s",
    "client_id": "app-id",
    "client_secret": _SECRET,
}


class _FakeSvc:
    def __init__(self, bundles: dict[str, str]):
        self.rows = dict(bundles)
        self.writes: list[str] = []
        self.corrupt_on_write = False

    def list_secrets(self, **_kw):
        return [{"id": sid} for sid in self.rows]

    def get_secret(self, secret_id=None, include_value=False, accessed_by=None, **_kw):
        value = self.rows.get(secret_id)
        return None if value is None else {"id": secret_id, "value": value, "created_by": "u1"}

    def update_secret(self, secret_id, value=None, updated_by=None, **_kw):
        self.writes.append(secret_id)
        if self.corrupt_on_write and "client_secret" not in value:
            value = json.dumps({**json.loads(value), "access_token": "tampered"})
        self.rows[secret_id] = value
        return True


class _Locks:
    """In-memory stand-in for the Redis lease: exclusive per key, like SET NX."""

    def __init__(self):
        self.held: dict[str, str] = {}

    def acquire(self, key: str, holder: str) -> bool:
        if key in self.held:
            return False
        self.held[key] = holder
        return True

    def release(self, key: str, holder: str) -> None:
        if self.held.get(key) == holder:
            del self.held[key]


@pytest.fixture(autouse=True)
def locks(monkeypatch):
    """Every test runs with the real lease factory over an in-memory exclusive lock."""
    state = _Locks()

    async def _acquire(self, *a, **k):
        return state.acquire(self.key, self.worker_id)

    async def _release(self, *a, **k):
        state.release(self.key, self.worker_id)

    monkeypatch.setattr(LeaderLease, "update_leadership", _acquire)
    monkeypatch.setattr(LeaderLease, "release", _release)
    return state


@pytest.fixture
def backup_verified(monkeypatch):
    """The verifier patched to True: its own behaviour is tested in secrets_backup_verifier_test.py (#18281)."""

    async def _verified(reference):
        return True

    monkeypatch.setattr(oauth_bundle_strip_action, "verify_backup", _verified)


@pytest.fixture
def configured(monkeypatch):
    """google is configured; microsoft is not."""
    real = oauth_flow.resolve_client_credentials

    def _resolve(provider):
        if provider.name == "google":
            return ("id", "secret")
        return real(provider)

    monkeypatch.setattr(oauth_flow, "resolve_client_credentials", _resolve)


def _svc(**extra):
    bundles = {
        "s-legacy": json.dumps(_LEGACY),
        "s-clean": json.dumps({k: v for k, v in _LEGACY.items() if "client" not in k}),
    }
    bundles.update(extra)
    return _FakeSvc(bundles)


async def test_preview_counts_without_writing_or_returning_values(configured):
    svc = _svc(**{"s-ms": json.dumps({**_LEGACY, "provider": "microsoft"}), "s-bad": "not json"})
    report = await oauth_bundle_strip.preview(svc, "admin")
    assert report.summary() == {
        "stripped": {"google": 1},
        "clean": {"google": 1},
        "skipped_unconfigured": {"microsoft": 1},
        "unreadable": {"unknown": 1},
    }
    assert svc.writes == []
    assert _SECRET not in json.dumps(report.summary()) + json.dumps(report.secret_ids)


async def test_strip_removes_only_app_credentials_and_preserves_tokens(configured):
    svc = _svc()
    before = oauth_bundle_strip.token_digest(_LEGACY)
    report = await oauth_bundle_strip.strip_all(svc, "approver")
    after = json.loads(svc.rows["s-legacy"])
    assert "client_id" not in after and "client_secret" not in after
    assert oauth_bundle_strip.token_digest(after) == before
    assert after["scope"] == "s"
    assert svc.writes == ["s-legacy"]  # the already-clean bundle is never rewritten
    assert report.count(oauth_bundle_strip.STRIPPED) == 1


async def test_unconfigured_provider_is_skipped_so_its_refresh_keeps_working(configured):
    svc = _FakeSvc({"s-ms": json.dumps({**_LEGACY, "provider": "microsoft"})})
    report = await oauth_bundle_strip.strip_all(svc, "approver")
    assert json.loads(svc.rows["s-ms"])["client_secret"] == _SECRET
    assert report.count(oauth_bundle_strip.SKIPPED_UNCONFIGURED) == 1 and svc.writes == []


async def test_digest_mismatch_restores_the_original(configured):
    svc = _svc()
    svc.corrupt_on_write = True
    original = svc.rows["s-legacy"]
    report = await oauth_bundle_strip.strip_all(svc, "approver")
    assert svc.rows["s-legacy"] == original
    assert report.count(oauth_bundle_strip.VERIFY_FAILED) == 1


async def test_bundle_whose_refresh_lease_is_held_is_skipped_not_stripped(configured, locks):
    svc = _svc()
    locks.acquire(_refresh_lock_key("s-legacy"), "refresher")
    report = await oauth_bundle_strip.strip_all(svc, "approver")
    assert report.summary()["lease_unavailable"] == {"unknown": 1}
    assert json.loads(svc.rows["s-legacy"])["client_secret"] == _SECRET and svc.writes == []


async def test_a_refresh_landing_between_the_strips_read_and_write_is_never_overwritten(configured, locks):
    """The #13627 lost-update race: a rotating provider's old refresh token is dead after a refresh.

    The refresh lands right after the strip's read. It can only write if it can take
    the per-credential lease; the strip must be holding it, so the refresh waits and
    runs afterwards against the CURRENT bundle. Without the lease the refresh lands
    mid-strip and the strip then writes its stale read over the new tokens.
    """
    svc = _svc()
    key = _refresh_lock_key("s-legacy")
    refreshed = {"access_token": "at-2", "refresh_token": "rt-2"}
    state = {"done": False, "blocked": 0}

    def _try_refresh():
        if state["done"]:
            return
        if not locks.acquire(key, "refresher"):
            state["blocked"] += 1
            return
        current = json.loads(svc.rows["s-legacy"])
        svc.rows["s-legacy"] = json.dumps({**current, **refreshed})
        locks.release(key, "refresher")
        state["done"] = True

    real_get = svc.get_secret
    first_read = []

    def _get(secret_id=None, **kw):
        row = real_get(secret_id=secret_id, **kw)
        if secret_id == "s-legacy" and not first_read:
            first_read.append(1)
            _try_refresh()  # lands between the strip's read and its write
        return row

    svc.get_secret = _get
    await oauth_bundle_strip.strip_all(svc, "approver")
    _try_refresh()  # a blocked refresh retries once the lease is free
    final = json.loads(svc.rows["s-legacy"])
    assert state["done"] and state["blocked"] == 1
    assert final["access_token"] == "at-2" and final["refresh_token"] == "rt-2"
    assert "client_secret" not in final


async def test_a_refresh_between_the_strips_write_and_its_vault_mirror_is_not_overwritten(
    configured, locks, monkeypatch
):
    """The mirror is inside the lease: a refresh cannot rotate+mirror between write and mirror."""
    monkeypatch.setenv("AUTOBOT_SECRETS_UNIFIED_WRITE", "true")
    svc = _svc()
    key = _refresh_lock_key("s-legacy")
    vault, state = [], {"done": False}

    def _try_refresh():
        if state["done"] or not locks.acquire(key, "refresher"):
            return
        svc.rows["s-legacy"] = json.dumps({**json.loads(svc.rows["s-legacy"]), "access_token": "at-2"})
        vault.append(("refresher", "at-2"))
        locks.release(key, "refresher")
        state["done"] = True

    async def _mirror(secret_id, owner, value):
        _try_refresh()  # a refresh lands after the strip's write, before its mirror
        vault.append(("strip", json.loads(value)["access_token"]))

    monkeypatch.setattr(oauth_bundle_strip, "mirror_credential_to_vault", _mirror)
    await oauth_bundle_strip.strip_all(svc, "approver")
    _try_refresh()  # the blocked refresh retries after the lease is free
    assert vault[-1] == ("refresher", "at-2"), vault
    assert json.loads(svc.rows["s-legacy"])["access_token"] == "at-2"


async def test_cancellation_waits_for_the_writing_thread_before_the_lease_is_released(configured, locks):
    import threading

    svc = _svc()
    key = _refresh_lock_key("s-legacy")
    started, proceed = threading.Event(), threading.Event()
    held_at_finish = []
    real_update = svc.update_secret

    def _slow_update(secret_id, **kw):
        started.set()
        proceed.wait(5)
        held_at_finish.append(key in locks.held)
        return real_update(secret_id, **kw)

    svc.update_secret = _slow_update
    task = asyncio.ensure_future(oauth_bundle_strip.strip_all(svc, "approver"))
    await eventually(started.is_set, watch=task)
    task.cancel()
    for _ in range(10):  # let the cancellation reach the task's shielded wait; no fixed interval
        await asyncio.sleep(0)
    assert key in locks.held  # still held while the thread is mid-write
    proceed.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert held_at_finish == [True] and key not in locks.held


def test_a_failing_restore_is_chained_to_the_original_error_not_masking_it():
    class _Svc:
        def update_secret(self, **kw):
            raise OSError("restore failed")

    cause = ValueError("first")
    with pytest.raises(OSError) as info:
        oauth_bundle_strip._restore(_Svc(), "s", "orig", "a", cause=cause)
    assert info.value.__cause__ is cause


async def test_one_bundle_failing_is_recorded_and_the_rest_are_still_processed(configured):
    svc = _svc(**{"s-boom": json.dumps(_LEGACY)})
    real_update = svc.update_secret

    def _update(secret_id, **kw):
        if secret_id == "s-boom":
            raise OSError("disk")
        return real_update(secret_id, **kw)

    svc.update_secret = _update
    report = await oauth_bundle_strip.strip_all(svc, "approver")
    assert report.secret_ids["error"] == ["s-boom"]
    assert report.secret_ids["stripped"] == ["s-legacy"]
    assert json.loads(svc.rows["s-boom"])["client_secret"] == _SECRET  # restored


class _Interrupt(BaseException):
    pass


async def test_an_interruption_halfway_still_writes_the_trail_for_the_partial_run(
    configured, backup_verified, monkeypatch
):
    svc = _svc(**{"s-third": json.dumps(_LEGACY)})
    monkeypatch.setattr("services.secrets_service.get_secrets_service", lambda: svc)
    audited, session = [], ApprovalClaimSession()

    async def _audit(op, **kw):
        audited.append(kw)

    monkeypatch.setattr(oauth_bundle_strip_action, "audit_log", _audit)
    real_strip = oauth_bundle_strip.strip_one_sync

    def _strip(svc_, secret_id, actor, report):
        if secret_id == "s-third":
            raise _Interrupt()
        return real_strip(svc_, secret_id, actor, report)

    monkeypatch.setattr(oauth_bundle_strip, "strip_one_sync", _strip)
    approval = Approval(context={"backup_reference": "snap"}, id=uuid.uuid4(), decided_by_user="human")
    with pytest.raises(_Interrupt):
        await oauth_bundle_strip_action.execute_oauth_bundle_strip(approval, session)
    body = session.added[0].body
    assert "INTERRUPTED" in body and "1 stripped" in body and "1 interrupted" in body
    assert audited[0]["result"] == "failed" and audited[0]["details"]["completed"] is False
    assert audited[0]["details"]["secret_ids"]["interrupted"] == ["s-third"]


async def test_digest_covers_every_field_but_the_app_credentials():
    base = json.loads(json.dumps(_LEGACY))
    digest = oauth_bundle_strip.token_digest(base)
    assert oauth_bundle_strip.token_digest({**base, "client_secret": "other"}) == digest  # pragma: allowlist secret
    assert oauth_bundle_strip.token_digest({**base, "id_token": "x"}) != digest  # a field outside the old fixed four
    assert oauth_bundle_strip.token_digest({**base, "scope": "other"}) != digest


async def _noop():
    return None


async def test_propose_then_approve_runs_the_strip_and_audits(configured, backup_verified, monkeypatch):
    svc = _svc()
    monkeypatch.setattr("services.secrets_service.get_secrets_service", lambda: svc)
    monkeypatch.setattr(ApprovalGateService, "_notify", lambda self, event, approval: _noop())
    audited = []

    async def _audit(op, **kw):
        audited.append((op, kw))

    monkeypatch.setattr(oauth_bundle_strip_action, "audit_log", _audit)
    oauth_bundle_strip_action.register_strip_action()
    session = ApprovalClaimSession()

    resp = await proposer.propose_oauth_bundle_strip(
        OAuthBundleStripRequest(backup_reference="snap-1"), current_user={"username": "agent"}, session=session
    )
    assert resp.status == "pending" and svc.writes == []  # a proposal executes nothing

    await ApprovalGateService(session).approve(
        session.approval.id, decided_by="human", author_type="human", comment=None
    )
    assert svc.writes == ["s-legacy"]
    comments = [o for o in session.added if isinstance(o, ApprovalComment)]
    assert any("1 stripped" in c.body for c in comments) and _SECRET not in " ".join(c.body for c in comments)
    assert audited and audited[-1][0] == "oauth_bundle.strip_app_credentials"
    assert _SECRET not in json.dumps(audited[-1][1], default=str)


async def test_execution_refuses_without_a_backup_reference(configured):
    approval = Approval(context={"action": oauth_bundle_strip_action.ACTION}, id=uuid.uuid4())
    with pytest.raises(ValueError, match="backup_reference"):
        await oauth_bundle_strip_action.execute_oauth_bundle_strip(approval, ApprovalClaimSession())


def test_action_is_registered_with_its_proposer():
    oauth_bundle_strip_action.register_strip_action()
    assert approval_execution.registered_action_proposers()[oauth_bundle_strip_action.ACTION] == (
        "api.admin_oauth_bundle_strip"
    )


async def test_unverifiable_backup_refuses_execution_records_why_and_touches_nothing(configured, monkeypatch):
    """Fail closed (#18281): a non-empty reference is not a backup."""
    svc = _svc()
    monkeypatch.setattr("services.secrets_service.get_secrets_service", lambda: svc)
    audited, session = [], ApprovalClaimSession()

    async def _audit(op, **kw):
        audited.append(kw)

    async def _unverified(reference):
        return False

    monkeypatch.setattr(oauth_bundle_strip_action, "audit_log", _audit)
    monkeypatch.setattr(oauth_bundle_strip_action, "verify_backup", _unverified)
    approval = Approval(context={"backup_reference": "snap-looks-real"}, id=uuid.uuid4(), decided_by_user="human")
    with pytest.raises(ValueError, match="18281"):
        await oauth_bundle_strip_action.execute_oauth_bundle_strip(approval, session)
    assert svc.writes == [] and json.loads(svc.rows["s-legacy"])["client_secret"] == _SECRET
    assert "no verifiable secrets-store backup (#18281)" in session.added[0].body
    assert audited[0]["result"] == "refused"


async def test_the_same_request_runs_once_the_seam_verifies(configured, backup_verified, monkeypatch):
    svc = _svc()
    monkeypatch.setattr("services.secrets_service.get_secrets_service", lambda: svc)

    async def _audit(op, **kw):
        return None

    monkeypatch.setattr(oauth_bundle_strip_action, "audit_log", _audit)
    approval = Approval(context={"backup_reference": "snap-looks-real"}, id=uuid.uuid4(), decided_by_user="human")
    await oauth_bundle_strip_action.execute_oauth_bundle_strip(approval, ApprovalClaimSession())
    assert svc.writes == ["s-legacy"]


async def test_an_unverifiable_reference_refuses_with_no_flag_to_skip(monkeypatch):
    """The real verifier, with no SLM reachable and no internal key, fails closed: the strip is refused."""
    monkeypatch.delenv("AUTOBOT_INTERNAL_API_KEY", raising=False)
    assert await oauth_bundle_strip_action.verify_backup("anything") is False
