# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for finding_proposal_service — scan / promote / dismiss (#11271)."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.models.enums import FindingProposalStatus
from llc.services.finding_proposal_service import (
    FindingsDisabledError,
    ProposalStateError,
    dismiss,
    promote,
    scan,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_project(code_source_id: str = "src-1") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        code_source_id=code_source_id,
    )


def _make_policy(enabled: bool = True, require_approval: bool = False, batch_size: int = 5):
    from llc.services.findings_policy import FindingsPolicy

    return FindingsPolicy(
        enabled=enabled,
        min_severity="medium",
        require_approval_to_promote=require_approval,
        run_on_index=False,
        verify_batch_size=batch_size,
    )


def _make_finding(severity: str = "high", ftype: str = "bug") -> dict:
    return {
        "type": ftype,
        "severity": severity,
        "file_path": "src/foo.py",
        "line_number": 42,
        "description": "Null pointer deref",
        "suggestion": "Check for None",
    }


def _async_none(*_, **__):
    """AsyncMock return that yields None (SQLAlchemy select dedup lookup)."""
    m = MagicMock()
    m.scalar_one_or_none = MagicMock(return_value=None)
    return m


def _make_session(existing_proposal=None):
    """Return an AsyncMock session with execute returning a row or None for dedup."""
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = existing_proposal
    session.execute = AsyncMock(return_value=result_mock)
    return session


# ---------------------------------------------------------------------------
# scan — disabled policy raises FindingsDisabledError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scan_raises_when_disabled():
    policy = _make_policy(enabled=False)
    project = _make_project()
    session = _make_session()

    with patch("llc.services.finding_proposal_service.get_findings_policy", AsyncMock(return_value=policy)):
        with pytest.raises(FindingsDisabledError):
            await scan(project, session)


# ---------------------------------------------------------------------------
# scan — only is_real findings queued; promoted key skipped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scan_queues_only_real_and_skips_promoted():
    """Verifies three behaviours in one scan call:
    1. A real finding with no existing proposal → queued.
    2. A false-positive finding → NOT queued.
    3. A finding whose key already has a PROMOTED proposal → skipped (dedup).
    """
    policy = _make_policy(enabled=True, batch_size=5)
    project = _make_project(code_source_id="src-42")

    # Three distinct findings (different file_path → distinct finding_keys)
    finding_real = {
        "type": "bug",
        "severity": "high",
        "file_path": "a.py",
        "line_number": 1,
        "description": "D1",
        "suggestion": None,
    }
    finding_fake = {
        "type": "style",
        "severity": "high",
        "file_path": "b.py",
        "line_number": 2,
        "description": "D2",
        "suggestion": None,
    }
    finding_promoted = {
        "type": "bug",
        "severity": "high",
        "file_path": "c.py",
        "line_number": 3,
        "description": "D3",
        "suggestion": None,
    }

    real_verdict = SimpleNamespace(is_real=True, confidence=0.95, rationale="Real bug")
    fake_verdict = SimpleNamespace(is_real=False, confidence=0.1, rationale="FP")

    promoted_proposal = MagicMock()
    promoted_proposal.status = FindingProposalStatus.PROMOTED

    source_id = "src-42"
    key_real = f"{source_id}:a.py:1:bug"
    key_fake = f"{source_id}:b.py:2:style"
    key_promoted = f"{source_id}:c.py:3:bug"
    existing_map = {key_real: None, key_fake: None, key_promoted: promoted_proposal}

    async def mock_lookup(project_id, fk, sess):
        return existing_map.get(fk)

    async def mock_upsert(proj, finding, key, verdict, sess):
        pass  # no-op so we control queued via the service logic

    clone_path = "/tmp/clone"

    async def mock_gather(proj, min_sev, sess):
        return [finding_real, finding_fake, finding_promoted]

    async def mock_verify(finding, cp):
        return fake_verdict if finding["file_path"] == "b.py" else real_verdict

    session = AsyncMock()

    with (
        patch("llc.services.finding_proposal_service.get_findings_policy", AsyncMock(return_value=policy)),
        patch("llc.services.finding_proposal_service.gather_findings", side_effect=mock_gather),
        patch("llc.services.finding_proposal_service.verify_finding", side_effect=mock_verify),
        patch("llc.services.finding_proposal_service._get_clone_path", return_value=clone_path),
        patch("llc.services.finding_proposal_service._lookup_existing", side_effect=mock_lookup),
        patch("llc.services.finding_proposal_service._upsert_proposal", side_effect=mock_upsert),
    ):
        result = await scan(project, session)

    assert result["gathered"] == 3
    # finding_fake is FP; finding_promoted is skipped before verify; only finding_real is verified+queued
    assert result["verified_real"] == 1
    assert result["queued"] == 1


# ---------------------------------------------------------------------------
# promote — immediate (no approval required)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_promote_immediate_creates_work_item():
    project = _make_project()
    policy = _make_policy(require_approval=False)

    proposal = MagicMock()
    proposal.status = FindingProposalStatus.PENDING
    proposal.project_id = project.id
    proposal.company_id = project.company_id
    proposal.source_id = "src-1"
    proposal.finding_type = "bug"
    proposal.severity = "high"
    proposal.file_path = "src/foo.py"
    proposal.line_number = 10
    proposal.description = "A real bug"
    proposal.suggestion = "Fix it"
    proposal.verdict_rationale = "Confirmed"

    fake_item = MagicMock()
    fake_item.id = uuid.uuid4()

    session = AsyncMock()
    actor_id = uuid.uuid4()

    async def fake_create(sess, company_id, type, title, **kwargs):
        return fake_item

    with (
        patch("llc.services.finding_proposal_service.get_findings_policy", AsyncMock(return_value=policy)),
        patch("llc.services.finding_proposal_service._work_item_service_create", side_effect=fake_create),
    ):
        result = await promote(proposal, session, actor_id)

    assert result is fake_item
    assert proposal.status == FindingProposalStatus.PROMOTED
    assert proposal.work_item_id == fake_item.id


# ---------------------------------------------------------------------------
# promote — approval required → pending_approval
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_promote_approval_required_returns_pending():
    project = _make_project()
    policy = _make_policy(require_approval=True)

    proposal = MagicMock()
    proposal.status = FindingProposalStatus.PENDING
    proposal.project_id = project.id
    proposal.company_id = project.company_id
    proposal.source_id = "src-1"
    proposal.finding_type = "bug"
    proposal.severity = "high"
    proposal.file_path = "src/foo.py"
    proposal.line_number = 10
    proposal.description = "A real bug"
    proposal.suggestion = "Fix it"
    proposal.verdict_rationale = "Confirmed"

    fake_approval = MagicMock()
    fake_approval.id = uuid.uuid4()

    session = AsyncMock()
    actor_id = uuid.uuid4()

    async def fake_request(sess, *, company_id, gate_type, payload, requested_by):
        return fake_approval

    with (
        patch("llc.services.finding_proposal_service.get_findings_policy", AsyncMock(return_value=policy)),
        patch("llc.services.finding_proposal_service._approval_service_request", side_effect=fake_request),
    ):
        result = await promote(proposal, session, actor_id)

    assert isinstance(result, dict)
    assert result["result"] == "pending_approval"
    assert result["approval_id"] == str(fake_approval.id)
    # Status must NOT be promoted yet
    assert proposal.status == FindingProposalStatus.PENDING


# ---------------------------------------------------------------------------
# dismiss — pending → dismissed + reason
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dismiss_sets_reason():
    proposal = MagicMock()
    proposal.status = FindingProposalStatus.PENDING

    session = AsyncMock()
    await dismiss(proposal, session, "Not reproducible")

    assert proposal.status == FindingProposalStatus.DISMISSED
    assert proposal.dismiss_reason == "Not reproducible"
    session.flush.assert_called_once()


# ---------------------------------------------------------------------------
# promote — wrong status raises ProposalStateError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_promote_from_non_pending_raises():
    proposal = MagicMock()
    proposal.status = FindingProposalStatus.DISMISSED

    session = AsyncMock()

    with pytest.raises(ProposalStateError):
        await promote(proposal, session, uuid.uuid4())
