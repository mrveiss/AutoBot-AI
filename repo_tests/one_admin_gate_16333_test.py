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
``verify_internal_api_key`` import, a ``Role.ADMIN``-style comparison, and a hand-built
``{"role": "admin"}`` principal.

Scope: ``autobot-backend``. ``autobot_shared`` holds the canonical predicate
(``auth.permissions.is_admin_role``) and the key check itself, and the SLM is a separate service
with its own admin-only gate (#20628); neither is a second gate inside this backend. The existing sites
are listed below with counts. The pending list only shrinks: PR B of #16333 moves the
``require_role`` sites, and PR C the local checks.
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
    # Membership of "admin" in a configured allowed-roles list, decided with is_admin_role.
    ("autobot-backend/services/mcp_external_bridge.py", "literal"): 1,
    # The auth-disabled (dev-only) principal; the human-decision check refuses it (#17042).
    ("autobot-backend/auth_middleware.py", "grant"): 1,
}

#: Pending migration. **Only shrinks.**
_PENDING = {
    # PR B: onto check_admin_permission.
    ("autobot-backend/api/admin_event_logs.py", "require_role"): 1,
    ("autobot-backend/api/admin_oauth_bundle_strip.py", "require_role"): 1,
    ("autobot-backend/api/admin_org_tier_column.py", "require_role"): 1,
    ("autobot-backend/api/admin_orphan_repair.py", "require_role"): 1,
    ("autobot-backend/api/admin_orphan_storage.py", "require_role"): 1,
    ("autobot-backend/api/admin_pricing.py", "require_role"): 4,
    ("autobot-backend/api/admin_retention_policies.py", "require_role"): 5,
    ("autobot-backend/api/chat_shared_links.py", "require_role"): 1,
    ("autobot-backend/api/mcp_token_admin.py", "require_role"): 3,
    ("autobot-backend/api/voice_bundle_admin.py", "require_role"): 2,
    ("autobot-backend/api/voice_bundle_user.py", "require_role"): 1,
    # PR C: local checks onto the one predicate and gate.
    ("autobot-backend/api/settings_config.py", "key"): 1,
    ("autobot-backend/api/redis_mcp/router.py", "literal"): 1,
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


def _constants(node: ast.expr) -> list[ast.Constant]:
    items = node.elts if isinstance(node, (ast.Tuple, ast.Set, ast.List)) else [node]
    return [c for c in items if isinstance(c, ast.Constant)]


_ADMIN_ATTRS = frozenset({"ADMIN", "SUPERADMIN"})


def _names_admin(node: ast.expr) -> bool:
    """``"admin"`` / ``"superadmin"``, or an attribute spelled ``ADMIN`` / ``SUPERADMIN`` (``Role.ADMIN``)."""
    if isinstance(node, (ast.Tuple, ast.Set, ast.List)):
        return any(_names_admin(e) for e in node.elts)
    if isinstance(node, ast.Constant):
        return node.value in _ADMIN
    return isinstance(node, ast.Attribute) and node.attr in _ADMIN_ATTRS


def admin_decisions(source: str) -> Counter:
    """Local admin decisions in *source*, by kind."""
    found: Counter = Counter()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and any(
            a.name == "verify_internal_api_key" and a.asname not in (None, a.name) for a in node.names
        ):
            found["key"] += 1  # an alias would hide every call from the name match below
        elif isinstance(node, ast.Dict) and any(
            isinstance(k, ast.Constant) and k.value == "role" and _names_admin(v)
            for k, v in zip(node.keys, node.values)
        ):
            found["grant"] += 1  # a hand-built admin principal, e.g. {"role": "admin"}
        elif isinstance(node, ast.Call):
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name == "require_role" and any(c.value in _ADMIN for a in node.args for c in _constants(a)):
                found["require_role"] += 1
            elif name == "verify_internal_api_key":
                found["key"] += 1
        elif isinstance(node, ast.Compare):
            if any(_names_admin(side) for side in (node.left, *node.comparators)):
                found["literal"] += 1
    return found


def _population() -> dict[tuple[str, str], int]:
    examined = REACH.examined(_ROOT)
    found: dict[tuple[str, str], int] = {}
    for rel in examined:
        try:
            counts = admin_decisions((_ROOT / rel).read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        found.update({(rel, kind): n for kind, n in counts.items()})
    REACH.completed(len(examined), _ROOT)
    return found


def test_no_new_local_admin_decision():
    population = _population()
    assert ("autobot-backend/auth_service_opt_in.py", "key") in population, "instrument check: the canonical site"
    allowed = {**_RECORDED, **_PENDING}
    new = {site: n for site, n in population.items() if site not in _CANONICAL and n > allowed.get(site, 0)}
    assert not new, (
        f"new local admin decisions: {new}. Use check_admin_permission (one gate, is_admin_role), or "
        "@service_opt_in('<caller>') for a route a service calls (#16333)."
    )


def test_the_pending_list_only_shrinks():
    population = _population()
    stale = {site: (n, population.get(site, 0)) for site, n in _PENDING.items() if population.get(site, 0) < n}
    assert not stale, f"migrated sites still listed (listed, found): {stale}. Lower or delete their entries."


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
