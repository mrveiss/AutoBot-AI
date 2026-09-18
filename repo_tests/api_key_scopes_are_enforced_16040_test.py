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
import os
from pathlib import Path

import pytest

from ._paths import repo_root

SLM = repo_root() / "autobot-slm-backend"
AUTH = SLM / "services" / "auth.py"
KEY_MIDDLEWARE = SLM / "middleware" / "api_key_allow_list.py"
BACKEND = repo_root() / "autobot-backend"
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


def _production_modules(root: Path) -> list[Path]:
    """Every non-test ``.py`` under *root*. Symlinked directories are not followed: a
    local ``backend -> .`` link would otherwise recurse."""
    if not root.is_dir():
        pytest.skip(f"{root} not present in this checkout")
    found = []
    for directory, subdirs, files in os.walk(root):
        subdirs[:] = [d for d in subdirs if not d.startswith((".", "__pycache__", "node_modules"))]
        found += [Path(directory) / f for f in files if f.endswith(".py")]
    return sorted(p for p in found if not _is_test_module(p.relative_to(root)))


def _slm_modules() -> list[Path]:
    """Every production module of the SLM backend. Fails, never passes, on an empty scan."""
    modules = _production_modules(SLM)
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


# --- #16294: the owner's ruling (2026-09-18) --------------------------------------
#
# The SLM accepts user API keys only on an explicit allow-list of integration routes,
# each declaring its permission through require_key_permission; the main backend
# accepts none. The list ships empty: no SLM route was found that an integration calls
# with a user key (#16294).

#: The SLM key allow-list, as (module, enclosing function) of each require_key_permission
#: use. Adding a member is an owner decision on #16294: record it there, then here.
_KEY_ALLOW_LIST: frozenset = frozenset()


def test_the_key_allow_list_is_exactly_the_owners() -> None:
    """A route joins the list by declaring ``require_key_permission``; this pins that list."""
    members = {
        (str(path.relative_to(SLM)), owner)
        for path in _slm_modules()
        if path != AUTH
        for owner in _references(ast.parse(path.read_text(encoding="utf-8")), "require_key_permission")
    }

    assert members == set(_KEY_ALLOW_LIST), (
        f"the SLM key allow-list is {sorted(members, key=str)}, but the owner's list is "
        f"{sorted(_KEY_ALLOW_LIST, key=str)}. A route that accepts a key is an owner decision (#16294)."
    )


def _is_key_header(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.lower() == "x-api-key"


def _is_header_call(node: ast.AST) -> bool:
    func = getattr(node, "func", None)
    return isinstance(node, ast.Call) and getattr(func, "id", getattr(func, "attr", None)) == "Header"


def _key_header_reads(tree: ast.Module) -> list[int]:
    """Lines that read the X-API-Key request header, in any of the ways a route can.

    - ``Header(..., alias="X-API-Key")``;
    - a ``Header()`` parameter named ``x_api_key``, which FastAPI maps to that header;
    - ``<x>.headers.get("X-API-Key")`` and ``<x>.headers["X-API-Key"]``.

    Building an outbound request (``headers={"X-API-Key": k}``) is not a read.
    """
    lines = []
    for node in ast.walk(tree):
        if _is_header_call(node) and any(kw.arg == "alias" and _is_key_header(kw.value) for kw in node.keywords):
            lines.append(node.lineno)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args.args + node.args.kwonlyargs
            defaults = [None] * (len(node.args.args) - len(node.args.defaults)) + node.args.defaults
            defaults += node.args.kw_defaults
            for arg, default in zip(args, defaults):
                if arg.arg == "x_api_key" and default is not None and _is_header_call(default):
                    lines.append(arg.lineno)
        on_headers = getattr(getattr(node, "func", None), "value", None) if isinstance(node, ast.Call) else None
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "get" and node.args:
            if getattr(on_headers, "attr", None) == "headers" and _is_key_header(node.args[0]):
                lines.append(node.lineno)
        if isinstance(node, ast.Subscript) and getattr(node.value, "attr", None) == "headers":
            if _is_key_header(node.slice):
                lines.append(node.lineno)
    return lines


@pytest.mark.parametrize(
    ("source", "flagged"),
    [
        ('def r(k: str = Header(None, alias="X-API-Key")): ...', True),
        ("def r(x_api_key: str = Header(None)): ...", True),
        ('def r(request): return request.headers.get("x-api-key")', True),
        ('def r(request): return request.headers["X-API-Key"]', True),
        ('httpx.get(url, headers={"X-API-Key": key})', False),
        ('BLOCKED_HEADERS = ["x-api-key"]', False),
        ('def r(request): return request.headers.get("Authorization")', False),
        ('header = config.get("header", "X-Api-Key")', False),
    ],
    ids=["alias", "x_api_key param", "headers.get", "headers[]", "outbound", "a list", "other header", "config"],
)
def test_the_header_detector_finds_reads_and_only_reads(source: str, flagged: bool) -> None:
    """Negative and positive controls for the two guards below."""
    assert bool(_key_header_reads(ast.parse(source))) is flagged


def test_the_slm_reads_the_key_header_only_where_keys_are_handled() -> None:
    """A route that read X-API-Key itself would authenticate a key without naming either guarded symbol.

    The one dependency that authenticates a key (``services/auth.py``) and the middleware
    that refuses keys off the list are the only places the header may be named at all,
    in any spelling, including a constant that a later ``.get(NAME)`` would use.
    """
    offenders = []
    for path in _slm_modules():
        if path in (AUTH, KEY_MIDDLEWARE):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        named = [n.lineno for n in ast.walk(tree) if _is_key_header(n)]
        offenders += [f"{path.relative_to(SLM)}:{line}" for line in sorted(set(named + _key_header_reads(tree)))]

    assert offenders == [], f"X-API-Key is read or named outside the key handling: {offenders}"


#: The LLC agent-key credential: a different key, table (``llc_agent_api_keys``) and header
#: (``Authorization: Bearer``), validated by the LLC agent middleware. Not a user API key.
_LLC_AGENT_KEY = BACKEND / "llc" / "middleware" / "agent_auth.py"
#: The user API-key table's model, re-exported for the backend's schema metadata only.
_KEY_MODEL_SHIM = BACKEND / "user_management" / "models"


def test_the_main_backend_accepts_no_user_api_key() -> None:
    """#16294: the main backend accepts no user API key until a named integration needs one.

    It may not read the X-API-Key header, validate a key (``validate_key``) except the
    named LLC agent-key exemption, or look up the user API-key table (``APIKey``,
    ``APIKeyService``) outside the model shim.
    """
    modules = _production_modules(BACKEND)
    assert len(modules) > 500, f"scanned {len(modules)} backend modules; this guard would pass on an empty set"
    assert _LLC_AGENT_KEY in modules, "the named LLC exemption was not scanned; re-derive this guard"

    offenders = []
    for path in modules:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        where = str(path.relative_to(BACKEND))
        offenders += [f"{where}:{line} reads X-API-Key" for line in _key_header_reads(tree)]
        if path != _LLC_AGENT_KEY and _references(tree, "validate_key"):
            offenders.append(f"{where} validates a key")
        if _KEY_MODEL_SHIM not in path.parents and (_references(tree, "APIKey") or _references(tree, "APIKeyService")):
            offenders.append(f"{where} uses the user API-key table")

    assert offenders == [], f"the main backend accepts user API keys (#16294 rules it accepts none): {offenders}"
