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

Two claims are checked, and the second is the one that decays:

* the payload derives ``admin`` from the key, not from the user alone
* ``APIKey.has_scope`` remains the single implementation of scope matching, so a
  second copy cannot drift from it
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from ._paths import repo_root

AUTH = repo_root() / "autobot-slm-backend" / "services" / "auth.py"
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


def test_the_payload_exposes_the_key_s_scopes() -> None:
    """A caller cannot enforce a scope it is never told about."""
    tree = ast.parse(_source(AUTH))
    func = _function(tree, "get_api_key_user")
    returns = [n for n in ast.walk(func) if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict)]

    for ret in returns:
        keys = [k.value for k in ret.value.keys if isinstance(k, ast.Constant)]
        assert "scopes" in keys, (
            "the payload does not carry `scopes`. Every route consuming this dependency would "
            "have to re-fetch the key to make a scope decision, and the ones that forget would "
            "silently authorise everything the owner can do."
        )


def test_scope_matching_has_exactly_one_implementation() -> None:
    """`has_scope` is the single source; a copy elsewhere is the drift this prevents."""
    model_src = _source(MODEL)
    assert "def has_scope" in model_src, (
        "APIKey.has_scope is gone; the guard above points at a method that no longer exists"
    )

    auth_src = _source(AUTH)
    for smell in ('"admin:*" in', "'admin:*' in", '"*" in api_key.scopes'):
        assert smell not in auth_src, (
            f"auth.py contains {smell!r}, which re-implements scope matching outside "
            "APIKey.has_scope. Two implementations of the same rule drift, and the drift is "
            "silent in the direction of more privilege."
        )
