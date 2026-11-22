# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Duplicate secrets are resolved by verification, through a proposal (#17850, #17038). No database needed."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from autobot_shared.secrets_vault import VaultRef
from models.approval import ApprovalType
from models.secret import Secret
from services import secret_duplicate_cleanup_action as action
from services import secret_duplicate_proposals as proposals
from services import secret_duplicates as dup
from services.approval_execution import set_verified_decider
from services.envelope_secrets_service import (
    AmbiguousSecretError,
    EnvelopeSecretsService,
    SecretAccessError,
    SecretConflictError,
)
from services.secrets_maintenance import MaintenanceActor, MaintenanceAuditError
from testkit.fake_async_session import FakeAsyncSession

_V = dup.Verdict
_VAULT = "system"
_NAME = "OPENAI_API_KEY"
_A, _B, _C = (uuid.UUID(int=n) for n in (1, 2, 3))


_ACTOR = MaintenanceActor(uuid.UUID(int=99), "ref-1")


def _result(verdicts: dict, name: str = _NAME) -> dup.GroupVerification:
    return dup.GroupVerification(dup.SecretDuplicateGroup(_VAULT, name, tuple(verdicts)), verdicts)


def test_exactly_one_verified_copy_is_the_survivor_whatever_the_order():
    for order in ([_A, _B, _C], [_C, _B, _A]):
        verdicts = {i: (_V.VERIFIED if i == _B else _V.NOT_VERIFIED) for i in order}
        assert _result(verdicts).survivor_id == _B


@pytest.mark.parametrize(
    "verdicts, reason",
    [
        ({_A: _V.NOT_VERIFIED, _B: _V.NOT_VERIFIED}, proposals.REASON_NONE),
        ({_A: _V.VERIFIED, _B: _V.VERIFIED}, proposals.REASON_SEVERAL),
        ({_A: _V.NO_VERIFIER, _B: _V.NO_VERIFIER}, proposals.REASON_NO_VERIFIER),
    ],
)
def test_no_single_verified_copy_means_no_survivor_and_no_removal(verdicts, reason):
    context = proposals.proposal_context(_result(verdicts))
    assert context["survivor_id"] is None and context["removal_ids"] == []
    assert context["reason"] == reason


def test_the_proposal_carries_ids_only():
    context = proposals.proposal_context(_result({_A: _V.NOT_VERIFIED, _B: _V.VERIFIED}))
    assert context["survivor_id"] == str(_B) and context["removal_ids"] == [str(_A)]
    assert context["action"] == action.ACTION
    assert _NAME not in repr(context) and _VAULT not in repr(context)


def test_only_known_provider_keys_have_a_verifier():
    assert dup.has_verifier("ANTHROPIC_API_KEY") and not dup.has_verifier("SLACK_BOT_TOKEN")


@pytest.mark.asyncio
async def test_a_type_without_a_verifier_is_never_probed_or_read():
    coordinator = MagicMock(maintenance_read=AsyncMock())
    group = dup.SecretDuplicateGroup(_VAULT, "SLACK_BOT_TOKEN", (_A, _B))
    assert await dup.verify_copy(MagicMock(), coordinator, _ACTOR, group, _A) is _V.NO_VERIFIER
    coordinator.maintenance_read.assert_not_called()


@pytest.mark.asyncio
async def test_a_copy_is_probed_with_its_own_value_and_only_healthy_verifies(monkeypatch):
    from services.provider_health.base import ProviderHealthStatus

    seen = []

    class _Checker:
        async def check_health(self):
            seen.append(self.api_key)
            ok = self.api_key == "good"  # pragma: allowlist secret
            return MagicMock(status=ProviderHealthStatus.HEALTHY if ok else ProviderHealthStatus.UNAVAILABLE)

    monkeypatch.setattr(dup, "_probe_classes", lambda: {_NAME: _Checker})
    values = {_A: b"bad", _B: b"good"}
    coordinator = MagicMock(maintenance_read=AsyncMock(side_effect=lambda s, actor, secret_id: values[secret_id]))
    group = dup.SecretDuplicateGroup(_VAULT, _NAME, (_A, _B))
    out = await dup.verify_group(MagicMock(), group, _ACTOR, coordinator)
    assert out.verdicts == {_A: _V.NOT_VERIFIED, _B: _V.VERIFIED} and out.survivor_id == _B
    assert sorted(seen) == ["bad", "good"]


@pytest.mark.asyncio
async def test_an_unreadable_copy_did_not_verify_and_its_value_is_not_logged(monkeypatch, caplog):
    monkeypatch.setattr(dup, "_probe_classes", lambda: {_NAME: object})
    coordinator = MagicMock(maintenance_read=AsyncMock(side_effect=ValueError("sk-secret-value")))
    with caplog.at_level("WARNING"):
        group = dup.SecretDuplicateGroup(_VAULT, _NAME, (_A,))
        verdict = await dup.verify_copy(MagicMock(), coordinator, _ACTOR, group, _A)
    assert verdict is _V.NOT_VERIFIED
    assert "sk-secret-value" not in caplog.text and _NAME not in caplog.text


@pytest.mark.asyncio
async def test_a_proposal_is_filed_once_per_group(monkeypatch):
    created = []

    class _Gate:
        def __init__(self, db):
            pass

        async def create_approval(self, **kw):
            created.append(kw)
            return MagicMock(id=uuid.uuid4())

    monkeypatch.setattr(proposals, "ApprovalGateService", _Gate)
    monkeypatch.setattr(proposals, "_already_proposed", AsyncMock(side_effect=[False, True]))
    result = _result({_A: _V.NOT_VERIFIED, _B: _V.VERIFIED})
    first = await proposals.propose_group(MagicMock(), result, "admin")
    again = await proposals.propose_group(MagicMock(), result, "admin")
    assert first.approval_id and again.skipped and len(created) == 1
    assert created[0]["approval_type"] == ApprovalType.DESTRUCTIVE_ACTION.value
    assert _NAME not in repr(created)


def _approval(**context):
    versions = {str(i): 1 for i in (_A, _B, _C)}
    approval = MagicMock(
        id=uuid.uuid4(), context={"action": action.ACTION, "versions": versions, **context}, decided_by_user="admin"
    )
    set_verified_decider(approval, _ACTOR.admin_id)
    return approval


@pytest.mark.asyncio
async def test_approving_a_human_choice_proposal_removes_nothing(monkeypatch):
    removed = AsyncMock()
    monkeypatch.setattr(action, "_remove_one", removed)
    await action.execute_secret_duplicate_cleanup(_approval(survivor_id=None, removal_ids=[]), AsyncMock())
    removed.assert_not_called()


@pytest.mark.asyncio
async def test_a_group_that_changed_since_review_removes_nothing(monkeypatch):
    removed = AsyncMock()
    monkeypatch.setattr(action, "_remove_one", removed)
    monkeypatch.setattr(
        action, "_group_rows", AsyncMock(return_value=[SimpleNamespace(id=_A, owner_vault="a", name="n", version=1)])
    )
    with pytest.raises(ValueError):
        await action.execute_secret_duplicate_cleanup(
            _approval(survivor_id=str(_A), removal_ids=[str(_B)]), AsyncMock()
        )
    removed.assert_not_called()


@pytest.mark.asyncio
async def test_a_survivor_that_stopped_working_removes_nothing(monkeypatch):
    removed = AsyncMock()
    rows = [
        SimpleNamespace(id=_A, owner_vault="v", name="n", version=1),
        SimpleNamespace(id=_B, owner_vault="v", name="n", version=1),
    ]
    monkeypatch.setattr(action, "_remove_one", removed)
    monkeypatch.setattr(action, "_group_rows", AsyncMock(return_value=rows))
    monkeypatch.setattr(action, "_survivor_still_works", AsyncMock(return_value=False))
    with pytest.raises(ValueError):
        await action.execute_secret_duplicate_cleanup(
            _approval(survivor_id=str(_A), removal_ids=[str(_B)]), AsyncMock()
        )
    removed.assert_not_called()


@pytest.mark.asyncio
async def test_only_the_named_removals_are_deleted(monkeypatch):
    removed = AsyncMock(return_value="removed")
    rows = [SimpleNamespace(id=i, owner_vault="v", name="n", version=1) for i in (_A, _B, _C)]
    monkeypatch.setattr(action, "_remove_one", removed)
    monkeypatch.setattr(action, "_group_rows", AsyncMock(return_value=rows))
    monkeypatch.setattr(action, "_survivor_still_works", AsyncMock(return_value=True))
    await action.execute_secret_duplicate_cleanup(
        _approval(survivor_id=str(_A), removal_ids=[str(_B), str(_C)]), AsyncMock()
    )
    assert [c.args[2] for c in removed.call_args_list] == [_B, _C]


@pytest.mark.asyncio
async def test_no_delete_runs_when_the_audit_entry_cannot_be_written(monkeypatch):
    monkeypatch.setattr(action, "_audit", AsyncMock(return_value=False))
    guarded = AsyncMock()
    monkeypatch.setattr(action, "_guarded_remove", guarded)
    assert "kept" in await action._remove_one(_approval(), AsyncMock(), _B, str(_A))
    guarded.assert_not_called()


def _rows(*ids):
    scalars = MagicMock(__iter__=lambda self: iter([MagicMock(id=i) for i in ids]))
    return MagicMock(scalars=lambda: scalars)


@pytest.mark.asyncio
async def test_lookup_by_name_refuses_when_ambiguous_and_names_ids_only():
    session = MagicMock(execute=AsyncMock(return_value=_rows(_B, _A)))
    with pytest.raises(AmbiguousSecretError) as raised:
        await EnvelopeSecretsService.find_by_name(session, owner_vault=_VAULT, name=_NAME)
    assert raised.value.secret_ids == [_A, _B] and _NAME not in str(raised.value)


@pytest.mark.asyncio
async def test_lookup_by_name_returns_the_single_row_or_none():
    one = MagicMock(execute=AsyncMock(return_value=_rows(_A)))
    assert (await EnvelopeSecretsService.find_by_name(one, owner_vault=_VAULT, name=_NAME)).id == _A
    none = MagicMock(execute=AsyncMock(return_value=_rows()))
    assert await EnvelopeSecretsService.find_by_name(none, owner_vault=_VAULT, name=_NAME) is None


def test_an_ambiguous_secret_is_a_fixed_409_never_a_pick():
    from api.secrets_delete_outcome import error_for

    refusal = error_for(AmbiguousSecretError(_VAULT, [_A, _B]))
    assert refusal.status_code == 409 and str(_A) not in str(refusal.detail)


# --- review round: active-only lookup, value-aware create, re-raise, per-call cap -------------------------------


def _held(value: bytes, active: bool = True, expired: bool = False):
    row = SimpleNamespace(id=_A, is_active=active, is_expired=expired, already_existed=False)
    return row, AsyncMock(return_value=value)


@pytest.mark.asyncio
async def test_a_repeat_with_the_same_value_returns_the_existing_row_and_says_so():
    row, read = _held(b"same")
    service = EnvelopeSecretsService(root_key=bytes(32))
    service.read = read
    got = await service._settle_existing(MagicMock(), row, VaultRef.parse("system"), b"same")
    assert got is row and row.already_existed is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "held, active, reason", [(b"zq-held-9", True, "value_differs"), (b"zq-new-7", False, "inactive")]
)
async def test_a_differing_or_deactivated_name_is_refused_never_reused(held, active, reason):
    row, read = _held(held, active)
    service = EnvelopeSecretsService(root_key=bytes(32))
    service.read = read
    with pytest.raises(SecretConflictError) as raised:
        await service._settle_existing(MagicMock(), row, VaultRef.parse("system"), b"zq-new-7")
    assert raised.value.reason == reason and "zq-" not in str(raised.value)
    assert not row.already_existed


@pytest.mark.asyncio
async def test_an_identical_empty_value_reuses_the_row():
    row, read = _held(b"")
    service = EnvelopeSecretsService(root_key=bytes(32))
    service.read = read
    got = await service._settle_existing(MagicMock(), row, VaultRef.parse("system"), b"")
    assert got is row and row.already_existed is True


@pytest.mark.asyncio
async def test_an_expired_row_is_refused_not_reused():
    row, read = _held(b"same", expired=True)
    service = EnvelopeSecretsService(root_key=bytes(32))
    service.read = read
    with pytest.raises(SecretConflictError) as raised:
        await service._settle_existing(MagicMock(), row, VaultRef.parse("system"), b"same")
    assert raised.value.reason == "inactive" and not row.already_existed


@pytest.mark.asyncio
async def test_a_copy_is_probed_with_its_exact_stored_value_unstripped(monkeypatch):
    from services.provider_health.base import ProviderHealthStatus

    seen = []

    class _Checker:
        async def check_health(self):
            seen.append(self.api_key)
            return MagicMock(status=ProviderHealthStatus.UNAVAILABLE)

    monkeypatch.setattr(dup, "_probe_classes", lambda: {_NAME: _Checker})
    coordinator = MagicMock(maintenance_read=AsyncMock(return_value=b"key-1\n"))
    group = dup.SecretDuplicateGroup(_VAULT, _NAME, (_A,))
    await dup.verify_copy(MagicMock(), coordinator, _ACTOR, group, _A)
    assert seen == ["key-1\n"]


@pytest.mark.asyncio
async def test_an_unreadable_existing_copy_is_not_treated_as_the_same_value():
    row, read = _held(b"")
    service = EnvelopeSecretsService(root_key=bytes(32))
    service.read = AsyncMock(side_effect=ValueError("boom"))
    with pytest.raises(SecretConflictError):
        await service._settle_existing(MagicMock(), row, VaultRef.parse("system"), b"x")


@pytest.mark.asyncio
@pytest.mark.parametrize("active, expected", [(True, _A), (False, None)])
async def test_the_provider_key_lookup_never_returns_a_deactivated_row(monkeypatch, active, expected):
    from services import provider_key_vault

    row = Secret(id=_A, is_active=active)
    monkeypatch.setattr(EnvelopeSecretsService, "find_by_name", staticmethod(AsyncMock(return_value=row)))
    assert await provider_key_vault._find_system_secret_id(MagicMock(), _NAME) == expected


@pytest.mark.asyncio
async def test_the_provider_key_lookup_judges_ambiguity_before_activity():
    """One active + one deactivated copy is still an unresolved group: refuse, never pick the active one."""
    from services import provider_key_vault

    rows = [Secret(id=_A, is_active=True), Secret(id=_B, is_active=False)]
    scalars = MagicMock(__iter__=lambda self: iter(rows))
    session = MagicMock(execute=AsyncMock(return_value=MagicMock(scalars=lambda: scalars)))
    with pytest.raises(AmbiguousSecretError):
        await provider_key_vault._find_system_secret_id(session, _NAME)


def _two_groups(monkeypatch, standing):
    groups = [dup.SecretDuplicateGroup(_VAULT, _NAME, (uuid.UUID(int=n), uuid.UUID(int=n + 10))) for n in (1, 2, 3)]
    monkeypatch.setattr(proposals, "find_duplicate_groups", AsyncMock(return_value=groups))
    monkeypatch.setattr(proposals, "_already_proposed", AsyncMock(side_effect=standing))
    monkeypatch.setattr(
        proposals,
        "verify_group",
        AsyncMock(side_effect=lambda db, g, actor: _result({i: _V.NOT_VERIFIED for i in g.secret_ids})),
    )
    gate = MagicMock(create_approval=AsyncMock(return_value=MagicMock(id=uuid.uuid4())))
    monkeypatch.setattr(proposals, "ApprovalGateService", lambda db: gate)
    return gate


@pytest.mark.asyncio
async def test_the_request_probes_at_most_the_cap_and_reports_the_rest(monkeypatch):
    gate = _two_groups(monkeypatch, lambda *a: False)
    batch = await proposals.propose_duplicate_resolutions(MagicMock(), "admin", _ACTOR, limit=2)
    assert len(batch.results) == 2 and batch.remaining == 1 and gate.create_approval.await_count == 2


@pytest.mark.asyncio
async def test_groups_with_a_standing_proposal_do_not_use_the_cap(monkeypatch):
    gate = _two_groups(monkeypatch, [True, True, False, False])
    batch = await proposals.propose_duplicate_resolutions(MagicMock(), "admin", _ACTOR, limit=1)
    assert batch.remaining == 0 and [r.skipped for r in batch.results] == [True, True, False]
    assert gate.create_approval.await_count == 1


@pytest.mark.asyncio
async def test_a_rejected_proposal_blocks_until_an_admin_re_raises():
    db = FakeAsyncSession(default_result=[])
    await proposals._already_proposed(db, "d")
    await proposals._already_proposed(db, "d", re_raise=True)
    seen = [str(q.compile(compile_kwargs={"literal_binds": True})) for q in db.statements]
    assert "rejected" in seen[0] and "rejected" not in seen[1] and "pending" in seen[1]


# --- review round: rotated copies, survivor hold, expired approval ----------------------------------------------


@pytest.mark.asyncio
async def test_a_copy_rotated_since_it_was_probed_removes_nothing(monkeypatch):
    removed = AsyncMock()
    rows = [
        SimpleNamespace(id=_A, owner_vault="v", name="n", version=1),
        SimpleNamespace(id=_B, owner_vault="v", name="n", version=2),
    ]
    monkeypatch.setattr(action, "_remove_one", removed)
    monkeypatch.setattr(action, "_group_rows", AsyncMock(return_value=rows))
    monkeypatch.setattr(action, "_survivor_still_works", AsyncMock(return_value=True))
    with pytest.raises(ValueError, match="changed since"):
        await action.execute_secret_duplicate_cleanup(
            _approval(survivor_id=str(_A), removal_ids=[str(_B)]), AsyncMock()
        )
    removed.assert_not_called()


@pytest.mark.asyncio
async def test_a_proposal_without_recorded_versions_is_refused(monkeypatch):
    rows = [
        SimpleNamespace(id=_A, owner_vault="v", name="n", version=1),
        SimpleNamespace(id=_B, owner_vault="v", name="n", version=1),
    ]
    monkeypatch.setattr(action, "_group_rows", AsyncMock(return_value=rows))
    approval = _approval(survivor_id=str(_A), removal_ids=[str(_B)])
    approval.context["versions"] = {}
    with pytest.raises(ValueError):
        await action.execute_secret_duplicate_cleanup(approval, AsyncMock())


def _review():
    return action._Review("ap", "admin", _A, 1, [_B], {str(_A): 1, str(_B): 1}, _ACTOR)


@pytest.mark.asyncio
@pytest.mark.parametrize("found", [None, SimpleNamespace(version=2)])
async def test_a_removal_is_refused_when_the_survivor_is_gone_or_rotated(found):
    session = MagicMock(execute=AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: found)))
    with pytest.raises(ValueError, match="surviving copy"):
        await action._hold_survivor(session, _review())


@pytest.mark.asyncio
async def test_a_refused_removal_refreshes_the_approval_and_still_audits_from_plain_values(monkeypatch):
    audits = []
    monkeypatch.setattr(
        action, "_audit", AsyncMock(side_effect=lambda review, result, sid, **kw: audits.append(result) or True)
    )
    monkeypatch.setattr(action, "_guarded_remove", AsyncMock(side_effect=RuntimeError("409")))
    session, approval = AsyncMock(), _approval()
    assert "kept" in await action._remove_one(approval, session, _B, _review())
    session.refresh.assert_awaited_once_with(approval)
    assert audits == ["attempted", "failed"]


def test_the_proposal_records_each_copys_version():
    group = dup.SecretDuplicateGroup(_VAULT, _NAME, (_A, _B), (3, 4))
    context = proposals.proposal_context(dup.GroupVerification(group, {_A: _V.NOT_VERIFIED, _B: _V.VERIFIED}))
    assert context["versions"] == {str(_A): 3, str(_B): 4}


def test_a_canonical_llm_provider_name_is_manual_only():
    assert not dup.has_verifier("llm:provider:openai:api_key")


@pytest.mark.asyncio
@pytest.mark.parametrize("found", [None, SimpleNamespace(version=9)])
async def test_a_removal_copy_rotated_or_gone_before_its_turn_is_kept(found):
    session = MagicMock(execute=AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: found)))
    with pytest.raises(ValueError, match="kept"):
        await action._hold_removal(session, _B, _review())


@pytest.mark.asyncio
async def test_an_unrotated_removal_copy_passes_its_hold():
    session = MagicMock(
        execute=AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: SimpleNamespace(version=1)))
    )
    await action._hold_removal(session, _B, _review())
    assert "FOR UPDATE" in str(session.execute.call_args.args[0])


@pytest.mark.asyncio
@pytest.mark.parametrize("refusal", [SecretAccessError("not an administrator"), MaintenanceAuditError("no audit")])
async def test_a_refused_maintenance_read_is_raised_never_read_as_a_copy_that_does_not_work(monkeypatch, refusal):
    monkeypatch.setattr(dup, "_probe_classes", lambda: {_NAME: object})
    coordinator = MagicMock(maintenance_read=AsyncMock(side_effect=refusal))
    with pytest.raises(type(refusal)):
        await dup.verify_copy(MagicMock(), coordinator, _ACTOR, dup.SecretDuplicateGroup(_VAULT, _NAME, (_A,)), _A)


@pytest.mark.asyncio
async def test_an_approval_without_a_verified_administrator_removes_nothing(monkeypatch):
    removed = AsyncMock()
    rows = [SimpleNamespace(id=i, owner_vault="v", name="n", version=1) for i in (_A, _B)]
    monkeypatch.setattr(action, "_remove_one", removed)
    monkeypatch.setattr(action, "_group_rows", AsyncMock(return_value=rows))
    approval = _approval(survivor_id=str(_A), removal_ids=[str(_B)])
    set_verified_decider(approval, None)
    with pytest.raises(ValueError, match="verified administrator"):
        await action.execute_secret_duplicate_cleanup(approval, AsyncMock())
    removed.assert_not_called()


@pytest.mark.asyncio
async def test_the_removal_goes_through_the_coordinators_maintenance_delete(monkeypatch):
    calls = []

    class _Coordinator:
        async def maintenance_delete(self, session, *, actor, secret_id):
            calls.append((actor, secret_id))

    async def _guarded(session, secret_id, *, dependents, delete, confirmed_digest=None):
        await delete()

    monkeypatch.setattr(action, "SecretsCoordinator", _Coordinator)
    monkeypatch.setattr(action, "_hold_removal", AsyncMock())
    monkeypatch.setattr(action, "_hold_survivor", AsyncMock())
    monkeypatch.setattr("api.secrets_guarded_delete.guarded_delete", _guarded)
    await action._guarded_remove(AsyncMock(), _B, _review())
    assert calls == [(_ACTOR, _B)]
