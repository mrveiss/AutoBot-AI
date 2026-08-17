# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One implementation of package-router resolution, two consumers (#14355).

Which submodules a registry-mounted package serves, and under which prefix, was
implemented twice: once in `autobot_shared.api_routing.router_prefixes`, reached
by `scripts/audit_api_wiring.py` and so by the **blocking** api-wiring gate, and
once as `BackendEndpointScanner._package_router_files`, which produces the
endpoint inventory a human reads to decide whether that gate is working.

Two copies of one algorithm drift. #13582 found a missing mount-prefix path in
the analytics copy and the shared copy had the identical gap; fixing one alone
would have widened the divergence. The interim guard was an equality test
between the two functions, which stopped them drifting further without making
them one thing. #14355 deleted the second copy, which is why that parity test is
gone: it had nothing left to compare.

What replaces it is the invariant the parity test was standing in for — *both
consumers resolve through the same implementation*. The first two tests assert
it by substitution rather than by reading source: replace the shared function
and each consumer's answer must change with it. A reintroduced private copy
would keep answering from itself and fail here, whatever it were named, and
however closely it were written to match.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from api.codebase_analytics.api_endpoint_scanner import (  # noqa: E402
    BackendEndpointScanner,
)
from autobot_shared.api_routing import router_prefixes as routing  # noqa: E402

#: A registry entry naming a package, in the shape both consumers accept.
_ENTRY = ("llc.api", "")


def _backend_tree(tmp_path: Path, package_prefix: str = "/llc") -> Path:
    """A minimal backend holding one registry-mounted router package.

    The `api/` directory is what `find_backend_dir` looks for; the routes under
    test deliberately live outside it, because resolving those is the whole job
    of the code under test.
    """
    (tmp_path / "api").mkdir(parents=True, exist_ok=True)
    package = tmp_path / "llc" / "api"
    package.mkdir(parents=True)
    (package / "costs.py").write_text("router = APIRouter(prefix='/costs')\n", encoding="utf-8")
    (package / "__init__.py").write_text(
        f"router = APIRouter(prefix='{package_prefix}')\n"
        "from .costs import router as costs_router\n"
        "router.include_router(costs_router)\n",
        encoding="utf-8",
    )
    return package


def _analytics_view(tmp_path: Path) -> dict[Path, str]:
    """What the analytics endpoint inventory believes the package serves."""
    scanner = BackendEndpointScanner(project_root=tmp_path)
    scanner._module_prefix_map = {_ENTRY[0]: _ENTRY[1]}
    return scanner._registry_router_files()


def _gate_view(tmp_path: Path) -> dict[Path, str]:
    """What the blocking api-wiring gate believes the package serves."""
    return routing.resolve_registry_targets(tmp_path, [_ENTRY])


def test_the_analytics_scanner_resolves_packages_through_the_shared_implementation(tmp_path, monkeypatch):
    """Substitution, not source reading: swap the shared function, and the
    scanner's answer must move with it.

    A scanner carrying its own copy again — under any name — answers from that
    copy and this assertion fails.
    """
    package = _backend_tree(tmp_path)
    substituted = {package / "substituted.py": "/only-the-shared-implementation-produces-this"}
    monkeypatch.setattr(routing, "package_router_files", lambda pkg, registry_prefix: dict(substituted))

    assert _analytics_view(tmp_path) == substituted


def test_the_api_wiring_gate_resolves_packages_through_the_same_implementation(tmp_path, monkeypatch):
    """The other consumer, asserted the same way.

    Without this, the scanner could be delegating to a shared function the gate
    had stopped using — one implementation by name, two by reach.
    """
    package = _backend_tree(tmp_path)
    substituted = {package / "substituted.py": "/only-the-shared-implementation-produces-this"}
    monkeypatch.setattr(routing, "package_router_files", lambda pkg, registry_prefix: dict(substituted))

    assert _gate_view(tmp_path) == substituted


def test_both_consumers_report_the_same_mapping(tmp_path):
    """The parity the deleted test asserted, now between the real consumers.

    The second assertion is the point of the first: two views that are both
    empty agree perfectly, and an empty result reads as a clean result.
    """
    package = _backend_tree(tmp_path)

    analytics, gate = _analytics_view(tmp_path), _gate_view(tmp_path)

    assert analytics == gate
    assert gate == {package / "costs.py": "/llc"}


def test_a_trailing_slash_on_the_package_prefix_is_normalised_for_both(tmp_path):
    """The divergence #14355 had to settle before the copies could merge.

    The gate stripped the trailing slash; the analytics copy did not, so a
    package declaring `'/llc/'` was reported at `/llc//costs` — a path nothing
    answers on, an invented endpoint of exactly the kind this resolver's own
    comments say it exists to avoid. FastAPI rejects such a prefix outright ("A
    path prefix must not end with '/'"), so the stripped form is the only one
    that can describe a served route.
    """
    package = _backend_tree(tmp_path, package_prefix="/llc/")

    analytics, gate = _analytics_view(tmp_path), _gate_view(tmp_path)

    assert analytics == gate
    assert gate == {package / "costs.py": "/llc"}


def test_a_file_level_prefix_is_normalised_the_same_way(tmp_path):
    """The scanner's other reader of the same grammar, reconciled with it.

    `_scan_file` applies this prefix to every route in the file, so leaving it
    unnormalised here would reintroduce the doubled separator one level down
    from where it was just removed.
    """
    (tmp_path / "api").mkdir(parents=True, exist_ok=True)
    scanner = BackendEndpointScanner(project_root=tmp_path)

    assert scanner._get_file_router_prefix("router = APIRouter(prefix='/llc/')\n") == "/llc"
    assert scanner._get_file_router_prefix("x = 1\n") == ""
