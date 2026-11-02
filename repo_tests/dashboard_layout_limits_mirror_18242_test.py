# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The frontend's copy of the dashboard layout limits equals the server schema's (#18242 review).

The generated contract (``api.ts``) carries the layout's shapes but not its bounds, so the
frontend mirrors them once, in ``dashboardLayoutModel.ts``, to fit legacy data and user input
before a save. A mirror that drifts from the schema turns every save into a 422 again.
"""

from __future__ import annotations

import ast
import re

from repo_tests._paths import repo_root

_ROOT = repo_root()
_SCHEMA = _ROOT / "autobot-backend" / "api" / "schemas_users_dashboard_layouts.py"
_MODEL = _ROOT / "autobot-frontend" / "src" / "composables" / "dashboard" / "dashboardLayoutModel.ts"


def _field_bounds(cls: str, field: str) -> dict[str, int]:
    tree = ast.parse(_SCHEMA.read_text(encoding="utf-8"))
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == cls)
    stmt = next(s for s in node.body if isinstance(s, ast.AnnAssign) and s.target.id == field)
    names = {"MAX_DASHBOARDS": _schema_const("MAX_DASHBOARDS"), "MAX_WIDGETS": _schema_const("MAX_WIDGETS")}
    return {
        kw.arg: (names[kw.value.id] if isinstance(kw.value, ast.Name) else ast.literal_eval(kw.value))
        for kw in stmt.value.keywords
        if kw.arg in {"ge", "le", "max_length"}
    }


def _schema_const(name: str) -> int:
    return int(re.search(rf"^{name} = (\d+)$", _SCHEMA.read_text(encoding="utf-8"), re.M).group(1))


def _ts_const(name: str) -> int:
    match = re.search(rf"^export const {name} = ([\d_]+)$", _MODEL.read_text(encoding="utf-8"), re.M)
    assert match, f"export const {name} not found in {_MODEL.name}"
    return int(match.group(1).replace("_", ""))


def test_the_frontend_limits_equal_the_schema() -> None:
    expected = {
        "MAX_TEXT": _field_bounds("Dashboard", "name")["max_length"],
        "MAX_DASHBOARDS": _field_bounds("DashboardLayout", "dashboards")["max_length"],
        "MAX_WIDGETS": _field_bounds("Dashboard", "widgets")["max_length"],
        "REFRESH_INTERVAL_MAX": _field_bounds("DashboardWidget", "refreshInterval")["le"],
        "HEIGHT_MIN": _field_bounds("DashboardWidget", "height")["ge"],
        "HEIGHT_MAX": _field_bounds("DashboardWidget", "height")["le"],
    }
    assert _field_bounds("DashboardWidget", "title")["max_length"] == expected["MAX_TEXT"]
    actual = {name: _ts_const(name) for name in expected}
    assert actual == expected, f"dashboardLayoutModel.ts drifted from the schema: {actual} != {expected}"
