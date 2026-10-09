#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One RBAC middleware, shared by both services (#18088).

`autobot-backend` and `autobot-slm-backend` each carried a 595/594-line copy of the
permission-enforcement middleware. `diff` reported 11 lines, all of them comment text --
two comments describing the same audit-swallowing bug under different issue numbers
(#14750 and #14654), which is #6511's warning in practice: "divergent permission logic
across two services that interoperate is a security drift risk."

The implementation now lives in `autobot_shared/user_management/middleware/`, and each
service keeps a re-export shim at the import path its call sites already use. This guard
pins that shape: one implementation, two shims, and no third copy.

Owner decision 2026-10-09 chose the shared package over an enforced byte-identical
mirror: a guard proves the copies agree today, a shared module makes disagreement
impossible.
"""

from __future__ import annotations

import ast

import pytest
from repo_tests._paths import repo_root

CANONICAL = "autobot_shared/user_management/middleware/rbac_middleware.py"
SHIMS = (
    "autobot-backend/user_management/middleware/rbac_middleware.py",
    "autobot-slm-backend/user_management/middleware/rbac_middleware.py",
)

#: The names call sites import from the shim. `rbac_middleware` is the module-level
#: singleton and `_permission_cache` crosses the boundary despite the underscore -- both
#: are imported by real call sites, so a shim that omits them breaks them at runtime.
REQUIRED_EXPORTS = frozenset(
    {
        "RBACMiddleware",
        "rbac_middleware",
        "require_permission",
        "require_any_permission",
        "require_all_permissions",
        "_permission_cache",
    }
)

#: A shim may not grow logic. Enforcement lives in exactly one file.
MAX_SHIM_LINES = 60


def _tree(rel: str) -> ast.Module:
    return ast.parse((repo_root() / rel).read_text(encoding="utf-8"))


def _defined_names(tree: ast.Module) -> set[str]:
    """Functions and classes DEFINED here — not names merely imported."""
    return {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}


def _imported_names(tree: ast.Module) -> set[str]:
    return {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }


def test_the_canonical_implementation_exists_and_holds_the_logic() -> None:
    defined = _defined_names(_tree(CANONICAL))
    assert "RBACMiddleware" in defined, f"{CANONICAL} must DEFINE RBACMiddleware, not import it"
    for decorator in ("require_permission", "require_any_permission", "require_all_permissions"):
        assert decorator in defined, f"{CANONICAL} must define {decorator}"


@pytest.mark.parametrize("rel", SHIMS)
def test_each_service_keeps_a_shim_not_a_copy(rel: str) -> None:
    """A second implementation is the defect; a thin re-export is the design."""
    source = (repo_root() / rel).read_text(encoding="utf-8")
    lines = len(source.splitlines())
    assert lines <= MAX_SHIM_LINES, (
        f"#18088: {rel} is {lines} lines. Enforcement lives in {CANONICAL}; this path is a "
        "re-export shim. A copy here is the security drift #6511 named."
    )
    defined = _defined_names(ast.parse(source))
    assert not defined, f"#18088: {rel} defines {sorted(defined)} — a shim defines nothing"


@pytest.mark.parametrize("rel", SHIMS)
def test_each_shim_re_exports_every_name_its_call_sites_import(rel: str) -> None:
    """Pinned by name, because a missing re-export fails only at the call site."""
    missing = REQUIRED_EXPORTS - _imported_names(_tree(rel))
    assert not missing, (
        f"#18088: {rel} does not re-export {sorted(missing)}. Call sites import these "
        "(api/secrets.py, api/envelope_secrets.py, user_management/services/user_service.py, "
        "and the cache-invalidation test); omitting one breaks them at runtime, not here."
    )


@pytest.mark.parametrize("rel", SHIMS)
def test_each_shim_points_at_the_canonical_module(rel: str) -> None:
    modules = {node.module for node in ast.walk(_tree(rel)) if isinstance(node, ast.ImportFrom) and node.module}
    expected = "autobot_shared.user_management.middleware.rbac_middleware"
    assert expected in modules, f"#18088: {rel} must re-export from {expected}, found {sorted(modules)}"


def test_no_third_copy_of_the_middleware_has_appeared() -> None:
    """By content, not by filename — a copy under any name is still a copy."""
    from tools.lint._scan_helpers import tracked_paths

    root = repo_root()
    offenders = []
    parsed = 0
    for rel in tracked_paths(root, "*.py"):
        if rel == CANONICAL or rel in SHIMS:
            continue
        if rel.endswith("_test.py") or rel.rsplit("/", 1)[-1].startswith("test_") or "/tests/" in rel:
            continue
        try:
            source = (root / rel).read_text(encoding="utf-8")
        except OSError:
            continue
        if "RBACMiddleware" not in source:
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        parsed += 1
        if "RBACMiddleware" in _defined_names(tree):
            offenders.append(rel)

    assert parsed > 0, "no non-test file mentions RBACMiddleware — the sweep is looking wrong"
    assert not offenders, f"#18088: {offenders} define RBACMiddleware again. One implementation, in {CANONICAL}."


def test_the_shim_detector_has_a_contrast_pair() -> None:
    """A detector that never fires passes every assertion above by finding nothing."""
    a_copy = "class RBACMiddleware:\n    def __init__(self):\n        pass\n"
    assert _defined_names(ast.parse(a_copy)) == {"RBACMiddleware"}, "must see a real copy"

    a_shim = (
        "from autobot_shared.user_management.middleware.rbac_middleware import (\n"
        "    RBACMiddleware,\n    rbac_middleware,\n)\n"
    )
    assert _defined_names(ast.parse(a_shim)) == set(), "must NOT call a re-export a definition"
    assert {"RBACMiddleware", "rbac_middleware"} <= _imported_names(ast.parse(a_shim))
