# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The two `_package_router_files` implementations must agree (#13582).

The same algorithm — which submodules a registry-mounted package serves, and
under which prefix — exists twice:

* `autobot_shared.api_routing.router_prefixes._package_router_files`, reached by
  `scripts/audit_api_wiring.py`, which backs the **blocking** api-wiring gate.
* `BackendEndpointScanner._package_router_files`, which produces the codebase
  analytics endpoint inventory.

A fork here is not a tidiness problem. The gate decides whether a PR may merge
and the report tells a human what the API serves; when they disagree, one of
them is wrong about the shape of the API and nothing says which. #13582 fixed a
missing mount-prefix path in the analytics copy, which would have widened an
existing divergence had the shared copy not been fixed with it.

So the guard is equality between them, not a restatement of either one's
expected output. Asserting each separately is what allowed them to drift in the
first place: both had tests, and both passed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from api.codebase_analytics.api_endpoint_scanner import (  # noqa: E402
    BackendEndpointScanner,
)
from autobot_shared.api_routing.router_prefixes import (  # noqa: E402
    _package_router_files as shared_package_router_files,
)

_ROUTER_MODULE = "router = APIRouter()\n\n\n@router.get('/items')\nasync def items():\n    return []\n"


def _write(root: Path, name: str, init_body: str, modules: dict[str, str] | None = None) -> Path:
    pkg = root / name
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text(init_body, encoding="utf-8")
    for module, body in (modules or {}).items():
        (pkg / f"{module}.py").write_text(body, encoding="utf-8")
    return pkg


def _both(tmp_path: Path, pkg: Path, registry_prefix: str) -> tuple[dict, dict]:
    (tmp_path / "api").mkdir(parents=True, exist_ok=True)
    scanner = BackendEndpointScanner(project_root=tmp_path)
    return (
        scanner._package_router_files(pkg, registry_prefix),
        shared_package_router_files(pkg, registry_prefix),
    )


_CASES = {
    "plain mount": (
        "from fastapi import APIRouter\n"
        "from .costs import router as costs_router\n"
        "router = APIRouter()\n"
        "router.include_router(costs_router)\n",
        {"costs": _ROUTER_MODULE},
    ),
    "mount with a prefix": (
        "from fastapi import APIRouter\n"
        "from .costs import router as costs_router\n"
        "router = APIRouter()\n"
        "router.include_router(costs_router, prefix='/costs')\n",
        {"costs": _ROUTER_MODULE},
    ),
    "mount with tags only": (
        "from fastapi import APIRouter\n"
        "from .tts import router as tts_router\n"
        "router = APIRouter()\n"
        "router.include_router(tts_router, tags=['voice'])\n",
        {"tts": _ROUTER_MODULE},
    ),
    "two mounts, two prefixes": (
        "from fastapi import APIRouter\n"
        "from .users import router as users_router\n"
        "from .audit import router as audit_router\n"
        "router = APIRouter()\n"
        "router.include_router(users_router, prefix='/users')\n"
        "router.include_router(audit_router, prefix='/audit')\n",
        {"users": _ROUTER_MODULE, "audit": _ROUTER_MODULE},
    ),
    "declared but not mounted": (
        "from fastapi import APIRouter\n"
        "from .draft import router as draft_router\n"
        "from .live import router as live_router\n"
        "router = APIRouter()\n"
        "router.include_router(live_router, prefix='/live')\n",
        {"draft": _ROUTER_MODULE, "live": _ROUTER_MODULE},
    ),
    "mounts nothing": ("from fastapi import APIRouter\n\nrouter = APIRouter()\n", {}),
}


@pytest.mark.parametrize("case", sorted(_CASES))
def test_both_implementations_return_the_same_mapping(tmp_path, case):
    """Equality, not a restatement — the point is that they cannot drift apart."""
    init_body, modules = _CASES[case]
    pkg = _write(tmp_path, "billing", init_body, modules)
    analytics, shared = _both(tmp_path, pkg, "/api/billing")
    assert analytics == shared, (
        f"the analytics scanner and the api-wiring gate disagree on {case!r}: "
        f"{analytics} vs {shared}. One of them is wrong about what the API serves (#13582)."
    )


def test_the_agreed_mapping_is_not_trivially_empty(tmp_path):
    """Two implementations that both return nothing agree perfectly.

    Without this, every assertion above would keep passing if either function
    started returning `{}` for everything — the failure mode where an empty
    result reads as a clean result.
    """
    init_body, modules = _CASES["mount with a prefix"]
    pkg = _write(tmp_path, "billing", init_body, modules)
    analytics, shared = _both(tmp_path, pkg, "/api/billing")
    assert analytics == {pkg / "costs.py": "/api/billing/costs"}
    assert shared == analytics


def test_nested_subpackages_agree(tmp_path):
    """The recursion is where a prefix error compounds rather than cancels."""
    parent = _write(
        tmp_path,
        "platform",
        "from fastapi import APIRouter\n"
        "from .metrics import router as metrics_router\n"
        "router = APIRouter()\n"
        "router.include_router(metrics_router, prefix='/metrics')\n",
    )
    _write(
        parent,
        "metrics",
        "from fastapi import APIRouter\n"
        "from .cpu import router as cpu_router\n"
        "router = APIRouter()\n"
        "router.include_router(cpu_router, prefix='/cpu')\n",
        {"cpu": _ROUTER_MODULE},
    )
    analytics, shared = _both(tmp_path, parent, "/api/platform")
    assert analytics == shared
    assert analytics[parent / "metrics" / "cpu.py"] == "/api/platform/metrics/cpu"
