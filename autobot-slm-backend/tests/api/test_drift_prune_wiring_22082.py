# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Wiring contract of the drift-prune endpoints (#22082), read from source (AST).

Importing ``api.code_sync`` needs the model stand-ins documented in
``_code_sync_import.py``; what must hold here is structural, so the module is
parsed instead of imported.
"""

from __future__ import annotations

import ast
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
_API = (_BACKEND / "api" / "drift_prune.py").read_text(encoding="utf-8")
_TREE = ast.parse(_API)


def _function(name: str) -> ast.AsyncFunctionDef:
    return next(n for n in ast.walk(_TREE) if isinstance(n, ast.AsyncFunctionDef) and n.name == name)


def test_both_routes_are_admin_only() -> None:
    for name in ("preview_drift_prune", "confirm_drift_prune"):
        assert "require_permission(Permission.ADMIN_SYSTEM)" in ast.unparse(_function(name).args), name


def test_the_destructive_route_checks_deploy_state_and_audits() -> None:
    body = ast.unparse(_function("confirm_drift_prune"))
    assert "_reject_if_deploy_in_progress()" in body
    assert "_audit_prune(" in body
    assert "apply_prune(" in body


def test_both_routes_validate_the_component_against_the_drift_check_set() -> None:
    for name in ("preview_drift_prune", "confirm_drift_prune"):
        assert "_require_component(request.component)" in ast.unparse(_function(name)), name


def test_the_module_is_registered_from_full_tree_drift() -> None:
    registrar = (_BACKEND / "api" / "full_tree_drift.py").read_text(encoding="utf-8")
    assert "from api import drift_prune" in registrar
