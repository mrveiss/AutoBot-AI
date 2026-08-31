# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A package's mount-time prefix reaches the routes it mounts (#13582).

#13582 was filed as dead-constant cleanup: `_ROUTER_INCLUDE_RE` had exactly one
reference, its own definition, and the question was whether to use it or remove
it. It was missing wiring, not surplus — and finding that out turned up a second
defect standing in front of it.

`package_router_files` guarded itself with a regex matching only
`router.include_router(name)` with the call closing immediately after the name.
Any package mounting with `prefix=`, `tags=`, or through `app.` failed that
guard and returned `{}` — every route in the package dropped, with no error.
The guard sat directly ahead of a `mounted` check asking the same question at
the correct width, so it could only ever subtract.

With the guard gone those packages are found, which then exposes what the dead
constant was for: a prefix given at mount time applies to every route in the
mounted module, and nothing was reading it. Reporting those routes without it
would invent endpoints that do not exist — the failure the surrounding code
says in its own comments that it exists to prevent.

These tests build real package trees on disk and assert on the paths the
resolver returns, because both defects are about which prefix a file is served
under — something no assertion on source text can see.

#14355 moved them here with the code. They were written against the analytics
scanner's private copy of this algorithm; that copy is gone and both consumers
now call `package_router_files`, so the tests live beside the implementation
they always described. Dropping the `fastapi` importorskip they used to need is
part of the same move: this module is stdlib-only, so the coverage now runs
everywhere instead of only where the backend's dependencies are installed.
"""

from __future__ import annotations

from pathlib import Path

from autobot_shared.api_routing.router_prefixes import package_router_files


def _package(root: Path, name: str, init_body: str, modules: dict[str, str] | None = None) -> Path:
    """Write a router package whose __init__ mounts its submodules."""
    pkg = root / name
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text(init_body, encoding="utf-8")
    for module, body in (modules or {}).items():
        (pkg / f"{module}.py").write_text(body, encoding="utf-8")
    return pkg


_ROUTER_MODULE = "router = APIRouter()\n\n\n@router.get('/items')\nasync def items():\n    return []\n"


def test_a_package_mounting_with_a_prefix_is_not_dropped(tmp_path):
    """The regression. `prefix=` in the mount call used to fail the guard.

    Before the fix this returned `{}` and every route in the package vanished
    from the scan — no error, no warning, just an endpoint inventory quietly
    missing a subtree.
    """
    pkg = _package(
        tmp_path,
        "billing",
        "from fastapi import APIRouter\n"
        "from .costs import router as costs_router\n"
        "router = APIRouter()\n"
        "router.include_router(costs_router, prefix='/costs')\n",
        {"costs": _ROUTER_MODULE},
    )
    files = package_router_files(pkg, "/api/billing")
    assert pkg / "costs.py" in files, "a package mounting with a prefix was dropped entirely"


def test_the_mount_prefix_reaches_the_module_it_mounts(tmp_path):
    """What the dead constant was for.

    The prefix lives on the mount call, not on the mounted router, so it is
    invisible to `APIRouter(prefix=)` parsing. Serving these routes without it
    reports endpoints at paths nothing answers on.
    """
    pkg = _package(
        tmp_path,
        "billing",
        "from fastapi import APIRouter\n"
        "from .costs import router as costs_router\n"
        "router = APIRouter()\n"
        "router.include_router(costs_router, prefix='/costs')\n",
        {"costs": _ROUTER_MODULE},
    )
    files = package_router_files(pkg, "/api/billing")
    assert files[pkg / "costs.py"] == "/api/billing/costs"


def test_a_mount_without_a_prefix_is_unchanged(tmp_path):
    """The common case must not acquire a prefix from nowhere."""
    pkg = _package(
        tmp_path,
        "chat",
        "from fastapi import APIRouter\n"
        "from .history import router as history_router\n"
        "router = APIRouter()\n"
        "router.include_router(history_router)\n",
        {"history": _ROUTER_MODULE},
    )
    files = package_router_files(pkg, "/api/chat")
    assert files[pkg / "history.py"] == "/api/chat"


def test_each_mount_gets_its_own_prefix(tmp_path):
    """Two submodules, two different mount prefixes.

    A single package-wide prefix would give both the same answer, so this is
    what separates 'reads the mount call' from 'reads something adjacent'.
    """
    pkg = _package(
        tmp_path,
        "admin",
        "from fastapi import APIRouter\n"
        "from .users import router as users_router\n"
        "from .audit import router as audit_router\n"
        "router = APIRouter()\n"
        "router.include_router(users_router, prefix='/users')\n"
        "router.include_router(audit_router, prefix='/audit')\n",
        {"users": _ROUTER_MODULE, "audit": _ROUTER_MODULE},
    )
    files = package_router_files(pkg, "/api/admin")
    assert files[pkg / "users.py"] == "/api/admin/users"
    assert files[pkg / "audit.py"] == "/api/admin/audit"


def test_a_mount_with_tags_but_no_prefix_is_not_dropped(tmp_path):
    """`tags=` also failed the old guard, for the same reason `prefix=` did:
    the pattern required the call to close right after the router name."""
    pkg = _package(
        tmp_path,
        "voice",
        "from fastapi import APIRouter\n"
        "from .tts import router as tts_router\n"
        "router = APIRouter()\n"
        "router.include_router(tts_router, tags=['voice'])\n",
        {"tts": _ROUTER_MODULE},
    )
    files = package_router_files(pkg, "/api/voice")
    assert files[pkg / "tts.py"] == "/api/voice"


def test_a_declared_but_unmounted_module_still_serves_nothing(tmp_path):
    """Widening the guard must not widen what counts as mounted.

    An import binds a name; only `include_router` serves it. This is the
    behaviour the removed guard was nominally protecting, and it is enforced by
    the `mounted` check that was always the real gate.
    """
    pkg = _package(
        tmp_path,
        "reports",
        "from fastapi import APIRouter\n"
        "from .draft import router as draft_router\n"
        "from .live import router as live_router\n"
        "router = APIRouter()\n"
        "router.include_router(live_router, prefix='/live')\n",
        {"draft": _ROUTER_MODULE, "live": _ROUTER_MODULE},
    )
    files = package_router_files(pkg, "/api/reports")
    assert pkg / "live.py" in files
    assert pkg / "draft.py" not in files, "an imported-but-never-mounted module serves no routes"


def test_a_package_mounting_nothing_still_returns_nothing(tmp_path):
    """The empty case the removed guard shared with the `mounted` check."""
    pkg = _package(
        tmp_path,
        "empty",
        "from fastapi import APIRouter\n\nrouter = APIRouter()\n",
    )
    assert package_router_files(pkg, "/api/empty") == {}


def test_nested_subpackages_inherit_the_mount_prefix(tmp_path):
    """The recursion carries the mount prefix down.

    `package_router_files` recurses for subpackages, so a mount prefix applied
    at the wrong level compounds — the nested module lands under a path with a
    missing or duplicated segment.
    """
    parent = _package(
        tmp_path,
        "platform",
        "from fastapi import APIRouter\n"
        "from .metrics import router as metrics_router\n"
        "router = APIRouter()\n"
        "router.include_router(metrics_router, prefix='/metrics')\n",
    )
    _package(
        parent,
        "metrics",
        "from fastapi import APIRouter\n"
        "from .cpu import router as cpu_router\n"
        "router = APIRouter()\n"
        "router.include_router(cpu_router, prefix='/cpu')\n",
        {"cpu": _ROUTER_MODULE},
    )
    files = package_router_files(parent, "/api/platform")
    assert files[parent / "metrics" / "cpu.py"] == "/api/platform/metrics/cpu"
