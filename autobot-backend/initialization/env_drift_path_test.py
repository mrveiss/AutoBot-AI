# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The startup drift check must read THIS backend's .env (#12782).

`check_env_drift()` with no argument walks up from `autobot_shared/` looking for
a sibling `.env`. That finds the repo root during development, but not on a
deployed host: `autobot_shared` sits at `<root>/autobot_shared` while the env
lives at `<root>/autobot-backend/.env`. The walk found nothing, fell back to
`<root>/.env` — which does not exist — and every SSOT key was reported missing:

    env drift: 194 drifted, 0 unknown, (194 SSOT keys, 0 .env keys)

against a file that actually held 93 keys. The `0 .env keys` was the tell: not
194 real drifts, but a comparison against nothing.

`lifespan.py` is always `<backend-root>/initialization/lifespan.py`, so
`parents[1] / ".env"` names the right file in both layouts. These tests pin that
the call site passes it explicitly rather than letting the resolver guess.
"""

from __future__ import annotations

import ast
from pathlib import Path

_LIFESPAN = Path(__file__).resolve().parent / "lifespan.py"


def _check_env_drift_node() -> ast.AsyncFunctionDef:
    """Return the `_check_env_drift` AST node, so assertions stay scoped."""
    tree = ast.parse(_LIFESPAN.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_check_env_drift":
            return node
    raise AssertionError("_check_env_drift not found in lifespan.py")


def _check_env_drift_source() -> str:
    src = _LIFESPAN.read_text(encoding="utf-8")
    return ast.get_source_segment(src, _check_env_drift_node()) or ""


def _drift_calls() -> list[ast.Call]:
    """Every call to check_env_drift inside the startup hook."""
    return [
        n
        for n in ast.walk(_check_env_drift_node())
        if isinstance(n, ast.Call)
        and getattr(n.func, "id", getattr(n.func, "attr", None)) == "check_env_drift"
    ]


def test_drift_check_passes_an_explicit_env_path() -> None:
    """A bare check_env_drift() re-introduces the wrong-file comparison.

    Asserted on the AST call node rather than a substring: the function's own
    signature contains the text ``check_env_drift()``, which made a naive
    substring check fail against correct code.
    """
    calls = _drift_calls()

    assert calls, "the drift check must still be invoked"
    for call in calls:
        assert call.args or call.keywords, (
            "check_env_drift() with no argument lets the resolver guess, which on "
            "a deployed host compares against a nonexistent <root>/.env and "
            "reports every SSOT key as drifted (#12782)"
        )


def test_env_path_is_derived_from_this_module_not_hardcoded() -> None:
    """It must work in both the repo and the deployed layout."""
    src = _check_env_drift_source()

    assert "parents[1]" in src, (
        "derive the backend root from __file__ — this module is always "
        "<backend-root>/initialization/lifespan.py"
    )
    assert "/opt/autobot" not in src, "must not hardcode a deployment path"


def test_parents1_names_the_backend_env_in_this_checkout() -> None:
    """Behavioural check: the expression resolves to the backend's own .env."""
    resolved = _LIFESPAN.parents[1] / ".env"

    assert resolved.parent == _LIFESPAN.parents[1]
    assert resolved.name == ".env"
    assert resolved.parent.name == "autobot-backend", (
        f"expected the backend root, got {resolved.parent} — the parents[] index is wrong"
    )
