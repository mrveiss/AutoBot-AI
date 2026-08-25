#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Verify the workflow API is registered with the backend router registry.

Checks, in order: the workflow entry exists in ``FEATURE_ROUTER_CONFIGS``, it
declares the prefix this script expects, the module it names exists on disk,
and mounting that router at the registry prefix yields the execute endpoint
operators call.

``backend.app_factory.add_api_routes`` -- which this script used to import and
read with ``inspect.getsource`` -- was deleted, and there is no ``backend``
package. Registration is now table-driven: ``app_factory._register_routers``
mounts every registry entry at ``f"/api{prefix}"``, so no ``"workflow_router"``
literal is left to grep for. The registry is read with ``ast`` rather than
imported, per the precedent in ``autobot-backend/api/presence_ws_router_test.py``
(``ssot_config.PROJECT_ROOT`` misresolves inside a git worktree -- #13357/#13409).

Issue: (#14870).
"""

import ast
import sys
from pathlib import Path
from typing import List, Optional, Tuple

# #14518: the first-party imports below carried a stale ``backend.`` package
# prefix -- no ``backend`` package exists -- and neither the repo root nor
# autobot-backend was on sys.path, so this script raised ModuleNotFoundError on
# its own import block before doing any work (#14129).
_REPO_ROOT = Path(__file__).resolve().parents[4]
_BACKEND_DIR = _REPO_ROOT / "autobot-backend"
for _entry in (str(_REPO_ROOT), str(_BACKEND_DIR)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from autobot_shared.logging_manager import get_logger  # noqa: E402
from autobot_shared.network_constants import ServiceURLs  # noqa: E402

logger = get_logger(__name__)

REGISTRY_FILE = _BACKEND_DIR / "initialization" / "router_registry" / "feature_routers.py"
REGISTRY_CONSTANT = "FEATURE_ROUTER_CONFIGS"
WORKFLOW_MODULE = "api.workflow"
EXPECTED_PREFIX = "/workflow"
# app_factory._register_routers mounts every registry entry at f"/api{prefix}".
API_MOUNT_PREFIX = "/api"
EXECUTE_PATH = "/execute"


class CheckResults:
    """Tally of check outcomes; a check that could not run is never a pass."""

    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.skipped = 0

    def record_pass(self, name: str, detail: str) -> None:
        self.passed += 1
        logger.info("PASSED  %s: %s", name, detail)

    def record_fail(self, name: str, detail: str) -> None:
        self.failed += 1
        logger.error("FAILED  %s: %s", name, detail)

    def record_skip(self, name: str, reason: str) -> None:
        self.skipped += 1
        logger.warning("SKIPPED %s: %s", name, reason)

    def summary(self) -> int:
        """Log the counts and return the process exit code."""
        logger.info("PASSED=%d FAILED=%d SKIPPED=%d", self.passed, self.failed, self.skipped)
        if self.failed or not self.passed:
            logger.error("❌ Workflow router registration NOT verified")
            return 1
        logger.info("✅ Workflow router registration verified")
        return 0


def _registry_value(tree: ast.Module) -> Optional[ast.expr]:
    """Return the assigned value node of ``REGISTRY_CONSTANT``, if present."""
    for node in tree.body:
        if isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == REGISTRY_CONSTANT:
                return node.value
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == REGISTRY_CONSTANT:
                    return node.value
    return None


def _load_registry_entries() -> Optional[List[Tuple]]:
    """Read the registry literal without importing anything from the backend."""
    tree = ast.parse(REGISTRY_FILE.read_text(encoding="utf-8"))
    value = _registry_value(tree)
    if value is None:
        return None
    return list(ast.literal_eval(value))


def _unpack(entry: Tuple) -> Tuple[str, str, List[str], str]:
    """Normalise an entry to ``(module_path, prefix, tags, name)``.

    The monitoring group carries the router attribute second -- a 5-tuple --
    while every other entry is a 4-tuple, as ``router_registry.loader._unpack``
    also handles.
    """
    if len(entry) == 5:
        module_path, _router_attr, prefix, tags, name = entry
        return module_path, prefix, tags, name
    if len(entry) == 4:
        module_path, prefix, tags, name = entry
        return module_path, prefix, tags, name
    raise ValueError(f"unsupported {REGISTRY_CONSTANT} entry arity {len(entry)}: {entry}")


def check_registry_entry(results: CheckResults) -> Optional[Tuple[str, str]]:
    """Assert the workflow router is declared, and return its module and prefix."""
    name = "registry entry"
    if not REGISTRY_FILE.is_file():
        results.record_fail(name, f"{REGISTRY_CONSTANT} source not found at {REGISTRY_FILE}")
        return None
    entries = _load_registry_entries()
    if entries is None:
        results.record_fail(name, f"{REGISTRY_CONSTANT} not declared in {REGISTRY_FILE.name}")
        return None
    matches = [_unpack(entry) for entry in entries]
    workflow = [item for item in matches if item[0] == WORKFLOW_MODULE]
    if not workflow:
        results.record_fail(name, f"{WORKFLOW_MODULE} absent from {len(matches)} registry entries")
        return None
    module_path, prefix, _tags, router_name = workflow[0]
    if prefix != EXPECTED_PREFIX:
        results.record_fail(name, f"{router_name} declares prefix {prefix!r}, expected {EXPECTED_PREFIX!r}")
        return None
    results.record_pass(name, f"{module_path} at {prefix} as {router_name!r} ({len(matches)} entries)")
    return module_path, prefix


def check_router_module(results: CheckResults, module_path: str) -> None:
    """Assert the module the registry names exists on disk."""
    name = "router module"
    module_file = _BACKEND_DIR.joinpath(*module_path.split(".")).with_suffix(".py")
    if module_file.is_file():
        results.record_pass(name, f"{module_path} resolves to {module_file.name}")
    else:
        results.record_fail(name, f"{module_path} names a missing file: {module_file}")


def check_route_registration(results: CheckResults, prefix: str) -> None:
    """Assert mounting at the registry prefix yields the execute endpoint."""
    name = "route registration"
    expected = f"{API_MOUNT_PREFIX}{prefix}{EXECUTE_PATH}"
    try:
        from api.workflow import router as workflow_router
        from fastapi import FastAPI
    except ImportError as exc:
        results.record_skip(name, f"backend imports unavailable ({exc})")
        return
    except Exception as exc:  # noqa: BLE001 - reported as a failure, never swallowed
        results.record_fail(name, f"importing {WORKFLOW_MODULE} raised {type(exc).__name__}: {exc}")
        return
    app = FastAPI()
    app.include_router(workflow_router, prefix=f"{API_MOUNT_PREFIX}{prefix}")
    paths = {getattr(route, "path", "") for route in app.routes}
    if expected in paths:
        results.record_pass(name, f"{expected} registered ({len(workflow_router.routes)} workflow routes)")
    else:
        results.record_fail(name, f"{expected} missing; mounted: {sorted(p for p in paths if prefix in p)}")


def main() -> int:
    """Run every check and return the exit code."""
    logger.info("🔍 Verifying workflow router registration (#14870)")
    results = CheckResults()
    entry = check_registry_entry(results)
    if entry is None:
        results.record_skip("router module", "registry entry unavailable")
        results.record_skip("route registration", "registry entry unavailable")
    else:
        module_path, prefix = entry
        check_router_module(results, module_path)
        check_route_registration(results, prefix)
        endpoint = f"{ServiceURLs.BACKEND_LOCAL}{API_MOUNT_PREFIX}{prefix}{EXECUTE_PATH}"
        logger.info("Check a running backend with: curl -X POST %s", endpoint)
    return results.summary()


if __name__ == "__main__":
    sys.exit(main())
