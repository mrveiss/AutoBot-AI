# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Duplicate secrets are resolved by verification, through a proposal (#17850, #17038). No database needed."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.approval import ApprovalType
from services import secret_duplicate_cleanup_action as action
from services import secret_duplicate_proposals as proposals
from services import secret_duplicates as dup
from services.envelope_secrets_service import AmbiguousSecretError, EnvelopeSecretsService

_V = dup.Verdict
_VAULT = "system"
_NAME = "OPENAI_API_KEY"
_A, _B, _C = (uuid.UUID(int=n) for n in (1, 2, 3))


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
    service = MagicMock(read=AsyncMock())
    group = dup.SecretDuplicateGroup(_VAULT, "SLACK_BOT_TOKEN", (_A, _B))
    assert await dup.verify_copy(MagicMock(), service, group, _A) is _V.NO_VERIFIER
    service.read.assert_not_called()


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
    service = MagicMock(read=AsyncMock(side_effect=lambda s, secret_id, accessible_vaults: values[secret_id]))
    out = await dup.verify_group(MagicMock(), dup.SecretDuplicateGroup(_VAULT, _NAME, (_A, _B)), service)
    assert out.verdicts == {_A: _V.NOT_VERIFIED, _B: _V.VERIFIED} and out.survivor_id == _B
    assert sorted(seen) == ["bad", "good"]


@pytest.mark.asyncio
async def test_an_unreadable_copy_did_not_verify_and_its_value_is_not_logged(monkeypatch, caplog):
    monkeypatch.setattr(dup, "_probe_classes", lambda: {_NAME: object})
    service = MagicMock(read=AsyncMock(side_effect=ValueError("sk-secret-value")))
    with caplog.at_level("WARNING"):
        verdict = await dup.verify_copy(MagicMock(), service, dup.SecretDuplicateGroup(_VAULT, _NAME, (_A,)), _A)
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
    return MagicMock(id=uuid.uuid4(), context={"action": action.ACTION, **context}, decided_by_user="admin")


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
    monkeypatch.setattr(action, "_group_rows", AsyncMock(return_value=[SimpleNamespace(owner_vault="a", name="n")]))
    with pytest.raises(ValueError):
        await action.execute_secret_duplicate_cleanup(
            _approval(survivor_id=str(_A), removal_ids=[str(_B)]), AsyncMock()
        )
    removed.assert_not_called()


@pytest.mark.asyncio
async def test_a_survivor_that_stopped_working_removes_nothing(monkeypatch):
    removed = AsyncMock()
    rows = [SimpleNamespace(id=_A, owner_vault="v", name="n"), SimpleNamespace(id=_B, owner_vault="v", name="n")]
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
    rows = [SimpleNamespace(id=i, owner_vault="v", name="n") for i in (_A, _B, _C)]
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
