# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one approval record: column validation, creation and resume dispatch (#13421 S1)."""

import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest

from autobot_shared.time_utils import now_utc
from models.approval import Approval, ApprovalSource
from services import approval_execution
from services.approval_gate_service import ApprovalGateService
from services.approval_record_fields import payload_hash_of, record_fields

pytestmark = pytest.mark.asyncio


def _fields(**over):
    base = dict(source=None, risk_tier=None, expires_at=None, payload_hash=None, resume_ref=None, context=None)
    return record_fields(**{**base, **over})


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setattr(approval_execution, "_RESUME_HANDLERS", {})
    monkeypatch.setattr(approval_execution, "_REGISTRY", {})
    monkeypatch.setattr(approval_execution, "_PROPOSERS", {})

    async def _audit(*a, **k):
        return True

    monkeypatch.setattr(approval_execution, "audit_log", _audit)

    async def _noop(self, event, approval):
        return None

    monkeypatch.setattr(ApprovalGateService, "_notify", _noop)


class _Session:
    def __init__(self, existing=None):
        self.added, self.existing, self.commits = [], existing, 0

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        self.added.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        return None

    async def execute(self, stmt):
        return SimpleNamespace(scalar_one_or_none=lambda: self.existing)


class TestRecordFields:
    def test_an_unsourced_approval_keeps_every_new_column_null(self):
        assert set(_fields().values()) == {None}

    def test_risk_tier_is_normalised_from_any_producer_vocabulary(self):
        assert _fields(source="agent_tool", risk_tier="HIGH", owner_user="alice")["risk_tier"] == "high"

    def test_a_sourced_approval_must_be_graded(self):
        with pytest.raises(ValueError, match="risk_tier"):
            _fields(source="agent_tool", owner_user="alice")

    def test_an_unknown_source_is_refused(self):
        with pytest.raises(ValueError):
            _fields(source="made_up", risk_tier="low", owner_user="alice")

    def test_a_sourced_approval_must_name_its_owner(self):
        with pytest.raises(ValueError, match="owner_user"):
            _fields(source="agent_tool", risk_tier="low")

    def test_owner_user_is_stripped_and_a_blank_owner_counts_as_missing(self):
        assert _fields(source="agent_tool", risk_tier="low", owner_user="  alice ")["owner_user"] == "alice"
        with pytest.raises(ValueError, match="owner_user"):
            _fields(source="agent_tool", risk_tier="low", owner_user="   ")

    def test_owner_user_without_a_source_is_refused(self):
        with pytest.raises(ValueError, match="require a source"):
            _fields(owner_user="alice")

    def test_risk_tier_or_resume_ref_without_a_source_is_refused(self):
        with pytest.raises(ValueError, match="require a source"):
            _fields(risk_tier="low")
        with pytest.raises(ValueError, match="require a source"):
            _fields(resume_ref="x")

    def test_resume_ref_needs_a_registered_resume_handler(self):
        with pytest.raises(ValueError, match="no registered resume handler"):
            _fields(source="agent_tool", risk_tier="low", resume_ref="call-1", owner_user="alice")

    def test_resume_ref_is_accepted_once_the_source_has_a_handler(self):
        approval_execution.register_resume_handler("agent_tool", lambda a, s: None)
        assert (
            _fields(source="agent_tool", risk_tier="low", resume_ref="call-1", owner_user="alice")["resume_ref"]
            == "call-1"
        )

    def test_expiry_must_be_aware_and_in_the_future(self):
        with pytest.raises(ValueError, match="timezone-aware"):
            _fields(expires_at=now_utc().replace(tzinfo=None))
        with pytest.raises(ValueError, match="future"):
            _fields(expires_at=now_utc() - timedelta(seconds=1))
        later = now_utc() + timedelta(hours=1)
        assert _fields(expires_at=later)["expires_at"] == later

    def test_payload_hash_defaults_to_the_canonical_hash_of_the_context(self):
        a = _fields(source="workflow_plan", risk_tier="low", owner_user="alice", context={"b": 1, "a": 2})
        b = _fields(source="workflow_plan", risk_tier="low", owner_user="alice", context={"a": 2, "b": 1})
        assert a["payload_hash"] == b["payload_hash"] == payload_hash_of({"a": 2, "b": 1})
        assert len(a["payload_hash"]) == 64

    def test_a_supplied_payload_hash_wins(self):
        assert (
            _fields(source="workflow_plan", risk_tier="low", owner_user="alice", payload_hash="abc")["payload_hash"]
            == "abc"
        )


class TestCreateApproval:
    async def test_create_persists_the_record_columns(self):
        session = _Session()
        svc = ApprovalGateService(session)
        approval = await svc.create_approval(
            title="t",
            approval_type="workflow_gate",
            context={"k": 1},
            source="plugin_capability",
            risk_tier="medium",
            owner_user="alice",
        )
        assert (approval.source, approval.risk_tier) == (ApprovalSource.PLUGIN_CAPABILITY.value, "medium")
        assert approval.payload_hash == payload_hash_of({"k": 1})

    async def test_create_without_the_new_fields_is_unchanged(self):
        approval = await ApprovalGateService(_Session()).create_approval(title="t", approval_type="workflow_gate")
        assert (approval.source, approval.risk_tier, approval.payload_hash, approval.resume_ref) == (None,) * 4

    async def test_create_refuses_a_resume_ref_nothing_can_resume(self):
        with pytest.raises(ValueError):
            await ApprovalGateService(_Session()).create_approval(
                title="t",
                approval_type="workflow_gate",
                source="agent_tool",
                risk_tier="low",
                resume_ref="c1",
                owner_user="alice",
            )


def test_the_model_declares_the_five_nullable_columns():
    for name in ("source", "risk_tier", "expires_at", "payload_hash", "resume_ref", "owner_user"):
        assert Approval.__table__.c[name].nullable is True
