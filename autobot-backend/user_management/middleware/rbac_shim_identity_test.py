# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shim identity tests for the deduplicated RBAC middleware (#18088).

Both backends carried byte-identical 595-line copies of
`user_management/middleware/rbac_middleware.py` against the same `audit_logs`
table. That is the shape #6511 named a security drift risk: a permission added
to one service's copy is not enforced by the other. There is one implementation
now, in `autobot_shared.middleware.rbac_middleware`, and these tests pin that
the historical import path resolves to the SAME objects rather than to a second
copy -- modelled on `tests/test_plugin_sdk_shim.py` (#11636).
"""

from autobot_shared.middleware import rbac_middleware as canonical
from user_management.middleware import rbac_middleware as shim


def test_the_decorators_are_the_same_objects():
    assert shim.require_permission is canonical.require_permission
    assert shim.require_any_permission is canonical.require_any_permission
    assert shim.require_all_permissions is canonical.require_all_permissions


def test_the_middleware_class_is_the_same_object():
    assert shim.RBACMiddleware is canonical.RBACMiddleware


def test_the_singleton_is_shared_across_import_paths():
    """One instance, or the permission cache is per-import-path."""
    assert shim.rbac_middleware is canonical.rbac_middleware


def test_the_permission_cache_is_one_dict():
    """A second cache would let one path serve stale permissions after a revoke."""
    assert shim._permission_cache is canonical._permission_cache
    canonical._permission_cache["_shim_probe"] = (frozenset(), 0.0)
    try:
        assert "_shim_probe" in shim._permission_cache
    finally:
        canonical._permission_cache.pop("_shim_probe", None)


def test_the_shim_defines_no_implementation_of_its_own():
    """The shim must re-export, never redeclare -- a redeclaration is the fork back."""
    import ast
    import pathlib

    tree = ast.parse(pathlib.Path(shim.__file__).read_text(encoding="utf-8"))
    declared = [n.name for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))]
    assert declared == [], f"shim declares its own {declared}; it must only re-export"
