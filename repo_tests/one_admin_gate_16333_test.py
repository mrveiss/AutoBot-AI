# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One admin gate for the backend (#16333, owner ruling b).

Admin decisions go through ``auth_middleware.check_admin_permission``, which uses the
shared ``is_admin_role`` predicate. The internal service key is admitted only through
``auth_service_opt_in`` (a route that names its caller). This guard fails on a NEW local
spelling of either decision:

* ``require_role(...)`` naming ``"admin"``/``"superadmin"``, a second admin gate;
* a comparison against the literal ``"admin"``/``"superadmin"``, a hand-rolled predicate;
* a direct ``verify_internal_api_key(...)`` call, a second place the key is admitted.

It reads the syntax tree, so prose naming these shapes is not a hit. Also caught: an aliased
``verify_internal_api_key`` import or a ``getattr`` of it, a raw ``compare_digest`` against the
internal key, ``Role.ADMIN`` / ``Role.ADMIN.value`` comparisons, any letter case of the literals,
``startswith``/``endswith("admin")``, ``match role: case "admin":``, a role-named collection
holding an admin role (a second ``ADMIN_ROLES``), and a hand-built admin principal
(``{"role": "admin"}``, ``user["role"] = "admin"``, ``user.role = "admin"``, ``role="admin"``).

It also fails on a new FUNCTION named like an admin check (``require_admin``, ``require_*admin*``,
``is_*admin*``, ``check_*admin*``...), even one built on ``is_admin_role``: the existing ones are
recorded with the reason each is not a second gate.

Heuristic limits, not caught: a default such as ``role or "admin"`` (no comparison), a regex such as
``re.match("admin", role)``, and a decision whose literals arrive from configuration or another module.

Scope: ``autobot-backend``. ``autobot_shared`` holds the canonical predicate
(``auth.permissions.is_admin_role``) and the key check itself. The SLM is a separate service with
its own admin-only gate (#20628), and the owner's ruling (b) on #16333 keeps the SLM's own
service-principal path; neither is a second gate inside this backend. The existing sites
are listed below with counts. The pending list only shrinks: PR B of #16333 moves the
``require_role`` sites, and PR C the local checks. Superadmin-only and company-membership
decisions are different concepts, recorded with their reason.
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOT = repo_root()
_ROOTS = ("autobot-backend",)
_TEST_FILE = re.compile(r"(_test\.py$|/tests?/|/test_[^/]*\.py$|conftest\.py$|/testkit/)")
_ADMIN = frozenset({"admin", "superadmin"})

#: The one place the key is admitted.
_CANONICAL = {("autobot-backend/auth_service_opt_in.py", "key")}

#: Permanent, each with its reason.
_RECORDED = {
    # The System-vault service principal: a separate mechanism, kept as is by the owner's ruling.
    ("autobot-backend/api/envelope_secrets.py", "key"): 1,
    # Refuses the key (stricter than the gate); it never admits it.
    ("autobot-backend/security/human_admin.py", "key"): 1,
    # Refuses the key on SYSTEM-vault secret writes (#17731); it never admits it.
    ("autobot-backend/api/secrets_system_vault.py", "key"): 1,
    # Membership of "admin" in a configured allowed-roles list, decided with is_admin_role.
    ("autobot-backend/services/mcp_external_bridge.py", "literal"): 1,
    # The auth-disabled (dev-only) principal; the human-decision check refuses it (#17042).
    ("autobot-backend/auth_middleware.py", "grant"): 1,
    # Superadmin ONLY, stricter than admin: the shared provider token serves every org (#19241).
    ("autobot-backend/api/provider_auth.py", "require_role"): 1,
    # Superadmin ONLY: the root-read predicate, ``is_superadmin_role`` (admin is not root).
    ("autobot-backend/knowledge/root_read.py", "literal"): 1,
    # Cross-org KB writes: platform_admin / superadmin, a platform-level concept (#12786).
    ("autobot-backend/llc/kb/write_guard.py", "set"): 1,
    # Company membership roles (owner / admin / lead of ONE company), not the system admin role.
    ("autobot-backend/llc/api/controls.py", "set"): 1,
    ("autobot-backend/llc/api/replay.py", "set"): 1,
    ("autobot-backend/llc/services/authz.py", "set"): 1,
    ("autobot-backend/llc/services/work_item_service.py", "set"): 1,
}

#: Functions NAMED like an admin check (``_ADMIN_DEF``), each with the reason it is not a second gate.
#: A new one fails: call ``check_admin_permission`` / ``is_admin_role`` inline, or record it here (#16333).
_RECORDED_DEFS = {
    # Delegates to the one gate (``Depends(check_admin_permission)`` or an awaited call), then adds a step.
    "api/feature_flags.py": {"require_admin_role"},
    "api/provider_auth_scope.py": {"provider_caller_is_admin"},
    "api/settings_config.py": {"require_settings_admin"},
    "api/system.py": {"admin_check"},  # a route handler, gated by the one gate
    "auth_rbac.py": {"check_admin_mcp_tool_permission"},
    # The one predicate (``is_admin_role``) over a caller record that is not a bare role.
    "api/live_events.py": {"_is_admin"},
    "api/redis_mcp/router.py": {"_is_admin"},
    "api/voice_bundle_user.py": {"_is_admin", "_check_self_or_admin"},
    "services/workflow_rbac.py": {"_is_admin"},
    "transcriber/deps.py": {"caller_is_admin"},  # reads the flag ``authenticate`` set with is_admin_role
    "knowledge/remote_read.py": {"remote_read_is_admin"},  # ``caller_reader``, built on is_admin_role
    # Ownership OR the one predicate: a resource rule, not an admin gate.
    "api/user_management/dependencies.py": {
        "require_self_or_admin",
        # The platform-admin CLAIM (``is_platform_admin``), a separate concept from the admin role.
        "_is_platform_admin_claim",
        "require_platform_admin_claim",
        "require_platform_admin",
    },
    "services/workflow_automation/workflow_ownership.py": {"is_owner_or_admin", "require_owner_or_admin"},
    "chat_workflow/tiered_context_sources.py": {"_is_platform_admin"},
    # Superadmin ONLY (root reads), stricter than admin.
    "knowledge/root_read.py": {"is_superadmin_role", "is_superadmin_user"},
    # Company / org membership roles: admin of ONE company, not the system admin role (#20778).
    "api/chat_presets.py": {"_is_org_admin"},
    "security/session_ownership.py": {"_is_org_admin_access"},
    "llc/api/budget.py": {"_require_budget_admin", "_require_limit_admin"},
    "llc/api/company_ceo.py": {"_require_owner_or_admin"},
    "llc/api/replay.py": {"_check_admin"},
    "llc/api/secrets.py": {"_require_secret_admin"},
    "llc/services/authz.py": {"require_company_admin", "require_company_admin_unless_platform"},
    "llc/services/company.py": {"_require_gate_admin"},
    # Not authorization: the security scanner probes a target's /admin paths.
    "agents/security_scanner_agent.py": {"_check_admin_path"},
}
_GATE_DEF = ("auth_middleware.py", "check_admin_permission")
_ADMIN_DEF = re.compile(
    r"^_?(require_\w*admin\w*|is_\w*admin\w*|\w+_is_admin|check_\w*admin\w*|admin_check|\w+_admin_(gate|check|required|only))$",
    re.IGNORECASE,
)


#: Pending migration. **Only shrinks.**
_PENDING = {
    # SecurityLayer.authenticate_user derives admin from the username; it waits on #20590/#20749,
    # which hold the same file.
    ("autobot-backend/security_layer.py", "literal"): 1,
}


def _source_files(root: Path) -> list[str]:
    try:
        paths = tracked_paths(root, *_ROOTS)
    except EmptyEnumeration:
        return []
    return [p for p in paths if p.endswith(".py") and not _TEST_FILE.search(p)]


def _all_python(root: Path) -> int:
    try:
        return sum(1 for p in tracked_paths(root, *_ROOTS) if p.endswith(".py"))
    except EmptyEnumeration:
        return 0


#: Measured 2026-11-03: 2822 of 5274 tracked backend .py files (54%) are non-test source.
REACH = declare(
    "one-admin-gate",
    discover=_source_files,
    reference=_all_python,
    min_fraction=0.4,
    what="non-test backend python source",
    roots=_ROOTS,
)


_ADMIN_ATTRS = frozenset({"ADMIN", "SUPERADMIN"})
_KEY_FN = "verify_internal_api_key"
_COLLECTIONS = (ast.Tuple, ast.Set, ast.List)


def _names_admin(node: ast.expr) -> bool:
    """``"admin"`` / ``"superadmin"`` in any case, or ``Role.ADMIN`` / ``Role.ADMIN.value``."""
    if isinstance(node, _COLLECTIONS):
        return any(_names_admin(e) for e in node.elts)
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str) and node.value.lower() in _ADMIN
    if isinstance(node, ast.Attribute) and node.attr == "value":
        node = node.value  # Role.ADMIN.value
    return isinstance(node, ast.Attribute) and node.attr in _ADMIN_ATTRS


def _call_name(node: ast.Call) -> str | None:
    return getattr(node.func, "id", None) or getattr(node.func, "attr", None)


def _mentions_internal_key(node: ast.AST) -> bool:
    return any("internal_api_key" in (getattr(n, "id", None) or getattr(n, "attr", None) or "") for n in ast.walk(node))


_ROLE_SET_NAME = re.compile(r"role|admin|privileg", re.IGNORECASE)


def _bound_name(node: ast.AST) -> str:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return " ".join(getattr(t, "id", None) or getattr(t, "attr", None) or "" for t in targets)


def _role_set(node: ast.AST) -> bool:
    """A collection of admin roles bound to a role-named variable: a second ``ADMIN_ROLES``."""
    value = getattr(node, "value", None)
    if not isinstance(node, (ast.Assign, ast.AnnAssign)) or value is None:
        return False
    if not _ROLE_SET_NAME.search(_bound_name(node)):
        return False  # tag lists, subdomain lists, keyword lists
    if isinstance(value, ast.Call) and _call_name(value) in ("frozenset", "set", "tuple", "list") and value.args:
        value = value.args[0]
    elts = value.elts if isinstance(value, _COLLECTIONS) else []
    return any(_names_admin(e) for e in elts if not isinstance(e, _COLLECTIONS))


def _role_write(node: ast.AST) -> bool:
    """``user["role"] = "admin"``, ``user.role = "admin"``, or ``role="admin"`` passed as a keyword."""
    if isinstance(node, ast.Assign) and _names_admin(node.value):
        return any(
            (isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant) and t.slice.value == "role")
            or (isinstance(t, ast.Attribute) and t.attr == "role")
            for t in node.targets
        )
    return isinstance(node, ast.keyword) and node.arg == "role" and _names_admin(node.value)


def _call_kind(node: ast.Call) -> str | None:
    name = _call_name(node)
    if name == "require_role" and any(_names_admin(a) for a in node.args):
        return "require_role"
    if name == _KEY_FN:
        return "key"
    if name == "getattr" and any(isinstance(a, ast.Constant) and a.value == _KEY_FN for a in node.args):
        return "key"  # getattr(module, "verify_internal_api_key")
    if name == "compare_digest" and any(_mentions_internal_key(a) for a in node.args):
        return "key"  # the key check spelled out by hand
    if name in ("startswith", "endswith") and any(_names_admin(a) for a in node.args):
        return "literal"  # role.lower().startswith("admin")
    return None


def _node_kind(node: ast.AST) -> str | None:
    if isinstance(node, ast.ImportFrom) and any(
        a.name == _KEY_FN and a.asname not in (None, a.name) for a in node.names
    ):
        return "key"  # an alias would hide every call from the name match
    if isinstance(node, ast.Dict) and any(
        isinstance(k, ast.Constant) and k.value == "role" and _names_admin(v) for k, v in zip(node.keys, node.values)
    ):
        return "grant"  # a hand-built admin principal, e.g. {"role": "admin"}
    if _role_write(node):
        return "grant"
    if _role_set(node):
        return "set"
    if isinstance(node, ast.Call):
        return _call_kind(node)
    if isinstance(node, ast.Compare) and any(_names_admin(side) for side in (node.left, *node.comparators)):
        return "literal"
    if isinstance(node, ast.MatchValue) and _names_admin(node.value):
        return "literal"  # match role: case "admin":
    return None


def admin_defs(source: str) -> set[str]:
    """Names of functions defined in *source* that are named like an admin check."""
    return {
        n.name
        for n in ast.walk(ast.parse(source))
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and _ADMIN_DEF.match(n.name)
    }


def admin_decisions(source: str) -> Counter:
    """Local admin decisions in *source*, by kind."""
    return Counter(kind for node in ast.walk(ast.parse(source)) if (kind := _node_kind(node)))


def _population() -> tuple[dict[tuple[str, str], int], dict[str, set[str]]]:
    examined = REACH.examined(_ROOT)
    found: dict[tuple[str, str], int] = {}
    defs: dict[str, set[str]] = {}
    for rel in examined:
        try:
            source = (_ROOT / rel).read_text(encoding="utf-8")
            counts, names = admin_decisions(source), admin_defs(source)
        except SyntaxError:
            continue
        found.update({(rel, kind): n for kind, n in counts.items()})
        if names:
            defs[rel.removeprefix("autobot-backend/")] = names
    REACH.completed(len(examined), _ROOT)
    return found, defs


def test_no_new_local_admin_decision():
    population, _ = _population()
    assert ("autobot-backend/auth_service_opt_in.py", "key") in population, "instrument check: the canonical site"
    allowed = {**_RECORDED, **_PENDING}
    new = {site: n for site, n in population.items() if site not in _CANONICAL and n > allowed.get(site, 0)}
    assert not new, (
        f"new local admin decisions: {new}. Use check_admin_permission (one gate, is_admin_role), or "
        "@service_opt_in('<caller>') for a route a service calls (#16333)."
    )


def test_the_pending_list_only_shrinks():
    population, _ = _population()
    stale = {site: (n, population.get(site, 0)) for site, n in _PENDING.items() if population.get(site, 0) < n}
    assert not stale, f"migrated sites still listed (listed, found): {stale}. Lower or delete their entries."


def test_no_new_function_named_like_an_admin_check():
    """#16333 AC: a new local ``def require_admin`` (or ``is_admin``, ``check_*admin*``) fails, even one
    built on ``is_admin_role``. The one gate is ``auth_middleware.check_admin_permission``."""
    _, defs = _population()
    assert _GATE_DEF[1] in defs.get(_GATE_DEF[0], set()), "instrument check: the one gate is named like one"
    new = {
        path: sorted(names - _RECORDED_DEFS.get(path, set()))
        for path, names in defs.items()
        if path != _GATE_DEF[0] and names - _RECORDED_DEFS.get(path, set())
    }
    assert not new, (
        f"new functions named like an admin check: {new}. Use Depends(check_admin_permission) or "
        "is_admin_role(...) inline, or record the function in _RECORDED_DEFS with its reason (#16333)."
    )


def test_recorded_admin_functions_still_exist():
    _, defs = _population()
    stale = {p: sorted(n - defs.get(p, set())) for p, n in _RECORDED_DEFS.items() if n - defs.get(p, set())}
    assert not stale, f"recorded functions that no longer exist: {stale}. Delete their entries."


def test_the_def_detector_reads_names_not_bodies():
    planted = """
def require_admin(request): return is_admin_role(request.state.role)
async def require_org_admin_access(user): ...
def is_admin(user): ...
def _is_superadmin(user): ...
def caller_is_admin(request): ...
def check_admin_rights(user): ...
def tool_admin_only(user): ...
def admin_check(): ...
"""
    assert admin_defs(planted) == {
        "require_admin",
        "require_org_admin_access",
        "is_admin",
        "_is_superadmin",
        "caller_is_admin",
        "check_admin_rights",
        "tool_admin_only",
        "admin_check",
    }
    lookalikes = "def list_admins(): ...\ndef admin_panel(): ...\ndef administrator_count(): ...\nis_admin = True"
    assert admin_defs(lookalikes) == set()


def test_the_detector_reads_code_not_prose():
    assert admin_decisions('require_role("admin", "superadmin")') == Counter({"require_role": 1})
    assert admin_decisions('if role in ("admin", "superadmin"): pass') == Counter({"literal": 1})
    assert admin_decisions("verify_internal_api_key(h)") == Counter({"key": 1})
    assert admin_decisions('"""require_role("admin") and role == "admin" in prose"""') == Counter()
    assert admin_decisions('require_role("analyst")') == Counter()
    assert admin_decisions("from x import verify_internal_api_key as ok") == Counter({"key": 1})
    assert admin_decisions('principal = {"username": "svc", "role": "admin"}') == Counter({"grant": 1})
    assert admin_decisions("if user.role == Role.ADMIN: pass") == Counter({"literal": 1})
    assert admin_decisions('principal = {"role": "service"}') == Counter()


def test_the_detector_reads_the_spellings_the_security_review_listed():
    """#16333 PR C: each spelling a second admin decision could hide behind, planted."""
    assert admin_decisions("if user.role == Role.ADMIN.value: pass") == Counter({"literal": 1})
    assert admin_decisions('if role == "Admin": pass') == Counter({"literal": 1})
    assert admin_decisions('if role.upper() == "SUPERADMIN": pass') == Counter({"literal": 1})
    assert admin_decisions('ok = role.lower().startswith("admin")') == Counter({"literal": 1})
    assert admin_decisions('_PRIVILEGED_ROLES = frozenset({"admin", "superadmin"})') == Counter({"set": 1})
    assert admin_decisions("ADMINS = (Role.ADMIN, Role.SUPERADMIN)") == Counter({"set": 1})
    assert admin_decisions('user["role"] = "admin"') == Counter({"grant": 1})
    assert admin_decisions('make_principal(name="svc", role="admin")') == Counter({"grant": 1})
    assert admin_decisions('check = getattr(auth, "verify_internal_api_key")') == Counter({"key": 1})
    assert admin_decisions("ok = hmac.compare_digest(header, internal_api_key())") == Counter({"key": 1})
    # #20787: two more spellings.
    assert admin_decisions('match role:\n    case "admin":\n        pass') == Counter({"literal": 1})
    assert admin_decisions('user.role = "admin"') == Counter({"grant": 1})


def test_the_extended_detector_leaves_lookalikes_alone():
    assert admin_decisions('_COMMON_SUBDOMAINS = ("www", "admin", "api")') == Counter()
    assert admin_decisions('router_configs = [("x", r, ["admin"], "/admin")]') == Counter()
    assert admin_decisions('ok = path.startswith("/api/admin")') == Counter()
    assert admin_decisions("ok = hmac.compare_digest(a, b)") == Counter()
    assert admin_decisions('user["name"] = "admin"') == Counter()
    assert admin_decisions('user.name = "admin"') == Counter()
    assert admin_decisions('match role:\n    case "user":\n        pass') == Counter()
