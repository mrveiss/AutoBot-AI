# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
from models.resource_grant import ResourceGrant


def test_resource_grant_table_and_columns():
    assert ResourceGrant.__tablename__ == "resource_grants"
    cols = set(ResourceGrant.__table__.columns.keys())
    assert cols == {
        "id", "resource_type", "resource_id", "grantee_type",
        "grantee_id", "permission", "created_by", "created_at",
        "updated_at",  # inherited from Base (DeclarativeBase adds this automatically)
    }


def test_resource_grant_unique_constraint_present():
    names = {c.name for c in ResourceGrant.__table__.constraints}
    assert "uq_resource_grants_target" in names
