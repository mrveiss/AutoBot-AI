# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Every route an AutoBot app really registers, read from the real router objects (#17325, #19033).

Run as ``python repo_tests/_dump_real_routes.py backend|slm <repo-root>`` it prints one JSON document on stdout:
``{"registrations": N, "routes": [[method, path, site], ...], "unrecoverable": [...]}``, plus
``"optional_failed"``: every configured optional router the backend registry loader swallowed (always empty
for the SLM, whose ``main.py`` imports its routers unconditionally).

It is a script, not an import, because the two apps cannot share a process: both ship top-level ``api``,
``config`` and ``services`` packages. The caller (``no_duplicate_route_registration_16908_test.py``) runs it
once per app in a child interpreter, so importing a backend leaves nothing behind in the test process. The caller
passes the root it got from ``repo_tests._paths.repo_root()``; the script never re-derives it (#15925).

* backend: the two loader calls ``app_factory.py`` mounts from, at ``/api{prefix}`` as it mounts them.
* slm: the ``app`` ``main.py`` builds, whose ``include_router`` calls run at import.

Both are walked with ``autobot_shared.api_routing.router_routes.effective_routes``, the one route traversal.
Design from commit ``f4e2d6badb`` (#16908), which built the backend half and never landed.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any


def registered_routes(entries: list[tuple[Any, str, Any, str]]) -> tuple[list[list[str]], list[str]]:
    """``(routes, unrecoverable)`` for registry tuples ``(router, prefix, tags, name)``, mounted at ``/api``.

    ``app_factory.py`` does ``app.include_router(router, prefix=f"/api{prefix}")``; this applies the same prefix to
    ``effective_routes(router)``. A route whose full path could not be recovered is listed, never dropped.
    """
    from autobot_shared.api_routing.router_routes import effective_routes

    routes: list[list[str]] = []
    unrecoverable: list[str] = []
    for router, prefix, _tags, name in entries:
        for mounted in effective_routes(router):
            if not mounted.prefix_complete:
                unrecoverable.append(f"{name}:{mounted.path}")
                continue
            routes.extend(_rows(mounted, f"/api{prefix}{mounted.path}", name))
    return routes, unrecoverable


def _rows(mounted: Any, full_path: str, name: str) -> list[list[str]]:
    endpoint = getattr(mounted.route, "endpoint", None)
    site = f"{name}:{getattr(endpoint, '__module__', '?')}.{getattr(endpoint, '__qualname__', '?')}"
    return [[method, full_path, site] for method in sorted(mounted.methods or {"WEBSOCKET"})]


def _dump_backend(root: Path) -> dict[str, Any]:
    sys.path.insert(0, str(root / "autobot-backend"))
    from initialization.router_registry.core_routers import load_core_routers
    from initialization.router_registry.loader import get_load_results
    from initialization.routers import load_optional_routers

    entries = [*load_core_routers(), *load_optional_routers()]
    routes, unrecoverable = registered_routes(entries)
    failed = [f"{r['group']}:{r['name']}: {r['error']}" for r in get_load_results() if not r["loaded"]]
    return {"registrations": len(entries), "routes": routes, "unrecoverable": unrecoverable, "optional_failed": failed}


def _dump_slm(root: Path) -> dict[str, Any]:
    from autobot_shared.api_routing.router_routes import effective_routes

    # Throwaway keys: config.py would otherwise write data/.slm_keys into the checkout at import.
    os.environ.setdefault("SLM_SECRET_KEY", "route-dump-not-a-secret")
    os.environ.setdefault("SLM_ENCRYPTION_KEY", "route-dump-not-a-secret")
    os.chdir(root / "autobot-slm-backend")
    sys.path.insert(0, os.getcwd())
    import main

    routes: list[list[str]] = []
    unrecoverable: list[str] = []
    for mounted in effective_routes(main.app.router):
        if mounted.prefix_complete:
            routes.extend(_rows(mounted, mounted.path, "slm"))
        else:
            unrecoverable.append(mounted.path)
    # main.py includes every router unconditionally: an import failure fails the dump, so nothing is swallowed.
    registrations = len(main.app.router.routes)
    return {"registrations": registrations, "routes": routes, "unrecoverable": unrecoverable, "optional_failed": []}


def main_cli(argv: list[str]) -> int:
    root = Path(argv[2])
    sys.path.insert(0, str(root))
    logging.disable(logging.CRITICAL)
    dump = {"backend": _dump_backend, "slm": _dump_slm}[argv[1]](root)
    sys.stdout.write("\n" + json.dumps(dump) + "\n")  # the last line is the document; imports may print before it
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli(sys.argv))
