# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Orchestrate the findings → proposal → work-item pipeline (#11271).

Public async API:
    scan(project, session) -> dict{gathered, verified_real, queued}
    promote(proposal, session, actor_user_id) -> LLCWorkItem | dict
    dismiss(proposal, session, reason) -> None

Helpers used in tests (patchable wrappers over lazy-imported services):
    _work_item_service_create(session, company_id, type, title, **kwargs)
    _approval_service_request(session, *, company_id, gate_type, payload, requested_by)
    _get_clone_path(project) -> str
    _requires_cross_vendor_review(session, company_id, item_type) -> bool  (#12618)
"""

import logging
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import ApprovalType, FindingProposalStatus, WorkItemPriority, WorkItemType
from ..models.finding_proposal import LLCFindingProposal
from .findings_gather import gather_findings
from .findings_policy import get_findings_policy
from .findings_verify import verify_finding

logger = logging.getLogger(__name__)

# Finding types that map to WorkItemType.BUG
_BUG_TYPES = frozenset({"bug", "race_condition", "security", "vulnerability", "null_dereference"})


class FindingsDisabledError(Exception):
    """Raised when scan/promote is called but the feature flag is OFF."""


class ProposalStateError(Exception):
    """Raised when a proposal is in the wrong state for the requested action."""


# ---------------------------------------------------------------------------
# Patchable thin wrappers (lazy-import heavy service classes)
# ---------------------------------------------------------------------------


async def _work_item_service_create(session: AsyncSession, company_id: str, type, title: str, **kwargs):
    """Thin wrapper around WorkItemService.create so tests can patch at module level."""
    from llc.services.work_item_service import WorkItemService  # noqa: PLC0415

    return await WorkItemService().create(session, company_id=company_id, type=type, title=title, **kwargs)


async def _approval_service_request(session: AsyncSession, *, company_id, gate_type, payload, requested_by):
    """Thin wrapper around ApprovalService.request_approval so tests can patch at module level."""
    from llc.services.approval import ApprovalService  # noqa: PLC0415

    return await ApprovalService().request_approval(
        session,
        company_id=company_id,
        gate_type=gate_type,
        payload=payload,
        requested_by=requested_by,
    )


async def _get_clone_path(project) -> str:
    """Resolve clone_path for *project* via the code source (lazy-import)."""
    from api.codebase_analytics.source_storage import get_source  # noqa: PLC0415

    source = await get_source(str(project.code_source_id))
    if source is None:
        raise ValueError(f"CodeSource {project.code_source_id!r} not found for project {project.id!r}")
    return getattr(source, "clone_path", "") or ""


async def _requires_cross_vendor_review(session: AsyncSession, company_id, item_type: WorkItemType) -> bool:
    """Thin wrapper around ReviewGatePolicyService so tests can patch at module level (#12618)."""
    from llc.services.review_gate import ReviewGatePolicyService  # noqa: PLC0415

    return await ReviewGatePolicyService().requires_cross_vendor_review(session, str(company_id), item_type)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _type_for(finding_type: str) -> WorkItemType:
    """Map analytics finding type to WorkItemType (BUG for defect-ish, TASK otherwise)."""
    return WorkItemType.BUG if (finding_type or "").lower() in _BUG_TYPES else WorkItemType.TASK


def _priority(severity: str) -> WorkItemPriority:
    """Map analytics severity to WorkItemPriority."""
    _map = {"high": WorkItemPriority.HIGH, "medium": WorkItemPriority.MEDIUM, "low": WorkItemPriority.LOW}
    return _map.get((severity or "").lower(), WorkItemPriority.MEDIUM)


def _title(proposal: LLCFindingProposal) -> str:
    """Build a concise work-item title from a finding proposal."""
    loc = f"{proposal.file_path}:{proposal.line_number}" if proposal.line_number else proposal.file_path
    return f"[{proposal.finding_type}] {proposal.description[:80]} ({loc})"


def _body(proposal: LLCFindingProposal) -> str:
    """Build a work-item description from a finding proposal."""
    loc = f"{proposal.file_path}:{proposal.line_number}" if proposal.line_number else proposal.file_path
    parts = [
        f"**Location:** `{loc}`",
        f"**Finding type:** {proposal.finding_type}  **Severity:** {proposal.severity}",
        "",
        f"**Description:** {proposal.description}",
    ]
    if proposal.suggestion:
        parts += ["", f"**Suggestion:** {proposal.suggestion}"]
    if proposal.verdict_rationale:
        parts += ["", f"**Verifier rationale:** {proposal.verdict_rationale}"]
    return "\n".join(parts)


def _finding_key(source_id: str, finding: dict) -> str:
    """Compute the dedup key for a finding dict."""
    return f"{source_id}:{finding.get('file_path', '')}:{finding.get('line_number', '')}:{finding.get('type', '')}"


async def _lookup_existing(project_id, finding_key: str, session: AsyncSession):
    """Return an existing LLCFindingProposal for (project_id, finding_key) or None."""
    stmt = sa.select(LLCFindingProposal).where(
        LLCFindingProposal.project_id == project_id,
        LLCFindingProposal.finding_key == finding_key,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _upsert_proposal(project, finding: dict, key: str, verdict, session: AsyncSession) -> None:
    """Insert or update a pending LLCFindingProposal with verdict fields."""
    existing = await _lookup_existing(project.id, key, session)
    if existing is not None:
        # Never regress a terminal proposal: a PROMOTED/DISMISSED row must not be
        # reset to PENDING by a re-scan (guards the race where the scan-level dedup
        # missed a concurrently-inserted terminal row).
        if existing.status != FindingProposalStatus.PENDING:
            return
        existing.verdict_is_real = verdict.is_real
        existing.verdict_confidence = float(verdict.confidence)
        existing.verdict_rationale = verdict.rationale
        existing.status = FindingProposalStatus.PENDING
    else:
        proposal = LLCFindingProposal(
            id=uuid.uuid4(),
            company_id=project.company_id,
            project_id=project.id,
            source_id=str(project.code_source_id),
            finding_key=key,
            finding_type=finding.get("type", ""),
            severity=finding.get("severity", ""),
            file_path=finding.get("file_path", ""),
            line_number=finding.get("line_number"),
            description=finding.get("description", ""),
            suggestion=finding.get("suggestion"),
            verdict_is_real=verdict.is_real,
            verdict_confidence=float(verdict.confidence),
            verdict_rationale=verdict.rationale,
            status=FindingProposalStatus.PENDING,
        )
        session.add(proposal)
    await session.flush()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def scan(project, session: AsyncSession) -> dict:
    """Gather + verify findings for *project* and upsert pending proposals.

    Returns:
        dict with keys: gathered, verified_real, queued.

    Raises:
        FindingsDisabledError: When the policy flag is off (feature-gated).
    """
    policy = await get_findings_policy()
    if not policy.enabled:
        raise FindingsDisabledError("findings feature is disabled (policy.enabled=False)")

    clone_path = await _get_clone_path(project)
    findings = await gather_findings(project, policy.min_severity, session)
    source_id = str(project.code_source_id)

    gathered = len(findings)
    verified_real = 0
    queued = 0

    batch_size = max(1, policy.verify_batch_size)
    for batch_start in range(0, len(findings), batch_size):
        batch = findings[batch_start : batch_start + batch_size]
        for finding in batch:
            key = _finding_key(source_id, finding)
            existing = await _lookup_existing(project.id, key, session)
            if existing is not None and existing.status in (
                FindingProposalStatus.PROMOTED,
                FindingProposalStatus.DISMISSED,
            ):
                logger.debug("scan: skip key=%s (status=%s)", key, existing.status)
                continue

            item_type = _type_for(finding.get("type", ""))
            cross_vendor = await _requires_cross_vendor_review(session, project.company_id, item_type)
            verdict = await verify_finding(finding, clone_path, cross_vendor=cross_vendor)
            if not verdict.is_real:
                logger.debug("scan: FP key=%s rationale=%s", key, verdict.rationale)
                continue

            verified_real += 1
            await _upsert_proposal(project, finding, key, verdict, session)
            queued += 1

    logger.info("scan: project=%s gathered=%d verified_real=%d queued=%d", project.id, gathered, verified_real, queued)
    return {"gathered": gathered, "verified_real": verified_real, "queued": queued}


async def promote(proposal: LLCFindingProposal, session: AsyncSession, actor_user_id: uuid.UUID):
    """Promote a pending finding proposal to a work item (or gate on approval).

    Returns:
        LLCWorkItem on immediate promote, or dict{result, approval_id} when gated.

    Raises:
        ProposalStateError: When proposal is not in PENDING status.
    """
    if proposal.status != FindingProposalStatus.PENDING:
        raise ProposalStateError(f"Cannot promote a proposal in status {proposal.status!r}")

    policy = await get_findings_policy()

    if policy.require_approval_to_promote:
        approval = await _approval_service_request(
            session,
            company_id=uuid.UUID(str(proposal.company_id)),
            gate_type=ApprovalType.FINDING_PROMOTION,
            payload={
                "proposal_id": str(proposal.id),
                "finding_key": proposal.finding_key,
                "requested_by_user_id": str(actor_user_id),
            },
            requested_by=uuid.UUID(str(actor_user_id)),
        )
        await session.flush()
        return {"result": "pending_approval", "approval_id": str(approval.id)}

    item = await _work_item_service_create(
        session,
        company_id=str(proposal.company_id),
        type=_type_for(proposal.finding_type),
        title=_title(proposal),
        description=_body(proposal),
        priority=_priority(proposal.severity),
        project_id=str(proposal.project_id),
        labels=["analytics-finding", f"severity:{proposal.severity}"],
    )
    proposal.status = FindingProposalStatus.PROMOTED
    proposal.work_item_id = item.id
    await session.flush()
    return item


async def dismiss(proposal: LLCFindingProposal, session: AsyncSession, reason: str) -> None:
    """Dismiss a pending finding proposal.

    Raises:
        ProposalStateError: When proposal is not in PENDING status.
    """
    if proposal.status != FindingProposalStatus.PENDING:
        raise ProposalStateError(f"Cannot dismiss a proposal in status {proposal.status!r}")

    proposal.status = FindingProposalStatus.DISMISSED
    proposal.dismiss_reason = reason
    await session.flush()
