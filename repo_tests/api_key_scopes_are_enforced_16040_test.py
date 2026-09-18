# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An API key's authority is the KEY's, never its owner's (#16040).

``get_api_key_user`` validated a key and then returned
``{"admin": user.is_platform_admin, ...}`` without ever reading
``api_key.scopes``. A key created with narrow scopes therefore carried its
owner's full authority — platform admin included — while the console that issued
it displayed the narrow scopes. **The scope a person selected and the authority
they granted were two different things, and nothing in the UI showed which one
was real.**

**It was never exploitable, and that is the reason to guard it rather than a
reason not to.** The dependency has no callers: at the time of writing, the only
references to ``get_api_key_user`` in the repository are its own definition and a
docstring mentioning it. No route authenticates by API key through it. An unwired
dependency and a wired one are indistinguishable from the function body, so the
first route to adopt this would have inherited a privilege escalation by
adoption rather than by anyone deciding to — and the diff that adopted it would
have looked like a one-line dependency change.

That distinction is why this file asserts the *source* rather than exercising a
route. There is no route to exercise. A behavioural test would have to wire one
up, and a test that invents its own caller proves the caller it invented, not the
ones someone will write later.

The claims checked:

* the payload derives ``admin`` from the key, not from the user alone
* the payload carries ``api_key_id``, ``role`` and ``scopes``, the three things the
  permission decision reads
* ``APIKey.has_scope`` remains the single implementation of scope matching, so a
  second copy cannot drift from it
* a key is authenticated in one place, and a route reaches that place only by
  declaring the permission it requires (``require_key_permission``), so no
  key-reachable route can go undeclared. Which routes accept keys is #16294's
  decision; this holds whatever it decides.

The HTTP behaviour of that declaration (403 for a key lacking the scope, 401 for no
key) is tested on a test route in
``autobot-slm-backend/tests/api/test_api_key_route_scope_16040.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from ._paths import repo_root

SLM = repo_root() / "autobot-slm-backend"
AUTH = SLM / "services" / "auth.py"
MODEL = repo_root() / "autobot_shared" / "user_management" / "models" / "api_key.py"


def _source(path: Path) -> str:
    if not path.exists():
        pytest.skip(f"{path} not present in this checkout")
    return path.read_text(encoding="utf-8")


def _function(tree: ast.Module, name: str) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    pytest.fail(f"{name}() not found — it was renamed or removed; update this guard deliberately")


def test_admin_is_not_taken_from_the_user_alone() -> None:
    """`admin` must depend on the key, or a narrow key carries full authority."""
    tree = ast.parse(_source(AUTH))
    func = _function(tree, "get_api_key_user")

    returns = [n for n in ast.walk(func) if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict)]
    assert returns, "get_api_key_user no longer returns a dict literal; re-derive this guard"

    for ret in returns:
        payload = ret.value
        keys = [k.value for k in payload.keys if isinstance(k, ast.Constant)]
        assert "admin" in keys, "the payload no longer carries `admin`; re-derive this guard"
        admin_expr = payload.values[keys.index("admin")]
        rendered = ast.unparse(admin_expr)

        assert "api_key" in rendered, (
            "get_api_key_user derives `admin` without consulting the key: "
            f"admin = {rendered}. A key's authority must be the key's, not its owner's — "
            "otherwise a scope-narrowed key silently carries platform admin while the UI "
            "that issued it shows narrow scopes."
        )
        assert "has_scope" in rendered, (
            f"`admin` is derived as {rendered}, which does not go through APIKey.has_scope. "
            "Scope matching (exact, wildcard, global admin) has one implementation; a second "
            "one here would drift from it silently."
        )


#: What ``permission_allowed`` reads from a key caller's payload, and what goes wrong without it.
_PAYLOAD_CLAIMS = {
    "api_key_id": "permission_allowed applies the key half only when `api_key_id` is present. Without "
    "it a key is judged as a session: its owner's full role, whatever its scopes (#16294, 90's review of #16298).",
    "role": "the role half of the intersection reads `role`. Without it the legacy `admin` flag decides, "
    "and a plain user's key would be judged by a flag instead of its owner's role.",
    "scopes": "a caller cannot enforce a scope it is never told about. Every route consuming this "
    "dependency would have to re-fetch the key, and the ones that forget would authorise everything "
    "the owner can do.",
}


@pytest.mark.parametrize("claim", sorted(_PAYLOAD_CLAIMS))
def test_the_payload_carries_what_the_decision_reads(claim: str) -> None:
    """#16294: this must hold before any route accepts a key."""
    tree = ast.parse(_source(AUTH))
    func = _function(tree, "get_api_key_user")
    returns = [n for n in ast.walk(func) if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict)]
    assert returns, "get_api_key_user no longer returns a dict literal; re-derive this guard"

    for ret in returns:
        keys = [k.value for k in ret.value.keys if isinstance(k, ast.Constant)]
        assert claim in keys, f"the payload does not carry `{claim}`: {_PAYLOAD_CLAIMS[claim]}"


def test_scope_matching_has_exactly_one_implementation() -> None:
    """`has_scope` is the single source; a copy elsewhere is the drift this prevents."""
    model_src = _source(MODEL)
    assert (
        "def has_scope" in model_src
    ), "APIKey.has_scope is gone; the guard above points at a method that no longer exists"

    auth_src = _source(AUTH)
    for smell in ('"admin:*" in', "'admin:*' in", '"*" in api_key.scopes'):
        assert smell not in auth_src, (
            f"auth.py contains {smell!r}, which re-implements scope matching outside "
            "APIKey.has_scope. Two implementations of the same rule drift, and the drift is "
            "silent in the direction of more privilege."
        )


def _is_test_module(relative: Path) -> bool:
    name = relative.name
    return name.endswith("_test.py") or name.startswith("test_") or name == "conftest.py" or "tests" in relative.parts


def _slm_modules() -> list[Path]:
    """Every production module of the SLM backend. Fails, never passes, on an empty scan."""
    if not SLM.is_dir():
        pytest.skip(f"{SLM} not present in this checkout")
    modules = [p for p in sorted(SLM.rglob("*.py")) if not _is_test_module(p.relative_to(SLM))]
    routes = [p for p in modules if p.relative_to(SLM).parts[0] == "api"]
    assert len(routes) > 10, f"scanned {len(routes)} SLM route modules; this guard would pass on an empty set"
    assert AUTH in modules, "services/auth.py was not scanned; re-derive this guard"
    return modules


def _references(tree: ast.Module, name: str) -> list[str | None]:
    """The enclosing top-level function of every use of *name*, or None at module or class level.

    A use is a name, an attribute, an import of it (an alias would otherwise hide one),
    or a string that is exactly the name (``getattr(auth, "get_api_key_user")``). A
    docstring that mentions the name is not a use: it only contains it.
    """
    found: list[str | None] = []

    def visit(node: ast.AST, owner: str | None) -> None:
        for child in ast.iter_child_nodes(node):
            is_function = isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            if (isinstance(child, ast.Name) and child.id == name) or (
                isinstance(child, ast.Attribute) and child.attr == name
            ):
                found.append(owner)
            if isinstance(child, ast.ImportFrom) and any(alias.name == name for alias in child.names):
                found.append(owner)
            if isinstance(child, ast.Constant) and child.value == name:
                found.append(owner)
            visit(child, child.name if is_function and owner is None else owner)

    visit(tree, None)
    return found


def _uses_outside(name: str, allowed_owner: str) -> list[str]:
    """Every use of *name* in the SLM backend except inside ``services/auth.py``'s *allowed_owner*."""
    offenders = []
    for path in _slm_modules():
        for owner in _references(ast.parse(path.read_text(encoding="utf-8")), name):
            if not (path == AUTH and owner == allowed_owner):
                offenders.append(f"{path.relative_to(SLM)} ({owner or 'module or class level'})")
    return offenders


def test_a_key_is_authenticated_in_one_place() -> None:
    """Only ``get_api_key_user`` validates a key, so every key caller gets the key's authority, not its owner's."""
    offenders = _uses_outside("validate_key", allowed_owner="get_api_key_user")

    assert offenders == [], (
        f"validate_key is called outside get_api_key_user: {offenders}. A second place that "
        "authenticates a key would build its own payload, and nothing makes it carry the key's "
        "scopes or api_key_id, so the key would act with its owner's full authority."
    )


def test_a_route_reaches_a_key_only_by_declaring_the_permission_it_requires() -> None:
    """#16040 AC4's mechanism: no key-reachable route can go undeclared.

    ``require_key_permission(permission)`` runs ``get_api_key_user`` and then answers
    403 unless the key's scopes, met with its owner's role, carry *permission*. A route
    or router that depended on ``get_api_key_user`` directly would authenticate the key
    and then check nothing.
    """
    offenders = _uses_outside("get_api_key_user", allowed_owner="require_key_permission")

    assert offenders == [], (
        f"get_api_key_user is used outside require_key_permission: {offenders}. Depend on "
        "require_key_permission(Permission.X) instead, so the route declares what the key must carry."
    )
