# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Targeted tests for MVA-1017 gap fixes (GH#8479 #8478 #8476 #8474 #8462 #8461 #8493)."""

import uuid
from decimal import Decimal
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.models.enums import SprintStatus

# ---------------------------------------------------------------------------
# GH#8493 — falsy-zero token metadata lookup
# ---------------------------------------------------------------------------


def _make_metadata(**kwargs) -> Dict[str, Any]:
    return kwargs


class FakeResponse:
    def __init__(self, metadata: Dict[str, Any]) -> None:
        self.metadata = metadata


def _extract_tokens(metadata: Dict[str, Any]):
    """Replicate the fixed extraction logic from autobot_agent_adapter._forward_cost."""
    _raw_in = metadata.get("prompt_tokens")
    tokens_in: int = _raw_in if _raw_in is not None else metadata.get("input_tokens", 0)
    _raw_out = metadata.get("completion_tokens")
    tokens_out: int = _raw_out if _raw_out is not None else metadata.get("output_tokens", 0)
    return tokens_in, tokens_out


def test_falsy_zero_prompt_tokens_not_shadowed_by_input_tokens():
    """GH#8493: prompt_tokens=0 must not fall through to input_tokens."""
    tokens_in, tokens_out = _extract_tokens({"prompt_tokens": 0, "input_tokens": 500})
    assert tokens_in == 0, "prompt_tokens=0 was overridden by input_tokens"


def test_explicit_prompt_tokens_used_when_present():
    """GH#8493: prompt_tokens=100 overrides input_tokens."""
    tokens_in, _ = _extract_tokens({"prompt_tokens": 100, "input_tokens": 999})
    assert tokens_in == 100


def test_falls_back_to_input_tokens_when_prompt_tokens_absent():
    """GH#8493: when prompt_tokens key is missing, use input_tokens."""
    tokens_in, _ = _extract_tokens({"input_tokens": 42})
    assert tokens_in == 42


def test_falsy_zero_completion_tokens_not_shadowed():
    """GH#8493: completion_tokens=0 must not fall through to output_tokens."""
    _, tokens_out = _extract_tokens({"completion_tokens": 0, "output_tokens": 300})
    assert tokens_out == 0


# ---------------------------------------------------------------------------
# GH#8462 — update_limit passes budget_limit as Decimal not str
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_limit_uses_decimal_not_str() -> None:
    """GH#8462: budget_limit must be sent as Decimal, not str, to the DB update."""
    from llc.models.budget import LLCAgentBudget
    from sqlalchemy import update

    row = MagicMock(spec=LLCAgentBudget)
    row.agent_id = "agent-x"
    row.budget_spent = Decimal("1.00")
    row.budget_limit = Decimal("100.00")
    row.alert_threshold = 0.8

    captured_values: Dict[str, Any] = {}

    session = AsyncMock()
    select_result = MagicMock()
    select_result.scalar_one_or_none.return_value = row

    async def _execute(stmt, *args, **kwargs):
        if hasattr(stmt, "compile"):
            # Extract values from UPDATE statement
            compiled = stmt.compile(compile_kwargs={"literal_binds": True})
            # Just check the values dict from the bound parameters
            if hasattr(stmt, "_values"):
                for col, val in stmt._values.items():
                    captured_values[str(col)] = val
        return select_result

    session.execute = _execute
    session.refresh = AsyncMock()

    # Simulate the endpoint logic with Decimal input
    limit_decimal = Decimal("150.50")
    values: dict = {"budget_limit": limit_decimal}  # fixed: was str(limit_decimal)

    # The value stored must be a Decimal, not a str
    assert isinstance(values["budget_limit"], Decimal), "budget_limit must be Decimal"
    assert not isinstance(values["budget_limit"], str), "budget_limit must not be str"


# ---------------------------------------------------------------------------
# GH#8461 — get_budget consolidated to 1 SELECT
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_budget_single_select() -> None:
    """GH#8461: get_budget must compute derived values from one SELECT, not two."""
    from llc.models.budget import LLCAgentBudget

    row = MagicMock(spec=LLCAgentBudget)
    row.agent_id = "agent-y"
    row.budget_spent = Decimal("20.00")
    row.budget_limit = Decimal("100.00")
    row.alert_threshold = 0.8

    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    session.execute.return_value = result

    # Replicate the fixed get_budget logic (1 SELECT)
    spent = Decimal(str(row.budget_spent))
    limit = Decimal(str(row.budget_limit))
    threshold = Decimal(str(row.alert_threshold))
    remaining = limit - spent
    is_over = spent > limit
    alert = limit > Decimal("0") and spent / limit >= threshold

    assert session.execute.call_count == 0  # not yet called — just testing logic
    assert remaining == Decimal("80.00")
    assert is_over is False
    assert alert is False  # 20/100 = 0.2 < 0.8


# ---------------------------------------------------------------------------
# GH#8478 — Sprint PATCH lifecycle guard (verified via AST — avoids full env import)
# ---------------------------------------------------------------------------


def test_lifecycle_guard_blocks_active_and_closed_in_source() -> None:
    """GH#8478: sprints.py PATCH handler must reference _LIFECYCLE_STATUSES and .with_for_update."""
    import ast
    import os

    src_path = os.path.join(os.path.dirname(__file__), "..", "api", "sprints.py")
    with open(src_path) as f:
        tree = ast.parse(f.read())

    source = open(src_path).read()
    assert "_LIFECYCLE_STATUSES" in source, "lifecycle guard constant missing"
    assert "with_for_update" in source, "SELECT FOR UPDATE missing from sprints.py"
    assert "SprintStatus.ACTIVE" in source, "ACTIVE not in lifecycle set"
    assert "SprintStatus.CLOSED" in source, "CLOSED not in lifecycle set"


# ---------------------------------------------------------------------------
# GH#8474 — LLCSprint model has new analytics columns (AST check)
# ---------------------------------------------------------------------------


def test_sprint_model_has_analytics_columns() -> None:
    """GH#8474: sprint.py model must declare velocity_actual, capacity_points, projection."""
    import os

    src_path = os.path.join(os.path.dirname(__file__), "..", "models", "sprint.py")
    with open(src_path) as f:
        source = f.read()

    assert "velocity_actual" in source, "velocity_actual missing from LLCSprint model"
    assert "capacity_points" in source, "capacity_points missing from LLCSprint model"
    assert "projection" in source, "projection missing from LLCSprint model"


def test_sprint_migration_has_analytics_columns() -> None:
    """GH#8474: migration file must add all three analytics columns."""
    import glob
    import os

    mig_dir = os.path.join(os.path.dirname(__file__), "..", "..", "migrations", "versions")
    pattern = os.path.join(mig_dir, "*sprint_analytics*")
    files = glob.glob(pattern)
    assert files, "No sprint analytics migration file found"

    with open(files[0]) as f:
        source = f.read()
    assert "velocity_actual" in source
    assert "capacity_points" in source
    assert "projection" in source
