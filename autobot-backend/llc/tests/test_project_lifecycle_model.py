# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Model contract for the project archive→dispose lifecycle (#11129 P2)."""
from llc.models.enums import ApprovalType
from llc.models.sprint import LLCProject


def test_project_has_lifecycle_columns():
    cols = LLCProject.__table__.columns
    assert "lifecycle_state" in cols
    assert "archived_at" in cols
    assert "disposal_scheduled_at" in cols
    assert "disposal_approval_id" in cols
    assert cols["lifecycle_state"].default.arg == "active"
    # server_default (DDL-level) protects existing rows during the migration.
    assert cols["lifecycle_state"].server_default is not None
    assert "active" in str(cols["lifecycle_state"].server_default.arg)


def test_approval_type_has_project_disposal():
    assert ApprovalType.PROJECT_DISPOSAL.value == "project_disposal"
