# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Dependencies come from declared roles, never from detected ones (#14859).

A vnc + slm-agent node contaminated by #14513 detects `backend`, `celery`,
`frontend`, `scheduler`, `slm-backend` and `slm-frontend` — the residue tracked
in #14667. Resolved from the declared-plus-detected union it was handed
`nodejs` and `postgresql` on top of what it actually needs, for roles it never
declared.

`vnc` genuinely requires `nginx` and `python_interpreter`, so those are correct and are
NOT what this fixes. (I first read this as nginx being the intruder, from a
truncated view of the dependency map. It is not: nginx failing to start on that
node is a missing-certificate problem, tracked under #14861.)

Detection legitimately drives plays: a node running redis that nobody declared
still needs the redis plays to reach it. Installing OS packages and enabling
services is a different act — that is provisioning a role, not reconciling one
that is already running.

The dependency map is read from source rather than imported: conftest does not
real-load `role_registry` (it pulls SQLAlchemy, above the dependency-light bar
`_REAL_SERVICE_MODULES` holds to), so an import resolves to a MagicMock or the
real module depending on shard order — and a MagicMock iterates as empty, which
would make every assertion here pass while checking nothing (#14307).
"""

from __future__ import annotations

import ast
from pathlib import Path

_SLM_ROOT = Path(__file__).resolve().parents[2]
_REGISTRY = _SLM_ROOT / "services" / "role_registry.py"
_WIZARD = _SLM_ROOT / "api" / "setup_wizard.py"

#: The exact shape observed on b9a29e04 when phase 7 failed.
_DECLARED = ["vnc", "slm-agent"]
_DETECTED = [
    "slm-backend",
    "slm-frontend",
    "slm-database",
    "slm-monitoring",
    "backend",
    "celery",
    "scheduler",
    "frontend",
    "redis",
    "chromadb",
    "autobot-llm-cpu",
    "autobot-llm-gpu",
    "vnc",
    "autobot_shared",
    "slm-agent",
]


def _role_dependencies() -> dict:
    """`ROLE_DEPENDENCIES` read from source, without importing role_registry."""
    src = _REGISTRY.read_text(encoding="utf-8")
    for node in ast.parse(src).body:
        target = None
        if isinstance(node, ast.AnnAssign):
            target = getattr(node.target, "id", None)
        elif isinstance(node, ast.Assign) and node.targets:
            target = getattr(node.targets[0], "id", None)
        if target == "ROLE_DEPENDENCIES":
            return ast.literal_eval(node.value)
    raise AssertionError("ROLE_DEPENDENCIES not found — this guard would pass vacuously")


def _resolve(roles) -> set[str]:
    deps = _role_dependencies()
    out: set[str] = set()
    for role in roles:
        out.update(deps.get(role, []))
    return out


def test_the_contaminated_node_gets_only_what_it_declares() -> None:
    """The regression: two packages were installed for roles it never declared."""
    declared = _resolve(_DECLARED)
    union = _resolve(set(_DECLARED) | set(_DETECTED))

    assert declared == {
        "nginx",
        "python_interpreter",
    }, f"vnc + slm-agent should resolve to exactly vnc's own dependencies; got {sorted(declared)}"
    unwanted = union - declared
    assert unwanted, "the union no longer differs from declared — this test's premise is stale"
    assert unwanted == {"nodejs", "postgresql"}, f"the packages detection would add have changed: {sorted(unwanted)}"


def test_vnc_really_does_need_nginx() -> None:
    """Guards the correction, not just the fix.

    The first diagnosis of #14859 claimed a vnc node needed nothing at all, from
    a truncated read of the dependency map. If someone repeats that reasoning,
    this says plainly that `nginx` belongs to `vnc` and removing it is a
    different change from the one #14859 made.
    """
    assert set(_role_dependencies().get("vnc", [])) == {
        "python_interpreter",
        "nginx",
    }, "vnc's dependencies changed — #14859's fix and its issue text both assume nginx is legitimate here"


def test_a_declared_backend_still_gets_its_packages() -> None:
    """The fix must not stop real roles being provisioned."""
    resolved = _resolve(["backend"])
    assert {"python_interpreter", "nginx"} <= resolved, f"a declared backend lost its dependencies: {sorted(resolved)}"


def test_the_wizard_resolves_dependencies_from_the_declared_hostvar() -> None:
    """Asserted on the source, because the seam is a hostvar name.

    Executing this path needs a database and a full inventory build; what is
    load-bearing is which of the two hostvars the loop reads, and that is
    visible without either.

    Only the INNERMOST matching loop counts. `ast.walk` also reports every
    enclosing loop — the `for node in db_nodes:` wrapper contains the
    dependency loop, so a naive search "finds" it iterating `db_nodes` and
    fails on a correct file. That is exactly what happened here on the first
    attempt.
    """
    src = _WIZARD.read_text(encoding="utf-8")
    tree = ast.parse(src)

    def resolves_dependencies(node: ast.AST) -> bool:
        return any(
            isinstance(c, ast.Call)
            and isinstance(c.func, ast.Attribute)
            and c.func.attr == "get"
            and isinstance(c.func.value, ast.Name)
            and c.func.value.id == "ROLE_DEPENDENCIES"
            for c in ast.walk(node)
        )

    candidates = [n for n in ast.walk(tree) if isinstance(n, ast.For) and resolves_dependencies(n)]
    assert candidates, "no loop resolves ROLE_DEPENDENCIES — this guard would pass vacuously"

    # Drop any loop that merely encloses another matching loop.
    innermost = [
        loop
        for loop in candidates
        if not any(
            other is not loop and resolves_dependencies(other) for other in ast.walk(loop) if isinstance(other, ast.For)
        )
    ]
    assert len(innermost) == 1, f"expected exactly one dependency loop, found {len(innermost)}"

    iterated = ast.unparse(innermost[0].iter)
    assert "declared" in iterated, (
        f"dependencies are resolved from {iterated!r}, which is not the declared-roles hostvar — "
        "a contaminated node would be provisioned for roles it never declared (#14859)"
    )
