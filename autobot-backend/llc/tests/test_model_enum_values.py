# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression guard: every LLC ``sa.Enum`` column emits member VALUES, not NAMES (#9980).

Generic ``sa.Enum(PythonEnumClass)`` defaults to using member NAMES as the
Postgres enum labels. Because every LLC enum is ``UPPERCASE = "lowercase"``,
a ``create_all`` bootstrap built the types with UPPERCASE labels while the
Alembic migrations build them with lowercase values — and
``server_default=Status.X.value`` ('lowercase') is then invalid against the
create_all-built type (the #9980 abort on ``llc_approvals``).

``values_callable=pg_enum_values`` forces the model-built type and the ORM
bind values to match the migration-built ones. This test fails for any LLC
PyEnum column that regresses (drops ``values_callable``), and asserts the
emitted labels equal the lowercase ``.value`` list — no database required.
"""

import enum

import pytest
import sqlalchemy as sa

# Importing the package runs llc/models/__init__.py, which imports every model
# module and registers their tables. LLC ORM models inherit from the shared
# user_management Base (not the activity-only LLCBase), so their enum columns
# live on Base.metadata — the same metadata env.py feeds to autogenerate.
import llc.models  # noqa: F401  — side-effect: registers all LLC tables on Base.metadata
from llc.models.enums import pg_enum_values
from user_management.models.base import Base


def _llc_enum_columns():
    """Yield (table, column, sa.Enum) for every LLC column typed over a Python enum."""
    for table in Base.metadata.tables.values():
        if not table.name.startswith("llc_"):
            continue
        for column in table.columns:
            col_type = column.type
            if isinstance(col_type, sa.Enum) and getattr(col_type, "enum_class", None) is not None:
                if issubclass(col_type.enum_class, enum.Enum):
                    yield table.name, column.name, col_type


ENUM_COLUMNS = list(_llc_enum_columns())


def test_discovers_the_known_pyenum_columns() -> None:
    # Guards the discovery itself — if model refactoring drops these columns the
    # parity assertions below would silently pass on an empty set.
    found = {(t, c) for t, c, _ in ENUM_COLUMNS}
    expected = {
        ("llc_approvals", "type"),
        ("llc_approvals", "status"),
        ("llc_boards", "type"),
        ("llc_company_memberships", "role"),
        ("llc_review_gate_policies", "item_type"),
        ("llc_sprints", "status"),
        ("llc_work_item_relations", "relation_type"),
        ("llc_work_items", "type"),
        ("llc_work_items", "status"),
        ("llc_work_items", "priority"),
        ("llc_work_products", "type"),
    }
    missing = expected - found
    assert not missing, f"expected LLC PyEnum columns not discovered: {missing}"


@pytest.mark.parametrize("table,column,col_type", ENUM_COLUMNS, ids=lambda v: v if isinstance(v, str) else "")
def test_enum_column_emits_values_not_names(table, column, col_type) -> None:
    expected_values = [member.value for member in col_type.enum_class]
    assert list(col_type.enums) == expected_values, (
        f"{table}.{column} ({col_type.enum_class.__name__}) emits {list(col_type.enums)} — "
        f"expected member VALUES {expected_values}. Missing values_callable=pg_enum_values? (#9980)"
    )
    # Every LLC enum is lowercase-valued; an UPPERCASE label means NAMES leaked through.
    assert all(label == label.lower() for label in col_type.enums), (
        f"{table}.{column} has a non-lowercase enum label: {list(col_type.enums)}"
    )


def test_pg_enum_values_returns_value_list() -> None:
    class _Sample(str, enum.Enum):
        FOO = "foo"
        BAR = "bar"

    assert pg_enum_values(_Sample) == ["foo", "bar"]
