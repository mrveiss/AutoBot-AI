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

from tools.lint import _parse_cache as parse_cache

CANONICAL = "autobot_shared/user_management/middleware/rbac_middleware.py"
#: The decorators live beside the middleware (split to stay under the file-size ceiling).
CANONICAL_DECORATORS = "autobot_shared/user_management/middleware/rbac_decorators.py"
MIDDLEWARE_DIR = "autobot_shared/user_management/middleware"
DECORATOR_NAMES = ("require_permission", "require_any_permission", "require_all_permissions")
#: What the decorators module defines now; the first two are the gate's, retired here.
DEFINED_DECORATORS = ("require_all_permissions",)
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
        "require_all_permissions",
        "_permission_cache",
    }
)

#: A shim may not grow logic. Enforcement lives in exactly one file.
MAX_SHIM_LINES = 60


def _tree(rel: str) -> ast.Module:
    return parse_cache.parse((repo_root() / rel).read_text(encoding="utf-8"))


def _defined_names(tree: ast.Module) -> set[str]:
    """Functions and classes DEFINED here — not names merely imported."""
    return {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}


#: Names only the DB-backed middleware's decorators touch. `auth_rbac.py` and the SLM's
#: `services/auth.py` define same-named decorators over a different, role-based
#: implementation, so the name alone would make them offenders.
_MIDDLEWARE_INTERNALS = frozenset({"rbac_middleware", "_emit_permission_denied_audit"})


def _redefines_enforcement(tree: ast.Module) -> bool:
    """A copy of the middleware, or of any one of ITS permission decorators (#18088 AC3)."""
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "RBACMiddleware":
            return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in DECORATOR_NAMES:
            used = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            if used & _MIDDLEWARE_INTERNALS:
                return True
    return False


def _is_type_checking(test: ast.expr) -> bool:
    """Exactly `TYPE_CHECKING` or `typing.TYPE_CHECKING` -- not `not TYPE_CHECKING`."""
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING" and isinstance(test.value, ast.Name)


def _is_service_module(name: str) -> bool:
    return name == "user_management" or name.startswith("user_management.")


def _service_import_names(sub: ast.AST) -> list[str]:
    """`user_management.*` modules named by one node: an import or a literal dynamic import."""
    if isinstance(sub, ast.ImportFrom) and sub.level == 0 and sub.module:
        names = [sub.module]
    elif isinstance(sub, ast.Import):
        names = [alias.name for alias in sub.names]
    elif isinstance(sub, ast.Call) and sub.args and isinstance(sub.args[0], ast.Constant):
        func = sub.func
        callee = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if callee not in ("import_module", "__import__") or not isinstance(sub.args[0].value, str):
            return []
        names = [sub.args[0].value]
    else:
        return []
    return [n for n in names if _is_service_module(n)]


def _scan_statements(nodes: list[ast.stmt]) -> list[str]:
    found: list[str] = []
    for node in nodes:
        if isinstance(node, ast.If) and _is_type_checking(node.test):
            found += _scan_statements(node.orelse)  # only the body is type-only
            continue
        for sub in ast.walk(node):
            found += _service_import_names(sub)
    return found


def _runtime_service_imports(tree: ast.Module) -> list[str]:
    """Module-level `user_management.*` imports outside a `TYPE_CHECKING` body.

    Shared code may not import a service package at runtime: `user_management` resolves to
    whichever service is on `sys.path`, so it would bind to the wrong one (#18088). Only the
    body of `if TYPE_CHECKING:` is exempt; its `else:` runs, and so does
    `if not TYPE_CHECKING:`. `importlib.import_module("user_management.x")` and
    `__import__(...)` with a literal are the same import by another spelling.
    """
    return _scan_statements(tree.body)


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
    decorators_defined = _defined_names(_tree(CANONICAL_DECORATORS))
    for decorator in DEFINED_DECORATORS:
        assert decorator in decorators_defined, f"{CANONICAL_DECORATORS} must define {decorator}"


@pytest.mark.parametrize("rel", SHIMS)
def test_each_service_keeps_a_shim_not_a_copy(rel: str) -> None:
    """A second implementation is the defect; a thin re-export is the design."""
    source = (repo_root() / rel).read_text(encoding="utf-8")
    lines = len(source.splitlines())
    assert lines <= MAX_SHIM_LINES, (
        f"#18088: {rel} is {lines} lines. Enforcement lives in {CANONICAL}; this path is a "
        "re-export shim. A copy here is the security drift #6511 named."
    )
    defined = _defined_names(parse_cache.parse(source))
    assert not defined, f"#18088: {rel} defines {sorted(defined)} — a shim defines nothing"


@pytest.mark.parametrize("rel", SHIMS)
def test_each_shim_re_exports_every_name_its_call_sites_import(rel: str) -> None:
    """Pinned by name, because a missing re-export fails only at the call site."""
    missing = REQUIRED_EXPORTS - _imported_names(_tree(rel))
    assert not missing, (
        f"#18088: {rel} does not re-export {sorted(missing)}. Call sites import these "
        "(api/secrets.py, api/envelope_secrets.py, "
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
        if rel in (CANONICAL, CANONICAL_DECORATORS) or rel in SHIMS:
            continue
        if rel.endswith("_test.py") or rel.rsplit("/", 1)[-1].startswith("test_") or "/tests/" in rel:
            continue
        try:
            source = (root / rel).read_text(encoding="utf-8")
        except OSError:
            continue
        if "RBACMiddleware" not in source and not any(name in source for name in DECORATOR_NAMES):
            continue
        try:
            tree = parse_cache.parse(source)
        except SyntaxError:
            continue
        parsed += 1
        if _redefines_enforcement(tree):
            offenders.append(rel)

    assert parsed > 0, "no non-test file mentions RBACMiddleware — the sweep is looking wrong"
    assert not offenders, (
        f"#18088: {offenders} define RBACMiddleware or a permission decorator again. "
        f"One implementation, in {CANONICAL} and {CANONICAL_DECORATORS}."
    )


def test_the_shim_detector_has_a_contrast_pair() -> None:
    """A detector that never fires passes every assertion above by finding nothing."""
    a_copy = "class RBACMiddleware:\n    def __init__(self):\n        pass\n"
    assert _defined_names(parse_cache.parse(a_copy)) == {"RBACMiddleware"}, "must see a real copy"

    a_shim = (
        "from autobot_shared.user_management.middleware.rbac_middleware import (\n"
        "    RBACMiddleware,\n    rbac_middleware,\n)\n"
    )
    assert _defined_names(parse_cache.parse(a_shim)) == set(), "must NOT call a re-export a definition"
    assert {"RBACMiddleware", "rbac_middleware"} <= _imported_names(parse_cache.parse(a_shim))


def test_the_shared_middleware_imports_no_service_module_at_runtime() -> None:
    """Dependencies are injected (`configure_rbac`), never imported from a service."""
    modules = sorted((repo_root() / MIDDLEWARE_DIR).glob("*.py"))
    assert modules, f"no module found under {MIDDLEWARE_DIR} -- the sweep is looking wrong"
    offenders = {m.name: _runtime_service_imports(parse_cache.parse(m.read_text(encoding="utf-8"))) for m in modules}
    offenders = {name: found for name, found in offenders.items() if found}
    assert not offenders, (
        f"#18088: {offenders} import a service's user_management at runtime. Shared code takes "
        "it by injection (configure_rbac), as session_scope takes its session maker."
    )


def test_the_runtime_import_detector_has_a_contrast_pair() -> None:
    bad = "from user_management.database import db_session_context\nimport user_management.models\n"
    assert _runtime_service_imports(parse_cache.parse(bad)) == ["user_management.database", "user_management.models"]

    ok = (
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n    from user_management.services import UserService\n"
        "from autobot_shared.user_management.models.audit import AuditLog\n"
    )
    assert _runtime_service_imports(parse_cache.parse(ok)) == [], "TYPE_CHECKING and autobot_shared imports are allowed"


def test_the_copy_detector_catches_a_partial_copy_with_a_contrast_pair() -> None:
    """A copy defining only one decorator is still a second implementation (#18088 AC3)."""
    for name in DECORATOR_NAMES:
        copy = f"def {name}(p):\n    async def w():\n        return await rbac_middleware.check_permission(p)\n"
        assert _redefines_enforcement(parse_cache.parse(copy)), name
    assert _redefines_enforcement(parse_cache.parse("class RBACMiddleware:\n    pass\n"))

    shim = "from autobot_shared.user_management.middleware.rbac_decorators import require_permission\n"
    assert not _redefines_enforcement(parse_cache.parse(shim)), "a re-export is not a definition"
    unrelated = "def require_permission(p):\n    return security_layer.check_permission(p)\n"
    assert not _redefines_enforcement(parse_cache.parse(unrelated)), "a different implementation is not a copy"


def test_the_type_checking_exemption_covers_only_the_body() -> None:
    """Contrast fixtures: the else branch and dynamic imports run, so they are flagged."""
    in_else = "if TYPE_CHECKING:\n    pass\nelse:\n    from user_management.x import Y\n"
    assert _runtime_service_imports(parse_cache.parse(in_else)) == ["user_management.x"]

    in_body = "if TYPE_CHECKING:\n    from user_management.x import Y\n"
    assert _runtime_service_imports(parse_cache.parse(in_body)) == []

    qualified = "import typing\nif typing.TYPE_CHECKING:\n    from user_management.x import Y\n"
    assert _runtime_service_imports(parse_cache.parse(qualified)) == []

    negated = "if not TYPE_CHECKING:\n    from user_management.x import Y\n"
    assert _runtime_service_imports(parse_cache.parse(negated)) == ["user_management.x"]

    dynamic = 'import importlib\nimportlib.import_module("user_management.x")\n__import__("user_management.y")\n'
    assert _runtime_service_imports(parse_cache.parse(dynamic)) == ["user_management.x", "user_management.y"]

    harmless = 'import importlib\nimportlib.import_module("autobot_shared.x")\n'
    assert _runtime_service_imports(parse_cache.parse(harmless)) == []


# --- AC2: a permission one service enforces, the other must enforce the same way -------------
#
# Read from the real enforcement source, not a hand-copied list: the enum from
# `permissions.py`, the gate bindings and every `Permission.X` named in a gate factory call
# from each service's own source. Behavioural parity (same answer per role/grant/org row) is
# `cross_service_permission_parity_18263_test`; this is the static half that names WHY it holds.

_PERMISSIONS = "autobot_shared/auth/permissions.py"
_GATE_FACTORIES = frozenset({"require_permission", "require_any_permission", "require_all_permissions"})
#: Each service's own auth module, where it binds the one shared gate to its caller dependency.
_GATE_BINDINGS = {
    "autobot-backend": "autobot-backend/auth_rbac.py",
    "autobot-slm-backend": "autobot-slm-backend/services/auth.py",
}


def _enum_members(tree: ast.Module) -> set[str]:
    """Member names of `class Permission` -- the set every route's argument must come from."""
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "Permission":
            return {
                t.id
                for stmt in node.body
                if isinstance(stmt, ast.Assign)
                for t in stmt.targets
                if isinstance(t, ast.Name)
            }
    return set()


def _enforced_members(tree: ast.Module) -> set[str]:
    """`X` for every `Permission.X` inside an argument of a gate-factory call."""
    found: set[str] = set()
    for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
        func = call.func
        if (func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")) not in _GATE_FACTORIES:
            continue
        for arg in (*call.args, *(k.value for k in call.keywords)):
            found |= {
                n.attr
                for n in ast.walk(arg)
                if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "Permission"
            }
    return found


def _binds_the_one_gate(tree: ast.Module) -> bool:
    """`require_permission = <gate>.require_permission` (and any) where `<gate> = PermissionGate(...)`."""
    gates, bound = set(), set()
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        name, value = node.targets[0].id, node.value
        if isinstance(value, ast.Call) and getattr(value.func, "id", None) == "PermissionGate":
            gates.add(name)
        elif isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name) and value.value.id in gates:
            bound.add((name, value.attr))
    return {("require_permission", "require_permission"), ("require_any_permission", "require_any_permission")} <= bound


@pytest.mark.parametrize(("service", "rel"), sorted(_GATE_BINDINGS.items()))
def test_each_service_enforces_through_the_one_shared_gate(service: str, rel: str) -> None:
    """A service that bound its own factory would enforce a permission the other does not."""
    assert _binds_the_one_gate(
        _tree(rel)
    ), f"{rel}: {service} must bind require_permission/require_any_permission to a PermissionGate"


def test_every_enforced_permission_is_a_member_of_the_one_enum() -> None:
    """Both services enforce only members of the shared enum, and each enforces a non-empty set."""
    from tools.lint._scan_helpers import tracked_paths

    members = _enum_members(_tree(_PERMISSIONS))
    assert len(members) > 10, f"{_PERMISSIONS}: parsed {len(members)} Permission members -- the parser is looking wrong"
    root = repo_root()
    enforced: dict[str, set[str]] = {service: set() for service in _GATE_BINDINGS}
    for rel in tracked_paths(root, *_GATE_BINDINGS):
        name = rel.rsplit("/", 1)[-1]
        if not rel.endswith(".py") or name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel:
            continue
        source = (root / rel).read_text(encoding="utf-8")
        if "Permission." in source:
            enforced[rel.split("/", 1)[0]] |= _enforced_members(parse_cache.parse(source))
    for service, names in enforced.items():
        assert names, f"{service}: no gate factory call names a Permission member -- the sweep is looking wrong"
        assert names <= members, f"{service} enforces {sorted(names - members)}, which are not Permission members"


def test_the_parity_detectors_have_contrast_pairs() -> None:
    gate = "g = PermissionGate(dep)\nrequire_permission = g.require_permission\nrequire_any_permission = g.require_any_permission\n"
    assert _binds_the_one_gate(parse_cache.parse(gate))
    own = "def require_permission(p):\n    return p\nrequire_any_permission = require_permission\n"
    assert not _binds_the_one_gate(parse_cache.parse(own)), "a service-local factory is the fork"
    src = "x = Depends(require_any_permission(Permission.A, Permission.B))\ny = Permission.C\n"
    assert _enforced_members(parse_cache.parse(src)) == {"A", "B"}, "only members named inside a gate call count"
    assert _enum_members(parse_cache.parse("class Permission(str, Enum):\n    A = 'a'\n    B = 'b'\n")) == {"A", "B"}
