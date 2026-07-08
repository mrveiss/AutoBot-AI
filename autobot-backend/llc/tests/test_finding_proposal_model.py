# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Model contract for LLCFindingProposal (#11271)."""

import sqlalchemy as sa

from llc.models.enums import ApprovalType, FindingProposalStatus
from llc.models.finding_proposal import LLCFindingProposal


def test_finding_proposal_has_all_columns():
    cols = LLCFindingProposal.__table__.columns
    expected = [
        "company_id",
        "project_id",
        "source_id",
        "finding_key",
        "finding_type",
        "severity",
        "file_path",
        "line_number",
        "description",
        "suggestion",
        "verdict_is_real",
        "verdict_confidence",
        "verdict_rationale",
        "status",
        "work_item_id",
        "dismiss_reason",
    ]
    for col in expected:
        assert col in cols, f"Missing column: {col}"


def test_status_server_default_is_pending():
    col = LLCFindingProposal.__table__.columns["status"]
    assert col.server_default is not None
    assert "pending" in str(col.server_default.arg)


def test_unique_constraint_project_finding_key():
    constraints = LLCFindingProposal.__table__.constraints
    unique_names = {c.name for c in constraints if isinstance(c, sa.UniqueConstraint)}
    assert "uq_finding_proposal_project_key" in unique_names


def test_finding_proposal_status_enum_values():
    assert FindingProposalStatus.PENDING.value == "pending"
    assert FindingProposalStatus.PROMOTED.value == "promoted"
    assert FindingProposalStatus.DISMISSED.value == "dismissed"


def test_approval_type_has_finding_promotion():
    assert ApprovalType.FINDING_PROMOTION.value == "finding_promotion"
